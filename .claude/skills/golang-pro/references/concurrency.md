# Concurrency -- LIA-SEC Idiomatic Go

Load this reference when writing goroutines, channels, select, sync primitives, worker pools, or any fan-out/fan-in pattern.

## Table of Contents

1. Context propagation (mandatory)
2. Worker pool pattern (bounded concurrency)
3. Fan-out / fan-in
4. select + ctx.Done() skeleton
5. sync.Mutex vs channels -- decision
6. errgroup for coordinated errors
7. Rate limiting (token bucket)
8. Common leak patterns + fixes

---

## 1. Context propagation (mandatory)

Every blocking operation MUST accept `context.Context` as its first parameter. Handlers use `r.Context()`. Background jobs use `context.Background()` with a timeout.

```go
// Handler derives context from request
func fooHandler(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()
    result, err := doWork(ctx, input)
    // ...
}

// Background job with explicit timeout
func runJob(parent context.Context) error {
    ctx, cancel := context.WithTimeout(parent, 30*time.Second)
    defer cancel()
    return doWork(ctx)
}
```

**LIA-SEC rule**: in handlers, propagate to every `db.QueryContext(ctx, ...)`, `http.NewRequestWithContext(ctx, ...)`, and child goroutine.

---

## 2. Worker pool pattern (bounded concurrency)

Prefer bounded pools over unlimited `go func()`. Default pool size: `runtime.NumCPU()` for CPU-bound, higher (2-4x) for IO-bound.

```go
func processBatch(ctx context.Context, items []Item, workers int) error {
    jobs := make(chan Item, len(items))
    errCh := make(chan error, workers)
    var wg sync.WaitGroup

    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for {
                select {
                case <-ctx.Done():
                    errCh <- ctx.Err()
                    return
                case item, ok := <-jobs:
                    if !ok {
                        return
                    }
                    if err := handle(ctx, item); err != nil {
                        errCh <- fmt.Errorf("item %v: %w", item.ID, err)
                        return
                    }
                }
            }
        }()
    }

    for _, it := range items {
        select {
        case <-ctx.Done():
            close(jobs)
            wg.Wait()
            return ctx.Err()
        case jobs <- it:
        }
    }
    close(jobs)
    wg.Wait()
    close(errCh)

    for err := range errCh {
        if err != nil {
            return err
        }
    }
    return nil
}
```

Key properties: bounded workers, context-cancellable, error surfaces on first failure, no goroutine leak.

---

## 3. Fan-out / fan-in

Distribute work across N goroutines, merge results into a single channel.

```go
func fanOut(ctx context.Context, in <-chan Job, n int) <-chan Result {
    out := make(chan Result)
    var wg sync.WaitGroup

    for i := 0; i < n; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range in {
                select {
                case <-ctx.Done():
                    return
                case out <- process(job):
                }
            }
        }()
    }

    go func() {
        wg.Wait()
        close(out)
    }()
    return out
}
```

---

## 4. select + ctx.Done() skeleton

Standard skeleton for any goroutine that must respect cancellation:

```go
for {
    select {
    case <-ctx.Done():
        return ctx.Err()
    case msg, ok := <-input:
        if !ok {
            return nil // channel closed, clean exit
        }
        if err := handle(ctx, msg); err != nil {
            return err
        }
    }
}
```

---

## 5. sync.Mutex vs channels -- decision

| Use channels when | Use sync.Mutex when |
|-------------------|---------------------|
| Passing ownership of data | Protecting shared state (counters, maps) |
| Signaling events | Ref-counting, caching |
| Fan-out / fan-in | Small critical section with no transfer |
| Coordinating multiple goroutines | Guard a single struct field |

**Rule of thumb**: if the code reads like "goroutine A sends X to goroutine B", use a channel. If the code reads like "multiple goroutines mutate X", use a mutex.

Avoid `sync.RWMutex` unless measured contention justifies it (typically read >> write).

---

## 6. errgroup for coordinated errors

When N goroutines must all succeed (or the first failure cancels the rest), use `golang.org/x/sync/errgroup`:

```go
import "golang.org/x/sync/errgroup"

func fetchAll(ctx context.Context, urls []string) ([]Response, error) {
    g, ctx := errgroup.WithContext(ctx)
    responses := make([]Response, len(urls))

    for i, u := range urls {
        i, u := i, u // capture
        g.Go(func() error {
            r, err := fetch(ctx, u)
            if err != nil {
                return fmt.Errorf("fetch %s: %w", u, err)
            }
            responses[i] = r
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return responses, nil
}
```

errgroup propagates the first error via the returned ctx -- other goroutines can observe `ctx.Done()` and exit early.

---

## 7. Rate limiting (token bucket)

LIA-SEC has a token-bucket rate limiter in `cmd/sigma_web/rate_limiter.go` (60 req/min/IP). For new endpoints, wire it in via the existing middleware -- do not reimplement.

For outbound calls (e.g. to an AI provider), use `golang.org/x/time/rate`:

```go
limiter := rate.NewLimiter(rate.Every(100*time.Millisecond), 5) // 10 rps, burst 5
if err := limiter.Wait(ctx); err != nil {
    return fmt.Errorf("rate limit wait: %w", err)
}
resp, err := callProvider(ctx, req)
```

---

## 8. Common leak patterns + fixes

### Leak: unbounded goroutines
```go
// WRONG
for _, item := range items {
    go process(item) // no lifecycle, no errors captured
}

// FIX: errgroup or worker pool (see section 2, 6)
```

### Leak: goroutine blocked on send to unread channel
```go
// WRONG
ch := make(chan Result)
go func() { ch <- compute() }() // blocks forever if caller never reads
return
```

Always close or drain, or use buffered channels with known capacity, or propagate cancellation.

### Leak: forgotten `defer cancel()` on WithTimeout
```go
ctx, cancel := context.WithTimeout(parent, 5*time.Second)
// WRONG: missing defer cancel()
result := doWork(ctx)
```

Always `defer cancel()` immediately after `WithTimeout`/`WithCancel`/`WithDeadline`.

### Leak: ticker not stopped
```go
t := time.NewTicker(time.Second)
// defer t.Stop() -- REQUIRED
for range t.C { ... }
```

---

## Testing concurrent code

- Always run with `-race`: `go test -race -count=1 ./pkg/...`
- Deterministic tests: don't rely on timing. Use channels to synchronize.
- Stress: `go test -race -count=100 -run TestConcurrent` to surface rare races.
