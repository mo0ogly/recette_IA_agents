---
name: rag-architect
description: Designs and evolves the LIA-SEC RAG pipeline (pgvector + Ollama all-minilm + ExecuteWithRAG). Use when adding a new RAG source type, tuning chunking/retrieval, designing an enrichment campaign, debugging low recall, evaluating retrieval quality, or wiring a new AI feature to ExecuteWithRAG. Enforces R22 (ExecuteWithRAG canonical path), R5 (PostgreSQL = source of truth), R6 (LogSystemEvent only), and prompts in ai_prompt_templates.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/rag-architect
  version: "2.0.0-lia"
  domain: ai-rag
  triggers: rag-architect, rag pipeline, pgvector, ExecuteWithRAG, rag_documents, embedding, semantic search, knowledge base, hybrid search, reranking, retrieval optimization, rag enrichment campaign, rag evaluation, rag chunking, rag low recall, rag debug
  role: architect
  scope: system-design + integration
  output-format: design-doc + Go code + SQL migration
  related-skills: db-schema-designer, api-handoff, doc-code, golang-pro
  enforces-rules: R5, R6, R10, R12, R22
---

# RAG Architect (LIA-SEC adaptation)

> **Stack reel LIA-SEC** : Go 1.25 + PostgreSQL 17 + pgvector (HNSW) + Ollama local
> (`all-minilm` 384 dim) + `ExecuteWithRAG` middleware + FallbackEngine
> (Groq/Ollama/Claude/OpenAI) + prompts dans `ai_prompt_templates`.
>
> **Ne JAMAIS** introduire Qdrant, Pinecone, Weaviate, Chroma, langchain,
> OpenAI embeddings, ni langage Python pour ce sous-systeme. Tout passe par
> les composants Go listes ci-dessous.

---

## 0. Avant de coder -- lecture obligatoire (R22)

| Source de verite | Chemin | Pourquoi |
|------------------|--------|----------|
| Architecture AI complete | `cmd/sigma_web/AI_ARCHITECTURE.md` | Providers, fallback, prompts, RAG |
| Middleware RAG (signatures, latence, tiers) | `_alire/01_DOCUMENTATION/technical/rag_middleware_tech_en.md` | Source de verite ExecuteWithRAG |
| Admin RAG end-to-end (UI + campagnes + web search) | `_alire/01_DOCUMENTATION/architecture/ai_administration_arch_en.md` | Integration UI |
| Enrichissement LiaProbe RAG | `_alire/01_DOCUMENTATION/technical/liaprobe_rag_enrichment_tech_en.md` | Cas d'usage agent terrain |
| Regle R22 (one call pattern) | `.claude/rules/ai-call-pattern.md` | Bloquant pour merge |
| Regle R5 (PostgreSQL = source) | `.claude/CLAUDE.md` | Bloquant pour merge |
| Regle R6 (LogSystemEvent) | `.claude/CLAUDE.md` | Bloquant pour merge |
| Tables pgvector | `cmd/sigma_web/postgres/migrations/003_rag_vector_tables.sql` | Schema reel |

Si une de ces docs est absente ou contredit la realite -- arreter, lire le code
source (`cmd/sigma_web/ai_rag_middleware.go`, `ai_universal_provider.go`,
`ai_fallback_engine.go`, `rag_enrichment_campaign_api.go`,
`ollama_embedding_service.go`) et corriger la doc AVANT de coder (R18).

---

## 1. Workflow agentique (OBJECTIVE -> DESIGN -> INGEST -> VALIDATE -> LOOP)

```
[1] OBJECTIVE
    - Cas d'usage exact (CVE analysis, expert chat, audit insights, etc.)
    - source_type cible (existant ou nouveau ?)
    - Latence cible (Groq cloud ~3s, Ollama local ~30s+)
    - Volume attendu (documents, queries/jour)
    - Multi-tenant ? (filtre metadata.tenant_id obligatoire)

[2] RESEARCH (parallele)
    - Lire cmd/sigma_web/ai_rag_middleware.go : ExecuteWithRAG signature
    - Lire postgres/migrations/003_rag_vector_tables.sql : schema rag_documents
    - Lire AI_ARCHITECTURE.md : modes, fallback, RAG flow
    - Lire references/ : chunking, embedding, retrieval, eval, vector-db
    - Si nouveau source_type : grep existant pour pattern d'ingestion

[3] DESIGN
    - Chunking strategy (taille, overlap, separateurs domaine-specifique)
    - source_type + metadata.* obligatoires
    - RAGEnrichmentConfig (TopK, MinScore, MaxContextChars, EnableWebSearch)
    - Prompt template (categorie + langue) dans ai_prompt_templates
    - Mode tag pour routing FallbackEngine (ai_fallback_engine.go > rules)

[4] INGEST (Go uniquement, jamais Python)
    - Source ingestion via rag_enrichment_campaign_api.go OU module dedie
    - Embedding via ollamaEmbeddingService.GenerateEmbedding(text)
    - INSERT INTO rag_documents avec deterministic id (SHA-256 du content)
    - LogSystemEvent("INFO", "RAG_INGEST", "INSERTED", ...) sur chaque batch

[5] VALIDATE (recette bloquante)
    - precision@5 >= 0.7 sur jeu de test domain-specifique
    - recall@5 >= 0.6
    - Latence p95 < 4.5s (sans web search) / < 6s (avec)
    - rag_context_used == true sur >= 80% des appels representatifs
    - Aucune regression sur les 22 sites RAG existants
    - Test render-and-assert R17 si composant frontend impacte

[6] LOOP -> retour [3] si KO, sinon COMPLETE + RETEX + Librarian Gate
```

