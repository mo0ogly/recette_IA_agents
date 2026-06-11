# Generics (Go 1.21+) -- LIA-SEC Idiomatic Usage

Load this reference when using type parameters, constraints, or writing generic slice/map helpers.

## Table of Contents

1. When to use generics (and when NOT to)
2. Basic syntax
3. Constraints: `any`, `comparable`, unions
4. Standard constraints
5. Common patterns: Filter, Map, Reduce, Keys, Values
6. Generic data structures
7. Anti-patterns

---

## 1. When to use generics (and when NOT to)

**Use generics when**:
- Writing a data structure that works for multiple types (linked list, cache, pool)
- Writing utility functions that operate on slices/maps of any type (Filter, Map, Keys)
- Building a type-safe client that returns different struct types per call

**DO NOT use generics when**:
- An interface satisfies the need (interfaces are often the right abstraction)
- The code is used with exactly one type today and foreseeable future
- It hurts readability for no measurable benefit
- Performance is critical and generics add overhead (monomorphization cost)

Rule: if in doubt, don't. Refactor into generics when you have 2+ concrete copies.

---

## 2. Basic syntax

```go
// Function with type parameter T constrained to any
func Identity[T any](v T) T {
    return v
}

// Function with constraint from constraints package
func Max[T cmp.Ordered](a, b T) T {
    if a > b { return a }
    return b
}

// Generic type
type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(v T)    { s.items = append(s.items, v) }
func (s *Stack[T]) Pop() (T, bool) {
    var zero T
    if len(s.items) == 0 { return zero, false }
    last := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return last, true
}
```

---

## 3. Constraints: any, comparable, unions

| Constraint | Allows | Notes |
|-----------|--------|-------|
| `any` | Any type | Equivalent to `interface{}` |
| `comparable` | Types that support `==` and `!=` | Most types except slices, maps, funcs |
| Union `int \| int64` | Either `int` or `int64` | Use with type parameters |
| `~int` | Any type whose underlying type is `int` | Includes `type MyInt int` |

Union + underlying:
```go
type Number interface {
    ~int | ~int64 | ~float64
}

func Sum[T Number](xs []T) T {
    var total T
    for _, x := range xs { total += x }
    return total
}
```

---

## 4. Standard constraints

Go 1.21+ provides `cmp.Ordered` and the `constraints` package (via `golang.org/x/exp/constraints`):

```go
import "cmp"

type Ordered = cmp.Ordered // int, float, string, etc.
```

Use `cmp.Ordered` for anything that supports `<`, `<=`, `>`, `>=`.

`comparable` is sufficient for `==` (map keys, etc.).

---

## 5. Common patterns

### Filter
```go
func Filter[T any](xs []T, pred func(T) bool) []T {
    out := make([]T, 0, len(xs))
    for _, x := range xs {
        if pred(x) {
            out = append(out, x)
        }
    }
    return out
}

// Usage
active := Filter(users, func(u User) bool { return u.Active })
```

### Map
```go
func Map[T, U any](xs []T, fn func(T) U) []U {
    out := make([]U, len(xs))
    for i, x := range xs {
        out[i] = fn(x)
    }
    return out
}

// Usage
names := Map(users, func(u User) string { return u.Name })
```

### Reduce
```go
func Reduce[T, U any](xs []T, init U, fn func(U, T) U) U {
    acc := init
    for _, x := range xs {
        acc = fn(acc, x)
    }
    return acc
}

// Usage
total := Reduce(items, 0.0, func(acc float64, it Item) float64 {
    return acc + it.Price
})
```

### Keys / Values (map helpers)
```go
func Keys[K comparable, V any](m map[K]V) []K {
    out := make([]K, 0, len(m))
    for k := range m {
        out = append(out, k)
    }
    return out
}

func Values[K comparable, V any](m map[K]V) []V {
    out := make([]V, 0, len(m))
    for _, v := range m {
        out = append(out, v)
    }
    return out
}
```

### Contains
```go
func Contains[T comparable](xs []T, target T) bool {
    for _, x := range xs {
        if x == target { return true }
    }
    return false
}
```

Many of these are in `slices` and `maps` standard packages since Go 1.21 -- prefer the stdlib:

```go
import "slices"
slices.Contains(xs, target)
slices.Sort(xs) // requires cmp.Ordered
slices.SortFunc(xs, cmp)
```

---

## 6. Generic data structures

### Typed cache
```go
type Cache[K comparable, V any] struct {
    mu   sync.RWMutex
    data map[K]V
}

func NewCache[K comparable, V any]() *Cache[K, V] {
    return &Cache[K, V]{data: make(map[K]V)}
}

func (c *Cache[K, V]) Get(k K) (V, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    v, ok := c.data[k]
    return v, ok
}

func (c *Cache[K, V]) Set(k K, v V) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.data[k] = v
}
```

### Result type (success/error union, explicit)
```go
type Result[T any] struct {
    Value T
    Err   error
}

func Ok[T any](v T) Result[T]    { return Result[T]{Value: v} }
func Fail[T any](e error) Result[T] { return Result[T]{Err: e} }
```

(Usage is controversial in Go; prefer multi-return `(T, error)`. Use Result only for channel-based async patterns.)

---

## 7. Anti-patterns

### Forcing generics where interfaces suffice
```go
// WRONG: generics on something that's really just a Stringer
func Print[T fmt.Stringer](v T) { fmt.Println(v.String()) }

// RIGHT: interface
func Print(v fmt.Stringer) { fmt.Println(v.String()) }
```

### Monster constraint unions
```go
// WRONG: if you need 20+ types, you're building an interface
type AllNumbers interface {
    int | int8 | int16 | int32 | int64 |
    uint | uint8 | uint16 | uint32 | uint64 |
    float32 | float64 | complex64 | complex128
}
```

Use `~int | ~float64` sparingly; prefer domain-specific constraints.

### Generic + reflection
Generics remove the NEED for reflection in many cases. If you find yourself using `reflect` inside a generic function, stop and reconsider.

---

## LIA-SEC notes

- The codebase does NOT yet use generics widely (legacy Go 1.18+ code predates them). New packages MAY use generics for slice/map helpers.
- Prefer stdlib `slices` / `maps` packages over writing your own generic helpers.
- For engine types (`pkg/model/`), stick with concrete types -- the engine's shape is fixed and interface + concrete is clearer.
