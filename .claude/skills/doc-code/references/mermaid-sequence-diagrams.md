# Sequence Diagrams

Sequence diagrams show interactions between participants over time. Ideal for API flows, authentication sequences, and system component interactions.

## Basic Syntax

```mermaid
sequenceDiagram
    participant A
    participant B
    A->>B: Message
```

## Participants and Actors

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant API
    participant Database

    User->>Frontend: Click button
    Frontend->>API: POST /data
```

**Difference:**
- `participant` - System components (services, classes, databases)
- `actor` - External entities (users, external systems)

## Message Types

### Solid Arrow (Synchronous)
- `->>`  Solid arrow (request)
- `-->>`  Dotted arrow (response/return)

```mermaid
sequenceDiagram
    Client->>Server: Request
    Server-->>Client: Response
```

### Open Arrow (Asynchronous)
- `-)` Solid open arrow
- `--)` Dotted open arrow

```mermaid
sequenceDiagram
    Client-)Server: Async message
    Server--)Client: Async response
```

### Cross/X (Delete)
```mermaid
sequenceDiagram
    Client-xServer: Delete
```

## Activations

Show when a participant is actively processing:

```mermaid
sequenceDiagram
    Client->>+Server: Request
    Server->>+Database: Query
    Database-->>-Server: Data
    Server-->>-Client: Response
```

- `+` after arrow activates
- `-` before arrow deactivates

## Alt/Else (Conditional Logic)

```mermaid
sequenceDiagram
    User->>API: POST /login
    API->>Database: Query user
    Database-->>API: User data

    alt Valid credentials
        API-->>User: 200 OK + Token
    else Invalid credentials
        API-->>User: 401 Unauthorized
    else Account locked
        API-->>User: 403 Forbidden
    end
```

## Opt (Optional)

```mermaid
sequenceDiagram
    User->>API: POST /order
    API->>PaymentService: Process payment

    opt Payment successful
        API->>EmailService: Send confirmation
    end

    API-->>User: Order result
```

## Par (Parallel)

Show concurrent operations:

```mermaid
sequenceDiagram
    API->>Service: Process order

    par Send email
        Service->>EmailService: Send confirmation
    and Update inventory
        Service->>InventoryService: Reduce stock
    and Log event
        Service->>LogService: Log order
    end

    Service-->>API: Complete
```

## Loop

```mermaid
sequenceDiagram
    Client->>Server: Request batch

    loop For each item
        Server->>Database: Process item
        Database-->>Server: Result
    end

    Server-->>Client: All results
```

## Break (Early Exit)

```mermaid
sequenceDiagram
    User->>API: Submit form
    API->>Validator: Validate input

    break Input invalid
        API-->>User: 400 Bad Request
    end

    API->>Database: Save data
    Database-->>API: Success
    API-->>User: 200 OK
```

## Notes

```mermaid
sequenceDiagram
    Frontend->>API: Request
    Note over Frontend,API: HTTPS encrypted
    Note right of API: Validates JWT token
    API-->>Frontend: Response
```

## Sequence Numbers

```mermaid
sequenceDiagram
    autonumber

    User->>Frontend: Login
    Frontend->>API: Authenticate
    API->>Database: Verify credentials
    Database-->>API: User data
    API-->>Frontend: JWT token
    Frontend-->>User: Success
```

## Comprehensive Example: LIA-SEC JWT Auth Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as React Frontend
    participant Backend as Go Backend :8081
    participant DB as PostgreSQL

    User->>+Frontend: Enter credentials
    Frontend->>+Backend: POST /api/auth/login {email, password}

    Backend->>+DB: SELECT user WHERE email=?
    DB-->>-Backend: user row + hashed_password

    alt User not found
        Backend-->>Frontend: 404 User not found
        Frontend-->>User: Show error
    else User found
        Backend->>Backend: bcrypt.CompareHashAndPassword()

        alt Invalid password
            Backend-->>Frontend: 401 Invalid credentials
            Frontend-->>User: Show error
        else Valid password
            Backend->>Backend: Generate JWT (24h expiry)
            Backend->>DB: UPDATE last_login
            Backend-->>-Frontend: 200 {token: JWT}
            Frontend->>Frontend: Store token (localStorage)
            Frontend-->>-User: Redirect to dashboard
        end
    end

    Note over Frontend,Backend: fetchWithConfig injects Bearer token on all subsequent calls
```

## Microservices Communication

```mermaid
sequenceDiagram
    actor User
    participant Gateway
    participant OrderService
    participant PaymentService
    participant InventoryService
    participant MessageQueue

    User->>+Gateway: POST /orders
    Gateway->>+OrderService: Create order

    OrderService->>+InventoryService: Check stock
    InventoryService-->>-OrderService: Stock available

    break Insufficient stock
        OrderService-->>Gateway: 400 Out of stock
        Gateway-->>User: Error message
    end

    OrderService->>+PaymentService: Charge customer

    alt Payment successful
        PaymentService-->>-OrderService: Payment confirmed
        OrderService->>MessageQueue: Publish OrderConfirmed

        par Async processing
            MessageQueue->>InventoryService: Reduce stock
        and
            MessageQueue->>User: Email confirmation
        end

        OrderService-->>-Gateway: 201 Created
        Gateway-->>User: Order confirmed
    else Payment failed
        PaymentService-->>OrderService: Payment declined
        OrderService-->>Gateway: 402 Payment Required
        Gateway-->>User: Payment failed
    end
```

## Best Practices

1. **Order participants logically** -- User -> Frontend -> Backend -> Database
2. **Use activations** -- Shows when components are actively processing
3. **Group related logic** -- Use `alt`/`opt`/`par` to organize conditional flows
4. **Add descriptive notes** -- Explain complex logic or important details
5. **Keep diagrams focused** -- One scenario per diagram
6. **Number messages** -- Use `autonumber` for complex flows
7. **Show error paths** -- Document failure scenarios with `alt`/`else`
8. **Indicate async operations** -- Use open arrows (`-)`) for fire-and-forget

## Common Use Cases (LIA-SEC)

| Scenario | Participants |
|----------|-------------|
| JWT authentication | User, React, Go Backend, PostgreSQL |
| AI call (ExecuteWithRAG) | Handler, FallbackEngine, Groq API, Ollama |
| ETL pipeline trigger | n8n, ETL Scheduler, PostgreSQL, External APIs |
| Rule validation | UI, Backend, LIA-Scan Engine, PostgreSQL |
| Discovery scan | Frontend, Backend, LiaProbe Agent, CMDB |