---

## 2. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| Vector databases (pgvector deep dive) | `references/vector-databases.md` | Choisir HNSW vs IVFFlat, sharding, partitioning, tuning HNSW (m, ef_construction) |
| Embedding models | `references/embedding-models.md` | Justifier `all-minilm` (384) vs autres, plan migration multilingue, benchmarks domaine |
| Chunking strategies | `references/chunking-strategies.md` | Decoupage CVE/sigma_rule/documentation, semantic chunking, overlap, metadata enrichment |
| Retrieval optimization | `references/retrieval-optimization.md` | Hybrid search (vector + BM25), reranking, query expansion, filters multi-tenant |
| RAG evaluation | `references/rag-evaluation.md` | Metriques precision@k/recall@k/MRR/NDCG, RAGAS, debug retrieval, ground-truth set |

> **Note** : ces references viennent de l'upstream Jeffallan/claude-skills et
> contiennent du Python/Qdrant/Pinecone illustratif. **Ne pas copier-coller**
> ce code dans LIA-SEC. Utiliser uniquement les principes (chunk size,
> recall metric, reranking strategy) et les transposer en Go via les
> helpers existants ci-dessous.

---

## 3. Stack reel -- composants a utiliser

### 3.1 Schema PostgreSQL (existant)

```sql
-- cmd/sigma_web/postgres/migrations/003_rag_vector_tables.sql
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS rag_documents (
    id           TEXT PRIMARY KEY,            -- deterministic (sha256 du content)
    content      TEXT NOT NULL,
    embedding    vector(384),                 -- Ollama all-minilm
    source       TEXT NOT NULL,               -- file path / rule id / cve id
    source_type  TEXT NOT NULL,               -- whitelist (voir 3.2)
    chunk_index  INTEGER DEFAULT 0,
    parent_id    TEXT,
    metadata     JSONB DEFAULT '{}',          -- tenant_id, tags, version, etc.
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rag_documents_embedding
    ON rag_documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_rag_documents_source      ON rag_documents(source);
CREATE INDEX idx_rag_documents_source_type ON rag_documents(source_type);
CREATE INDEX idx_rag_documents_parent      ON rag_documents(parent_id);
CREATE INDEX idx_rag_documents_created     ON rag_documents(created_at DESC);
```

### 3.2 source_type whitelist (NE JAMAIS inventer un nouveau type sans migration)

`knowledge_base`, `sigma_rule`, `cve`, `documentation`, `user_document`,
`cve_rule` (catalogue migration 004).

Pour ajouter un type, creer une migration `cmd/sigma_web/postgres/migrations/NNN_rag_<type>.sql`
qui documente le source_type, ses metadata.* obligatoires, et les
SourceTypes a passer dans `RAGEnrichmentConfig`.

### 3.3 Embedding -- helper unique

```go
// ollama_embedding_service.go
embedding, err := ollamaEmbeddingService.GenerateEmbedding(text)
// 384 dims, all-minilm, fallback word-frequency si Ollama down
// Cache SHA-256 sur queries repetees (~0ms hit)
```

INTERDIT : appeler Ollama directement, OpenAI embeddings, sentence-transformers
en Python. Toujours passer par le service.

### 3.4 ExecuteWithRAG -- the ONE call pattern (R22)

