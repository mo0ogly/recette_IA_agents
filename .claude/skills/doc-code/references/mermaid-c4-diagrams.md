# C4 Model Diagrams

The C4 model provides a hierarchical way to visualize software architecture at different levels of abstraction: Context, Containers, Components, and Code.

## C4 Model Levels

1. **System Context** (`C4Context`) -- Shows the system and its users/external systems
2. **Container** (`C4Container`) -- Shows applications, databases, and services within the system
3. **Component** (`C4Component`) -- Shows internal structure of containers
4. **Code** -- Use regular `classDiagram` for class-level details

## C4 Context Diagram

Shows the big picture: your system and its relationships with users and external systems.

```mermaid
C4Context
    title System Context - LIA-SEC Platform

    Person(rssi, "RSSI / Auditor", "Uses the platform to run security audits")
    Person(admin, "Admin", "Configures the platform")
    System(liasec, "LIA-SEC Platform", "Security audit and compliance platform")

    System_Ext(nvd, "NVD / CISA KEV", "CVE vulnerability data source")
    System_Ext(mitre, "MITRE ATT&CK", "Threat intelligence framework")
    System_Ext(groq, "Groq API", "Cloud LLM provider")
    SystemDb(postgres, "PostgreSQL 17", "332K CVEs, 268 tables")

    Rel(rssi, liasec, "Runs audits, views reports")
    Rel(admin, liasec, "Configures providers, variables")
    Rel(liasec, nvd, "Fetches CVE data", "HTTPS/REST")
    Rel(liasec, mitre, "Fetches ATT&CK data", "HTTPS/REST")
    Rel(liasec, groq, "AI generation", "HTTPS/REST")
    Rel(liasec, postgres, "Reads/writes", "SQL/TCP")
```

### Elements

**People:**
```
Person(id, "Label", "Description")
Person_Ext(id, "Label", "Description")   -- external user
```

**Systems:**
```
System(id, "Label", "Description")
System_Ext(id, "Label", "Description")  -- external system
SystemDb(id, "Label", "Description")    -- database system
SystemQueue(id, "Label", "Description") -- message queue
```

**Relationships:**
```
Rel(from, to, "Label")
Rel(from, to, "Label", "Technology")
BiRel(a, b, "Label")
```

## C4 Container Diagram

Zooms into the system to show containers (applications, databases, services).

```mermaid
C4Container
    title Container Diagram - LIA-SEC Platform

    Person(user, "Auditor / RSSI")
    System_Ext(liaprobe, "LiaProbe Agent", "Remote collector")

    Container_Boundary(liasec, "LIA-SEC Platform") {
        Container(frontend, "React Frontend", "React 19 / TypeScript", "314 components, SPA")
        Container(backend, "Go Backend", "Go 1.25, Gorilla Mux", "560+ REST routes, :8081")
        Container(engine, "LIA-Scan Engine", "Go binary", "Sigma rule evaluation")
        ContainerDb(db, "PostgreSQL 17", "PostgreSQL", "268 tables, 332K CVEs")
    }

    Container_Boundary(ai, "AI Stack") {
        Container(fallback, "FallbackEngine", "Go", "Provider rotation, RAG")
        Container(ollama, "Ollama", "Local", "Embeddings only (nomic-embed-text)")
        System_Ext(groq, "Groq API", "Cloud LLM provider")
    }

    Rel(user, frontend, "Uses", "HTTPS/443")
    Rel(liaprobe, backend, "Pushes results", "HTTPS/REST + X-Agent-Key")
    Rel(frontend, backend, "API calls", "HTTPS/JWT")
    Rel(backend, db, "Reads/writes", "SQL/TCP:5432")
    Rel(backend, engine, "Executes rules", "subprocess")
    Rel(backend, fallback, "AI calls", "internal")
    Rel(fallback, groq, "LLM generation", "HTTPS")
    Rel(fallback, ollama, "Embeddings", "HTTP:11434")
```

### Container Elements

```
Container(id, "Label", "Technology", "Description")
ContainerDb(id, "Label", "Technology", "Description")
ContainerQueue(id, "Label", "Technology", "Description")
Container_Ext(id, "Label", "Technology", "Description")
Container_Boundary(id, "Label") { ... }
```

