# Interfaces -- LIA-SEC Idiomatic Design

Load this reference when designing a new package contract, composing `io.Reader`/`io.Writer`, or planning a mocking strategy.

## Table of Contents

1. Design principles
2. Small + focused (1-3 methods)
3. Composition over inheritance
4. Accept interfaces, return structs
5. Standard library interfaces to compose
6. Mocking strategy
7. LIA-SEC examples

---

## 1. Design principles

- **Define interfaces at the consumer**, not the producer. The package that USES the abstraction owns the interface.
- **Start small**: 1-3 methods. Grow only when genuinely needed.
- **Name by behavior**: `Reader`, `Writer`, `Closer`, `StringConverter`, `RuleValidator`. NOT `IManager`, `FooService`.
- **Single responsibility per interface**. If it's doing two things, it should be two interfaces.

Anti-pattern (over-engineered):
```go
// WRONG: God interface
type UserService interface {
    GetUser(id string) (*User, error)
    CreateUser(u *User) error
    UpdateUser(u *User) error
    DeleteUser(id string) error
    SendEmail(u *User) error
    LogActivity(u *User, action string) error
    ValidatePassword(u *User, pw string) bool
}
```

Idiomatic:
```go
// RIGHT: split by capability; compose at the call site
type UserReader interface {
    GetUser(ctx context.Context, id string) (*User, error)
}
type UserWriter interface {
    CreateUser(ctx context.Context, u *User) error
    UpdateUser(ctx context.Context, u *User) error
    DeleteUser(ctx context.Context, id string) error
}
```

---

## 2. Small + focused (1-3 methods)

Interfaces with 1 method are the strongest. They are easy to mock, compose, and pass around.

Classic single-method interfaces:

```go
type Reader interface { Read(p []byte) (n int, err error) }
type Writer interface { Write(p []byte) (n int, err error) }
type Stringer interface { String() string }
type Error interface { Error() string }
```

LIA-SEC example:
```go
// Validator validates a single rule and returns issues found.
type Validator interface {
    Validate(ctx context.Context, rule *sigmarule.Rule) ([]Issue, error)
}
```

---

## 3. Composition over inheritance

Go has no inheritance. Compose interfaces to build richer contracts:

```go
type ReadCloser interface {
    io.Reader
    io.Closer
}

type ReadWriteCloser interface {
    io.Reader
    io.Writer
    io.Closer
}
```

LIA-SEC example:
```go
type RuleValidator interface {
    Validator
    Namer // added: returns the validator's name for logs
}

type Namer interface {
    Name() string
}
```

---

## 4. Accept interfaces, return structs

Functions SHOULD accept interfaces (flexibility at call site) but RETURN concrete types (preserve caller's access to specific methods).

```go
// GOOD
func NewProcessor(store RuleReader) *Processor {
    return &Processor{store: store}
}

// AVOID: returning interface loses type info
func NewProcessor(store RuleReader) interface{ Process() error } {
    return &Processor{store: store}
}
```

Exceptions: when the function truly returns one of several concrete types (factory pattern), returning an interface is justified.

---

## 5. Standard library interfaces to compose

| Interface | Methods | Use for |
|-----------|---------|---------|
| `io.Reader` | `Read([]byte) (int, error)` | Streaming input |
| `io.Writer` | `Write([]byte) (int, error)` | Streaming output (handlers write to `http.ResponseWriter`) |
| `io.Closer` | `Close() error` | Resource cleanup |
| `fmt.Stringer` | `String() string` | Human-readable representation |
| `error` | `Error() string` | Errors |
| `sort.Interface` | `Len/Less/Swap` | Custom sorting |
| `http.Handler` | `ServeHTTP(w, r)` | HTTP handlers |
| `driver.Valuer` + `sql.Scanner` | Marshal/Unmarshal to/from SQL | Custom DB types |
| `encoding.TextMarshaler/Unmarshaler` | Text serialization | Config, URL params |
| `json.Marshaler/Unmarshaler` | Custom JSON | API types |

LIA-SEC hint: implement `fmt.Stringer` on domain types for better logs with `LogSystemEvent(..., ..., ..., fmt.Sprintf("%s", obj))`.

---

## 6. Mocking strategy

Small interfaces are trivially mockable. Two approaches:

### Hand-written fake (preferred for simple interfaces)
```go
type fakeRuleReader struct {
    rules map[string]*sigmarule.Rule
    err   error
}

func (f *fakeRuleReader) GetRule(ctx context.Context, id string) (*sigmarule.Rule, error) {
    if f.err != nil { return nil, f.err }
    r, ok := f.rules[id]
    if !ok { return nil, ErrNotFound }
    return r, nil
}
```

### Generated mock (for large interfaces)
Use `gomock` or `mockery`. Prefer hand-written if the interface has <= 3 methods.

LIA-SEC does NOT use mockery by default. Prefer hand-written fakes in `*_test.go`.

---

## 7. LIA-SEC examples

### pkg/validator (recipe, ultimate, reportrule)

```go
type Validator interface {
    Validate(rulePath string) ([]Finding, error)
    Name() string
}

// Implementations:
//   pkg/validator/recipe.Validator
//   pkg/validator/ultimate.Validator
//   pkg/validator/reportrule.Validator

// Composite invokes all validators.
type Composite struct {
    validators []Validator
}

func (c *Composite) Validate(rulePath string) ([]Finding, error) {
    var all []Finding
    for _, v := range c.validators {
        findings, err := v.Validate(rulePath)
        if err != nil {
            return nil, fmt.Errorf("%s validate: %w", v.Name(), err)
        }
        all = append(all, findings...)
    }
    return all, nil
}
```

### AI provider (from `ai_universal_provider.go`)

```go
type AIProvider interface {
    Call(ctx context.Context, prompt string, opts CallOpts) (string, error)
    HealthCheck(ctx context.Context) error
    Name() string
}

// Implementations: GroqProvider, OllamaProvider, etc.
// Fallback chain iterates []AIProvider by priority from ai_providers table.
```

---

## Interface documentation

Every exported interface MUST have a doc comment:

```go
// RuleValidator validates a single rule and returns zero or more findings.
// Implementations must be safe for concurrent use.
// Validate respects context cancellation.
type RuleValidator interface {
    Validate(ctx context.Context, rule *sigmarule.Rule) ([]Finding, error)
}
```

Include: purpose, concurrency safety, cancellation behavior, nil/empty input behavior.