```go
import (
    // ai_rag_middleware.go
)

ragConfig := RAGEnrichmentConfig{
    Query:               "human-readable search query",
    SourceTypes:         []string{"cve", "sigma_rule"}, // [] = all
    TopK:                5,
    MinScore:            0.3,
    MaxContextChars:     3000,
    EnableWebSearch:     false, // opt-in, voir 3.6
    WebSearchMaxResults: 3,
}

// 1. Charger prompt depuis PostgreSQL (R5 + R22)
systemMsg, userTemplate, temperature, maxTokens :=
    GetPromptTemplateWithFallback("myfeature_summary", resolveAILang(req.Language))

// 2. Substitutions
userPrompt := strings.ReplaceAll(userTemplate, "{cve_id}", cveID)

// 3. Appel canonique (RAG + FallbackEngine + sanitize)
result := ExecuteWithRAG(systemMsg, userPrompt, "myfeature_mode",
    temperature, maxTokens, ragConfig)

// 4. Parsing defensif + fallback deterministe
success, _ := result["success"].(bool)
if !success {
    LogSystemEvent("WARN", "MYFEATURE", "AI_CALL_FAILED",
        fmt.Sprintf("%v", result["error"]))
    return deterministicFallback()
}
response, _   := result["response"].(string)
provider, _   := result["provider"].(string)
ragUsed, _    := result["rag_context_used"].(bool)
ragDocs, _    := result["rag_docs_count"].(int)
retrievalMs, _:= result["rag_retrieval_ms"].(int64)
```

### 3.5 system_variables -- flags admin (R5)

| Cle | Defaut | Effet |
|-----|--------|-------|
| `RAG_ENRICHMENT_ENABLED` | `true` | Toggle global enrichissement |
| `RAG_WEB_SEARCH_ENABLED` | `false` | Toggle global web search |
| `WEB_SEARCH_PROVIDER` | `brave` | brave / serper / searxng |
| `WEB_SEARCH_API_KEY` | (vide) | Brave / Serper |
| `WEB_SEARCH_URL` | (vide) | Self-hosted |
| `SEARXNG_URL` | `http://searxng:8888` | SearXNG instance |
| `LIA_DEFAULT_LANGUAGE` | `en` | Langue defaut sortie IA (R22) |

Lire/ecrire via `system_variables` -- jamais hardcoder dans le Go.

### 3.6 Enrichment campaigns -- pattern d'ingestion themed

`cmd/sigma_web/rag_enrichment_campaign_api.go` (7 endpoints
`/api/rag/enrichment/campaigns*`). Pattern type :

```
1. Admin definit topic + keywords -> 6 queries auto-generees
2. Run async :
   for q in queries:
     a. WebSearchService.Search(q, n)              -> []RAGWebSearchResult
     b. WebSearchService.FetchContent(url)         -> texte (HTML strip, 10K cap)
     c. ollamaEmbeddingService.GenerateEmbedding(content)
     d. INSERT INTO rag_documents (id=sha256, source_type, metadata)
3. LogSystemEvent("INFO", "RAG_CAMPAIGN", "INDEXED", ...) per chunk
```

Reutiliser ce pattern pour toute ingestion massive (CVE corpus, sigma rules,
vendor advisories, etc.).

---

## 4. Anti-patterns interdits (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| `manager.CallAI(prompt)` | `ExecuteWithRAG(...)` (bypass FallbackEngine + RAG) |
| `callGrcAI(prompt)` dans nouveau code | `ExecuteWithRAG(...)` |
| Provider hardcode (`"groq"`, `BaseURL: "https://api.groq.com/..."`) | Lire `ai_providers` PostgreSQL |
| Prompt hardcode dans le Go | `ai_prompt_templates` + `GetPromptTemplateWithFallback` |
| Embedding via OpenAI / sentence-transformers Python | `ollamaEmbeddingService.GenerateEmbedding` |
| Qdrant / Pinecone / Weaviate / Chroma | `pgvector` + `rag_documents` |
| `chunk_size = 512` par defaut sans evaluation | Mesurer sur jeu domaine, justifier dans PR |
| Insertion sans deterministic id | `id = sha256(content + source)` (idempotent) |
| Insertion sans `source_type` ou `metadata.tenant_id` (multi-tenant) | Whitelist + validation prealable |
| `lang = "fr"` ou `"en"` hardcode | `resolveAILang(req.Language)` (R22 -> system_variables) |
| `fmt.Println` / `log.Printf` pour les events ingest | `LogSystemEvent("INFO", "RAG_INGEST", ...)` (R6) |
| Suppression d'un fichier RAG sans archive | Archiver `mv ... archive/` (R15 + project NO DELETION) |

---

## 5. Recette obligatoire avant merge

