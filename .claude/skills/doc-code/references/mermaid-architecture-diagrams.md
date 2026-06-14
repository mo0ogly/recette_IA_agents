# Architecture Diagrams Reference (`architecture-beta`)

Architecture diagrams visualize cloud services, CI/CD deployments, and infrastructure relationships. Introduced in Mermaid v11.1.0.

## Basic Syntax

```mermaid
architecture-beta
    group public_api(cloud)[Public API]
    service api1(server)[API Server] in public_api
    service db(database)[Database]

    api1:R --> L:db
```

## Building Blocks

### Groups

Group related services together:

```
group {groupId}({icon})[{title}] (in {parentId})?
```

```mermaid
architecture-beta
    group internet(cloud)[Internet]
    group private_vpc(cloud)[Private VPC] in internet
```

### Services

Declare services (nodes):

```
service {serviceId}({icon})[{title}] (in {parentId})?
```

**Default icons:** `cloud`, `database`, `disk`, `internet`, `server`

```mermaid
architecture-beta
    service api(server)[API Server]
    service db(database)[Database]
    service cache(disk)[Cache]
```

### Edges

Connect services with edges:

```
{serviceId}:{T|B|L|R} {<}?--{>}? {T|B|L|R}:{serviceId}
```

**Directions:** `T` (top), `B` (bottom), `L` (left), `R` (right)
**Arrows:** `<` incoming, `>` outgoing, `<-->` bidirectional

```mermaid
architecture-beta
    service client(internet)[Client]
    service api(server)[API]
    service db(database)[Database]

    client:B --> T:api
    api:R --> L:db
```

### Junctions

Create 4-way splits:

```mermaid
architecture-beta
    service input(server)[Input]
    service out1(server)[Output 1]
    service out2(server)[Output 2]

    junction j1

    input:R --> L:j1
    j1:T --> B:out1
    j1:B --> T:out2
```

## Icons

**Custom icons via @iconify-json:**
```bash
npm install @iconify-json/logos @mermaid-js/mermaid-cli
mmdc --iconPacks @iconify-json/logos -i diagram.mmd -o output.svg
```

| Icon Pack | Description | Install |
|-----------|-------------|---------|
| `@iconify-json/logos` | Tech brands (Docker, AWS, GitHub...) | `npm i @iconify-json/logos` |
| `@iconify-json/mdi` | Material Design icons | `npm i @iconify-json/mdi` |
| `@iconify-json/bi` | Bootstrap icons | `npm i @iconify-json/bi` |

Usage: `pack:icon-name` (e.g., `logos:docker`, `mdi:database`)

```mermaid
architecture-beta
    service web(logos:docker)[Docker Container]
    service k8s(logos:kubernetes)[Kubernetes]
    service aws(logos:aws)[AWS Services]

    web:R --> L:k8s
    k8s:R --> L:aws
```

## LIA-SEC VPS Architecture

```mermaid
architecture-beta
    group internet(cloud)[Internet]
    group vps(server)[VPS inspect-ia-agents.tech :443]
    group dev_env(disk)[Dev Mirror /opt/lia-sec/dev/]

    service browser(internet)[Browser] in internet
    service nginx(server)[Nginx :443] in vps
    service frontend(disk)[React Build] in vps
    service backend(server)[Go Backend :8081] in vps
    service postgres(database)[PostgreSQL :5432] in vps
    service n8n(server)[n8n :5678] in vps

    service dev_cc(server)[Claude Code Dev] in dev_env
    service dev_back(server)[Dev Backend :8081] in dev_env

    browser:R --> L:nginx
    nginx:R --> L:frontend
    nginx:R --> L:backend
    backend:B --> T:postgres
    n8n:B --> T:postgres
    dev_back:B --> T:postgres
```

## Complex Infrastructure Example

```mermaid
architecture-beta
    group internet(cloud)[Internet]
    group private_vpc(cloud)[Private VPC]

    service lb(server)[Load Balancer] in internet
    service api1(server)[API Server 1] in private_vpc
    service api2(server)[API Server 2] in private_vpc
    service db(database)[Primary Database] in private_vpc
    service replica(database)[Read Replica] in private_vpc
    service cache(disk)[Redis Cache] in private_vpc

    lb:R --> L:api1
    lb:R --> L:api2
    api1:R --> L:db
    api2:R --> L:db
    db:R --> L:replica
    api1:B --> T:cache
    api2:B --> T:cache
```

## Edge Patterns Reference

| Pattern | Description |
|---------|-------------|
| `A:R -- L:B` | Horizontal edge (no arrow) |
| `A:T -- B:B` | Vertical edge |
| `A:R --> L:B` | Edge with arrow |
| `A:R <--> L:B` | Bidirectional edge |
| `A{group}:R --> L:B` | Edge from group boundary |

## Group Edges

Connect groups using the `{group}` modifier:

```mermaid
architecture-beta
    group frontend(cloud)[Frontend]
    group backend(cloud)[Backend]

    service client(internet)[Client] in frontend
    service api(server)[API] in backend

    client{group}:B --> T:api{group}
```

## Best Practices

1. Group services by environment (public/private) or layer (frontend/backend/data)
2. Use consistent icons for service types across diagrams
3. Label edges with protocols (HTTPS, TCP, SQL, etc.)
4. Use junctions for fan-out patterns (load balancer -> multiple backends)
5. Keep diagrams focused; split complex architectures into multiple views
6. Prefer `architecture-beta` for cloud/infra, `C4Container` for software architecture
