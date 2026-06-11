# Testing & Benchmarks -- LIA-SEC Go

Load this reference when writing `*_test.go`, httptest handlers, benchmarks, pprof profiles, or fuzz tests.

## Table of Contents

1. Table-driven tests (mandatory pattern)
2. httptest for HTTP handlers
3. Subtests + t.Run
4. Race detector (-race)
5. Benchmarks
6. pprof profiling
7. Fuzzing (Go 1.18+)
8. Coverage
9. LIA-SEC conventions

---

## 1. Table-driven tests (mandatory pattern)

Every unit test in LIA-SEC MUST be table-driven with subtests. This is the canonical shape:

```go
func TestTruncate(t *testing.T) {
    tests := []struct {
        name string
        in   string
        max  int
        want string
    }{
        {"empty", "", 10, ""},
        {"under", "abc", 10, "abc"},
        {"exact", "abcdefghij", 10, "abcdefghij"},
        {"over", "abcdefghijk", 10, "abcdefgh..."},
        {"unicode", "longtext", 4, "l..."},
    }

    for _, tc := range tests {
        tc := tc // capture
        t.Run(tc.name, func(t *testing.T) {
            t.Parallel() // safe if no shared mutable state
            got := truncate(tc.in, tc.max)
            if got != tc.want {
                t.Errorf("truncate(%q, %d) = %q, want %q", tc.in, tc.max, got, tc.want)
            }
        })
    }
}
```

Guidelines:
- Name each case descriptively (will show in `t.Run` output).
- Use `t.Parallel()` when safe. Always capture `tc := tc` before.
- Assertions use `t.Errorf` (continue) not `t.Fatalf` (stop) -- let the table run fully.

---

## 2. httptest for HTTP handlers

For every handler in `cmd/sigma_web/`, write at minimum these 4 cases (R17 Go Contract Gate):

1. 200 success
2. 401 unauthenticated (if route is protected)
3. 400 invalid input
4. 500 db error

```go
func TestFooList(t *testing.T) {
    tests := []struct {
        name       string
        query      string
        seed       func(t *testing.T)
        wantStatus int
        wantKey    string
    }{
        {
            name:       "success returns envelope",
            query:      "",
            seed:       func(t *testing.T) { seedFoos(t, 3) },
            wantStatus: http.StatusOK,
            wantKey:    "data",
        },
        {
            name:       "invalid limit returns 400",
            query:      "?limit=abc",
            seed:       func(t *testing.T) {},
            wantStatus: http.StatusBadRequest,
        },
    }

    for _, tc := range tests {
        tc := tc
        t.Run(tc.name, func(t *testing.T) {
            tc.seed(t)
            req := httptest.NewRequest(http.MethodGet, "/api/foo/list"+tc.query, nil)
            rec := httptest.NewRecorder()

            fooList(rec, req)

            if rec.Code != tc.wantStatus {
                t.Fatalf("status = %d, want %d", rec.Code, tc.wantStatus)
            }
            if tc.wantKey != "" {
                var envelope map[string]any
                if err := json.Unmarshal(rec.Body.Bytes(), &envelope); err != nil {
                    t.Fatalf("unmarshal: %v", err)
                }
                if _, ok := envelope[tc.wantKey]; !ok {
                    t.Errorf("missing key %q in response", tc.wantKey)
                }
            }
        })
    }
}
```

R17 rule: the test MUST render against a **real payload** (captured from the live backend with curl and saved to a fixture) before the component/handler can close its wave.

---

## 3. Subtests + t.Run

Subtests enable:
- Running a single case: `go test -run TestFoo/case_name`
- Parallel execution via `t.Parallel()`
- Grouping related tests
- Better output in CI

Prefer subtests over `TestFoo1`, `TestFoo2`, `TestFoo3`.

---

## 4. Race detector (-race)

MANDATORY for any package with goroutines:

```bash
go test -race -count=1 ./pkg/engine/...
```

The race detector adds ~10x runtime cost but catches data races that would cause rare production bugs. NEVER skip it for packages with concurrency.

In CI, always run `-race` for the full test suite of packages touched by the change.

---

## 5. Benchmarks

Benchmarks go in `*_test.go` with `BenchmarkXxx` names:

```go
func BenchmarkParseRule(b *testing.B) {
    data := mustReadFile(b, "testdata/rule.yml")
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        _, err := parseRule(data)
        if err != nil {
            b.Fatalf("parse: %v", err)
        }
    }
}
```

Run:
```bash
go test -bench=BenchmarkParseRule -benchmem -count=5 -run=^$ ./pkg/model/
```

Flags:
- `-bench=...` : run benchmarks matching pattern
- `-benchmem` : report memory allocations per op
- `-count=N` : run N times (stability)
- `-run=^$` : skip tests, benchmarks only

Sub-benchmarks for parameter sweeps:
```go
func BenchmarkParse(b *testing.B) {
    for _, n := range []int{10, 100, 1000, 10000} {
        b.Run(fmt.Sprintf("n=%d", n), func(b *testing.B) {
            rules := genRules(n)
            b.ResetTimer()
            for i := 0; i < b.N; i++ {
                parse(rules)
            }
        })
    }
}
```

---

## 6. pprof profiling

For performance investigation, collect profiles:

```bash
# CPU profile during benchmark
go test -bench=. -cpuprofile=cpu.out -run=^$ ./pkg/engine/

# Memory profile
go test -bench=. -memprofile=mem.out -run=^$ ./pkg/engine/

# Analyze
go tool pprof cpu.out
# (interactive) top10, list funcname, web
```

For live backend, expose `/debug/pprof/` via `net/http/pprof` (LIA-SEC does NOT expose this in prod by default -- add only under an admin gate if needed).

---

## 7. Fuzzing (Go 1.18+)

For parsers, validators, serializers -- anything that ingests untrusted input:

```go
func FuzzParseRule(f *testing.F) {
    // Seed corpus
    f.Add([]byte("title: foo\ntags: [a, b]"))
    f.Add([]byte("{}"))

    f.Fuzz(func(t *testing.T, data []byte) {
        rule, err := parseRule(data)
        if err != nil {
            return // invalid input is expected
        }
        // Any successfully parsed rule must re-serialize and re-parse identically
        serialized, err := serializeRule(rule)
        if err != nil {
            t.Fatalf("serialize: %v", err)
        }
        reparsed, err := parseRule(serialized)
        if err != nil {
            t.Fatalf("re-parse: %v", err)
        }
        if !reflect.DeepEqual(rule, reparsed) {
            t.Fatalf("round-trip mismatch")
        }
    })
}
```

Run:
```bash
go test -fuzz=FuzzParseRule -fuzztime=30s ./pkg/model/
```

Fuzz corpus is cached in `testdata/fuzz/FuzzXxx/`. Commit crashers to lock regressions.

---

## 8. Coverage

Target: **>= 80% on new code**.

```bash
# Per-package coverage
go test -coverprofile=cover.out ./pkg/validator/...
go tool cover -func=cover.out
go tool cover -html=cover.out -o cover.html # visual

# Integration in CI
go test -cover ./pkg/... | grep -v "no test"
```

Don't chase 100% -- test public behavior, not private helpers. Edge cases and error paths matter more than line coverage.

---

## 9. LIA-SEC conventions

### Test file location
- Same directory as source: `cmd/sigma_web/foo.go` -> `cmd/sigma_web/foo_test.go`
- NOT in a separate `_test` directory

### Test fixtures
- `testdata/` subdirectory (Go toolchain excludes this from compilation)
- R17 contract fixtures: `sigma-react-frontend/src/components/__fixtures__/{component}.fixture.json` mirrored on the Go side with captured payloads

### Running tests
```bash
# Full backend test suite
cd /opt/lia-sec/dev/cmd/sigma_web && go test -race -count=1 ./...

# Single handler
go test -race -run TestFooList ./cmd/sigma_web/

# Engine
cd /opt/lia-sec/dev && go test -race ./pkg/engine/...
```

### Skip in CI
Use `testing.Short()` and `-short` flag for slow tests:

```go
func TestSlowIntegration(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping in short mode")
    }
    // ...
}
```

CI runs `go test -short` by default; nightly runs full suite.

### test-first skill
After creating or modifying a handler, invoke `/test-first` to enforce the `_test.go` gate. Failing tests = BLOQUANT before commit.