```
[1] STATIC
    [ ] /go-recette sur les fichiers touches (gosec + govulncheck + R17)
    [ ] Migration SQL ajoutee si nouveau source_type ou colonne
    [ ] Prompt template ajoute dans migration cmd/sigma_web/migrations/0NN_*_prompts.sql

[2] BUILD (R3 + cmd/sigma_web/CLAUDE.md)
    [ ] Nouveaux .go ajoutes dans build_secure_lia.sh
    [ ] ./build_secure_lia.sh OK
    [ ] RegisterXxxRoutes(r) ajoute dans backend_8081.go si nouveaux endpoints

[3] RUNTIME
    [ ] curl /api/rag/enrichment/settings -> 200
    [ ] curl /api/<my-feature> -> reponse contient rag_context_used + rag_docs_count
    [ ] Verifier dans unified_logs : 0 ERROR sur RAG_*, AI_*, FALLBACK_*

[4] CONTRACT (R17)
    [ ] Si frontend appelle l'endpoint : fixture reelle + render-and-assert
    [ ] Reponse AI rendue via <AIMarkdownView /> (jamais <Typography>raw</Typography>)
    [ ] resolveAILang utilisee (jamais hardcode lang)

[5] EVAL (jeu de test domain-specifique)
    [ ] precision@5 >= 0.7
    [ ] recall@5 >= 0.6
    [ ] p95 latence < 4.5s (no web) / < 6s (with web)
    [ ] zero regression sur sites RAG existants
```

Toute case [ ] non cochee -> cycle PDCA/APEX REOPEN, pas de merge.

---

## 6. Documentation obligatoire (R20 + R15)

Apres tout changement RAG :

1. Mettre a jour `_alire/01_DOCUMENTATION/technical/rag_middleware_tech_en.md`
   (signatures, source_types, metriques)
2. Mettre a jour `_alire/01_DOCUMENTATION/architecture/ai_administration_arch_en.md`
   (admin UI, campagnes)
3. Si nouveau composant frontend : `/create-ui-help` pour le HelpButton (R8)
4. `python3 .claude/skills/doc-code/scripts/doc_classifier.py bump <file>`
5. `python3 .claude/skills/doc-code/scripts/doc_librarian.py reindex _alire/01_DOCUMENTATION/`
6. Plan dans `_alire/tracking/PLAN_RAG_*_YYYY-MM-DD.md` (Librarian Gate)

---

## 7. Triggers automatiques

Cette skill DOIT etre invoquee quand :

- Ajout d'un nouveau source_type RAG
- Ajout d'une nouvelle source de donnees a ingerer (corpus CVE, sigma rules, doc vendor)
- Tuning HNSW (m, ef_construction) ou MinScore / TopK
- Changement de modele d'embedding (impact migration `vector(N)`)
- Debug "rag_context_used=false" sur un endpoint qui devrait l'utiliser
- Plainte utilisateur "l'IA ne sait pas X" / "le contexte est mauvais"
- Ajout d'un nouveau provider de web search (Brave/Serper/SearXNG)
- Audit recall/precision avant cycle PDCA AI

Triggers conversationnels : `rag-architect`, `concois la pipeline rag`,
`audite le rag`, `pourquoi le rag ne trouve pas`, `nouvelle source rag`,
`tune les chunks`, `ameliore la retrieval`, `evalue le rag`.

---

## 8. Output template (livrable d'une session rag-architect)

```markdown
# RAG Design : <feature> -- YYYY-MM-DD

## 1. Objectif et contraintes
- Cas d'usage : ...
- source_type : ... (existant | NEW migration NNN)
- Latence cible : ...
- Volume : ... docs ingerés / ... queries/jour
- Multi-tenant : oui (metadata.tenant_id) | non

## 2. Decisions
- Chunking : taille=N, overlap=M, separateurs=[...]   (justifie mesure jeu)
- TopK / MinScore / MaxContextChars : ...
- SourceTypes : [...]
- Web search : enabled | disabled (raison)
- Mode tag : "<feature>_mode" (route FallbackEngine)
- Prompt templates : categories ajoutees dans migration NNN

## 3. Schema delta
- (Migration SQL si nouveau source_type / colonne metadata)

## 4. Code
- Fichiers touches (Go) : ...
- Fichiers ajoutes : ...
- ExecuteWithRAG call sites : ...

## 5. Recette
- precision@5 = ... / recall@5 = ... / MRR = ...
- p95 latence = ...
- Captures : screenshots avant/apres

## 6. Evolutions possibles
- Quick win : ...
- Moyen : ...
- Long terme : migration embedding multilingue ?

## 7. Cross-references
- R22 ai-call-pattern.md : checklist passee
- R20 doc-after-code.md : doc rag_middleware_tech_en.md mise a jour v1.x
- Plan _alire/tracking/PLAN_RAG_<feature>_YYYY-MM-DD.md
```

---

## 9. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | 5+ sous-taches alignees sur le workflow section 1 |
| C2 Planification (THINK) | 9/10 | 2+ alternatives evaluees (chunking, hybrid vs vector pur, etc.) |
| C3 Replanification | 8/10 | REPLAN sur metrique recette KO + 2+ alternatives |
| C4 Outillage | 8/10 | grep / Read sur ai_rag_middleware.go AVANT design |
| C5 Tracabilite | 8/10 | PLAN_RAG_*.md + RETEX + decision_log.jsonl + Librarian Gate |