## C4 Component Diagram

Zooms into a container to show its internal components.

```mermaid
C4Component
    title Component Diagram - Go Backend (AI subsystem)

    Container(frontend, "React Frontend", "React 19")
    ContainerDb(db, "PostgreSQL", "268 tables")
    System_Ext(groq, "Groq API")
    Container(ollama, "Ollama", "nomic-embed-text")

    Container_Boundary(backend, "Go Backend") {
        Component(router, "Gorilla Mux Router", "560+ routes", "Request routing")
        Component(rag, "ExecuteWithRAG()", "Go func", "RAG context injection + AI dispatch")
        Component(fallback, "FallbackEngine", "Go struct", "Provider rotation, health checks")
        Component(embedding, "OllamaEmbeddingService", "Go struct", "Vector embeddings only")
        Component(templates, "PromptTemplateManager", "Go struct", "PostgreSQL-backed prompts")
    }

    Rel(frontend, router, "REST calls", "HTTPS/JWT")
    Rel(router, rag, "AI handlers call")
    Rel(rag, templates, "Load prompts")
    Rel(rag, embedding, "Get query embedding")
    Rel(rag, fallback, "Execute with context")
    Rel(fallback, groq, "Generate text", "HTTPS")
    Rel(embedding, ollama, "Embed text", "HTTP:11434")
    Rel(templates, db, "Read ai_prompt_templates", "SQL")
```

### Component Elements

```
Component(id, "Label", "Technology", "Description")
```

## Common Architecture Patterns

### Monolithic Application
```mermaid
C4Container
    Person(user, "User")

    Container_Boundary(system, "Application") {
        Container(app, "Web Application", "Go + React", "Monolithic application")
        ContainerDb(db, "Database", "PostgreSQL", "Application database")
        ContainerDb(cache, "Cache", "Redis", "Session store")
    }

    Rel(user, app, "Uses", "HTTPS")
    Rel(app, db, "Reads/writes", "SQL")
    Rel(app, cache, "Caches", "Redis Protocol")
```

### Three-Tier Architecture
```mermaid
C4Container
    Person(user, "User")

    Container_Boundary(presentation, "Presentation Tier") {
        Container(frontend, "SPA", "React", "Client-side UI")
    }

    Container_Boundary(business, "Business Tier") {
        Container(api, "API Server", "Go", "Business logic + routing")
    }

    Container_Boundary(data, "Data Tier") {
        ContainerDb(db, "Database", "PostgreSQL", "Data storage")
    }

    Rel(user, frontend, "Uses", "HTTPS")
    Rel(frontend, api, "REST calls", "HTTPS/JWT")
    Rel(api, db, "Reads/writes", "SQL")
```

### Event-Driven Architecture
```mermaid
C4Container
    Container(api, "API Gateway", "Go", "Request routing")

    Container_Boundary(services, "Services") {
        Container(order, "Order Service", "Go", "Order processing")
        Container(inventory, "Inventory Service", "Go", "Stock management")
        Container(notification, "Notification Service", "Go", "Alerts")
    }

    ContainerQueue(events, "Event Bus", "n8n / RabbitMQ", "Async event streaming")
    ContainerDb(db, "Databases", "PostgreSQL", "Service databases")

    Rel(api, order, "Routes to")
    Rel(order, events, "Publishes OrderCreated")
    Rel(events, inventory, "Consumes events")
    Rel(events, notification, "Consumes events")
    Rel(order, db, "Persists")
```

## Best Practices

1. **Use appropriate level** -- Context for stakeholders, Container for architects, Component for developers
2. **Keep it focused** -- One system per Context diagram, one container per Component diagram
3. **Show key relationships** -- Don't clutter with every possible connection
4. **Add technology details** -- Specify frameworks, languages, protocols at Container/Component level
5. **Update regularly** -- Keep diagrams in sync with architecture changes (R20)
6. **Use boundaries** -- Group related containers/components logically
7. **Document protocols** -- Show communication methods (REST, gRPC, SQL, etc.)
8. **Highlight external systems** -- Use `*_Ext` variants for clarity
9. **Start simple** -- Begin with Context, drill down as needed
