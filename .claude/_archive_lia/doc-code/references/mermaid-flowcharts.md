# Flowcharts

Flowcharts visualize processes, algorithms, decision trees, and user journeys. They show step-by-step progression through a system or workflow.

## Basic Syntax

```mermaid
flowchart TD
    A --> B
```

**Directions:**
- `TD` or `TB` - Top to Bottom (default)
- `BT` - Bottom to Top
- `LR` - Left to Right
- `RL` - Right to Left

## Node Shapes

| Shape | Syntax | Use case |
|-------|--------|----------|
| Rectangle (default) | `A[Process step]` | Standard process |
| Rounded rectangle | `B([Rounded])` | Start/end |
| Stadium/Pill | `C(Start or End)` | Entry/exit points |
| Subroutine | `D[[Subroutine]]` | Called subprocess |
| Cylindrical | `E[(Database)]` | Storage |
| Circle | `F((Circle))` | Events |
| Rhombus | `G{Decision?}` | Yes/No branch |
| Hexagon | `H{{Hexagon}}` | Preparation |
| Parallelogram | `I[/Input Output/]` | I/O operations |
| Trapezoid | `J[/Trapezoid\]` | Manual operation |

## Connections

```mermaid
flowchart LR
    A --> B           %% Basic arrow
    C --- D           %% Open link (no arrow)
    E -->|Label| F    %% Labeled arrow
    G -.-> H          %% Dotted arrow
    I ==> J           %% Thick arrow
    K -.Label.-> L    %% Dotted labeled
    M ==Label==> N    %% Thick labeled
```

### Multi-target chaining
```mermaid
flowchart LR
    A --> B & C & D
    B & C & D --> E
```

## Subgraphs

Group related nodes:

```mermaid
flowchart TB
    A[Start]

    subgraph Processing
        B[Step 1]
        C[Step 2]
        D[Step 3]
    end

    E[End]

    A --> B
    D --> E
```

### Nested Subgraphs with Direction
```mermaid
flowchart LR
    subgraph Frontend
        direction TB
        UI[React UI]
        State[State Manager]
        UI --> State
    end

    subgraph Backend
        direction TB
        API[Go Handler]
        DB[(PostgreSQL)]
        API --> DB
    end

    Frontend --> Backend
```

## Styling

### Class-based Styling
```mermaid
flowchart LR
    A[Node 1]:::success
    B[Node 2]:::warning
    C[Node 3]:::critical

    classDef success fill:#003d1a,stroke:#06d6a0,color:#b7f4cc
    classDef warning fill:#3d2800,stroke:#f4a261,color:#ffe5c0
    classDef critical fill:#4a0000,stroke:#ff0000,color:#ffaaaa

    A --> B --> C
```

### Individual Node Styling
```mermaid
flowchart LR
    A[Normal]
    B[Styled]

    style B fill:#0f3460,stroke:#00b4d8,color:#90e0ef,stroke-width:2px
```

## Comprehensive Example: LIA-Scan Rule Validation Pipeline

```mermaid
flowchart TD
    Start([Rule submitted]) --> Recipe[Recipe validation\n41 checks]
    Recipe --> RecipeOk{Recipe passed?}

    RecipeOk -->|NO| Fail([Fix required])
    RecipeOk -->|YES| Ultimate[Ultimate validation\n91 checks]

    Ultimate --> UltimateOk{Ultimate passed?}
    UltimateOk -->|NO| Fail
    UltimateOk -->|YES| ReportRule[ReportRule JSON\n8 checks]

    ReportRule --> ReportOk{ReportRule passed?}
    ReportOk -->|NO| Fail
    ReportOk -->|YES| Commit([Commit allowed])

    style Start fill:#003d1a,stroke:#06d6a0,color:#b7f4cc
    style Commit fill:#003d1a,stroke:#06d6a0,color:#b7f4cc
    style Fail fill:#4a0000,stroke:#ff0000,color:#ffaaaa
```

## CI/CD Pipeline Example

```mermaid
flowchart LR
    subgraph Development
        Commit[Developer commits] --> Push[Push to repo]
    end

    subgraph CI
        Push --> Trigger[Trigger CI]
        Trigger --> Lint[Run linters]
        Lint --> Test[Run tests]
        Test --> Build[Build]
    end

    subgraph QA
        Build --> DeployStaging[Deploy to staging]
        DeployStaging --> E2E[Run E2E tests]
        E2E --> Approval{Manual QA?}
    end

    subgraph Production
        Approval -->|Approved| DeployProd[Deploy to production]
        DeployProd --> Health{Health check?}
        Health -->|OK| Success([Deployment successful])
        Health -->|KO| Rollback[Rollback]
    end

    Approval -->|Rejected| Fix[Fix issues]
    Fix --> Development
    Test -->|Failed| Fix
```

## Common Patterns

### Branching Decision
```mermaid
flowchart TD
    A[Input] --> B{Condition?}
    B -->|True| C[Path 1]
    B -->|False| D[Path 2]
    C --> E[Merge]
    D --> E
```

### Loop Pattern
```mermaid
flowchart TD
    A[Initialize] --> B[Process]
    B --> C{Continue?}
    C -->|Yes| B
    C -->|No| D[Exit]
```

### Error Handling
```mermaid
flowchart TD
    A[Try operation] --> B{Success?}
    B -->|Yes| C[Continue]
    B -->|No| D[Handle error]
    D --> E{Retry?}
    E -->|Yes| A
    E -->|No| F[Abort]
```

## Best Practices

1. **Meaningful labels** -- Node text should be clear and action-oriented
2. **Consistent shapes** -- Same shapes for same types of actions
3. **Decision nodes as diamonds** -- Standard convention for yes/no decisions
4. **Flow top-to-bottom or left-to-right** -- Natural reading direction
5. **Start and end nodes** -- Use stadium shapes to mark entry/exit
6. **Group related steps** -- Use subgraphs for logical groupings
7. **Color code** -- Highlight different types of actions (see classDef above)
8. **Keep it focused** -- One process per diagram; split complex flows
