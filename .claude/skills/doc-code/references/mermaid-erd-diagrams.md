# Entity Relationship Diagrams (ERD)

ERDs model database schemas, showing tables (entities), their columns (attributes), and relationships between tables. Essential for database design and documentation.

## Basic Syntax

```mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
```

## Defining Entities

```mermaid
erDiagram
    CUSTOMER {
        int id PK
        string email UK
        string name
        string phone
        datetime created_at
    }
```

**Attribute format:** `type name constraints`

**Common constraints:**
- `PK` - Primary Key
- `FK` - Foreign Key
- `UK` - Unique Key
- `NN` - Not Null

## Relationship Symbols

**Cardinality indicators:**
- `||` - Exactly one
- `|o` - Zero or one
- `}{` - One or many
- `}o` - Zero or many

**Relationship line:**
- `--` - Non-identifying relationship
- `..` - Identifying relationship

### Common Relationships

```mermaid
erDiagram
    %% One-to-One
    USER ||--|| PROFILE : has

    %% One-to-Many
    CUSTOMER ||--o{ ORDER : places

    %% Many-to-Many (with junction table)
    STUDENT ||--o{ ENROLLMENT : has
    COURSE ||--o{ ENROLLMENT : includes

    %% Optional Relationships
    EMPLOYEE |o--o{ DEPARTMENT : manages
```

## Data Types

Standard database types:
- `int`, `bigint`, `smallint`
- `varchar`, `text`, `char`
- `decimal`, `float`, `double`
- `boolean`, `bool`
- `date`, `datetime`, `timestamp`
- `json`, `jsonb`
- `uuid`
- `blob`, `bytea`

## LIA-SEC CVE Core Schema

```mermaid
erDiagram
    cve_nvd_data ||--o{ cisa_kev : tracked_in
    cve_nvd_data ||--o{ exploit_db : exploited_by
    cve_nvd_data ||--o{ cve_attack_mapping : mapped_to
    cve_nvd_data ||--o{ apt_mitre_mapping : linked_via
    apt_groups_reference ||--o{ apt_mitre_mapping : performs
    mitre_techniques ||--o{ cve_attack_mapping : covers

    cve_nvd_data {
        varchar cve_id PK
        decimal cvss_score
        varchar severity
        text description
        jsonb cpe_matches
        decimal epss_score
        timestamp published_date
        timestamp updated_at
    }

    cisa_kev {
        varchar cve_id FK PK
        date date_added
        date due_date
        text required_action
        boolean ransomware_use
    }

    exploit_db {
        integer exploit_id PK
        varchar cve_id FK
        varchar type
        text description
        date published
    }

    apt_groups_reference {
        varchar mitre_id PK
        varchar name UK
        varchar country
        text description
        jsonb aliases
    }
```

## Comprehensive Example: E-Commerce Database

```mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE_ITEM : contains
    PRODUCT ||--o{ LINE_ITEM : "ordered in"
    PRODUCT }o--|| CATEGORY : "belongs to"
    ORDER ||--|| PAYMENT : "paid by"

    CUSTOMER {
        uuid id PK
        varchar email UK "NOT NULL"
        varchar name "NOT NULL"
        timestamp created_at "DEFAULT NOW()"
    }

    ORDER {
        uuid id PK
        uuid customer_id FK "NOT NULL"
        decimal total "NOT NULL"
        varchar status "NOT NULL"
        timestamp order_date "DEFAULT NOW()"
    }

    LINE_ITEM {
        uuid id PK
        uuid order_id FK "NOT NULL"
        uuid product_id FK "NOT NULL"
        int quantity "NOT NULL"
        decimal price_per_unit "NOT NULL"
    }

    PRODUCT {
        uuid id PK
        varchar sku UK "NOT NULL"
        varchar name "NOT NULL"
        decimal price "NOT NULL"
        uuid category_id FK
        boolean is_active "DEFAULT TRUE"
    }

    PAYMENT {
        uuid id PK
        uuid order_id FK "NOT NULL"
        varchar payment_method "NOT NULL"
        decimal amount "NOT NULL"
        varchar status "NOT NULL"
        varchar transaction_id UK
        timestamp processed_at
    }
```

## Common Patterns

### Self-Referencing (Hierarchical)
```mermaid
erDiagram
    CATEGORY ||--o{ CATEGORY : "parent of"

    CATEGORY {
        uuid id PK
        varchar name "NOT NULL"
        uuid parent_id FK "NULLABLE"
    }
```

### Junction Table (Many-to-Many)
```mermaid
erDiagram
    STUDENT ||--o{ ENROLLMENT : has
    COURSE ||--o{ ENROLLMENT : includes

    ENROLLMENT {
        uuid student_id FK PK
        uuid course_id FK PK
        date enrolled_date
        varchar grade
    }
```

### Audit Trail
```mermaid
erDiagram
    DOCUMENT ||--o{ DOCUMENT_VERSION : has

    DOCUMENT_VERSION {
        uuid id PK
        uuid document_id FK "NOT NULL"
        int version_number "NOT NULL"
        text content "NOT NULL"
        uuid modified_by FK
        timestamp created_at "DEFAULT NOW()"
    }
```

### Soft Deletes
```mermaid
erDiagram
    USER {
        uuid id PK
        varchar email UK
        varchar name
        timestamp deleted_at "NULLABLE"
    }
```

## Best Practices

1. **Name entities in UPPERCASE** -- Convention for clarity
2. **Use singular names** -- `USER` not `USERS`, `ORDER` not `ORDERS`
3. **Define all constraints** -- Document PKs, FKs, UKs, NOT NULL
4. **Show cardinality accurately** -- Be precise about one-to-many vs many-to-many
5. **Include timestamps** -- created_at, updated_at for auditing
6. **Document computed columns** -- Mark calculated/derived values
7. **Show indexes** -- Document UK (unique keys) beyond PKs
8. **Consider junction tables** -- Explicitly model many-to-many relationships

## LIA-SEC ERD Guidelines

- Always show `created_at` / `updated_at` for audit tables
- JSONB columns: use comment `"JSONB"` to clarify
- Migrations live in `cmd/sigma_web/migrations/NNN_*.sql` -- ERD must stay in sync
- Use the `db-schema-designer` skill for new schema design with migration generation
