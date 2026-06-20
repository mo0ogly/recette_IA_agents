# Registre des agents + catalogue -- runbook

> Deux registres en lecture seule decrivent la population d'agents du systeme. Le
> **registre genere** (`GET /registry/agents`) est une projection DERIVEE des
> manifests du corpus -- jamais ecrite a la main -- une ligne par sujet. Le
> **catalogue declaratif** (`GET /catalog/summary`) lit un fichier de registre
> publie et n'en expose que des proprietes INVARIANTES de discovery (comptes,
> noms distincts, couverture d'outils, union de tags), avec un moteur Rust natif
> en accord croise.
>
> Code Python : `recette/registry.py` (pur), `recette/api/routers/registry.py`,
> `recette/api/routers/catalog_registry.py`, `recette/catalog_sync.py`.
> Moteur Rust : `discoveryprobe/discoveryprobe-catalog/`.
> Console : `console/src/pages/agent-registry/` et `console/src/pages/registry/`.

## Pourquoi ce sous-systeme existe

La recette doit pouvoir presenter, sans effet de bord ni recalcul opaque, "qui
sont les agents" sous deux angles complementaires :

1. **Registre genere** -- un agregat de TOUS les sujets du corpus (agents git +
   sujets MAF), construit a la demande a partir des manifests. C'est le concept
   auto-registry-on-merge (style microsoft/discovery) : le registre est une
   fonction des manifests, jamais un fichier maintenu a la main qui pourrait
   diverger.
2. **Catalogue declaratif** -- l'index machine-lisible qu'une source de discovery
   publie (`version` + `entries`). Le catalogue ne montre que des invariants (R20
   : la verite-terrain de discovery est invariant-only, jamais un score exact),
   afin de servir de banc d'essai aux outils de discovery externes.

Les deux sont en **lecture seule** cote API et cote console.

## Registre genere -- ce qu'il fait

### Construction (derivee, pure)

`recette/api/routers/registry.py::build_agent_registry()` scanne deux familles de
repertoires de sujets et produit une ligne par manifest :

- `discover_agent_dirs()` (`recette/harness.py`) -> chaque `manifest.json` d'agent
  git, famille `"git"`.
- `discover_maf_dirs()` (`recette/maf_harness.py`) -> chaque `spec.json` de sujet
  MAF, famille `"maf"`.

Chaque ligne est produite par la fonction pure `registry_row(manifest, family)`
(`recette/registry.py`). Une ligne porte exactement ces champs :

| Champ | Source dans le manifest | Comportement si absent |
|-------|-------------------------|------------------------|
| `agent_id` | `agent_id` | `None` |
| `name` | `name` | `None` |
| `kind` | `kind` | defaut `"git_agent"` |
| `family` | (parametre `git` / `maf`) | -- |
| `version` | `version` | `None` |
| `target_systems` | `target_systems` | `[]` |
| `capabilities` | `len(capability_scope)` | `0` |
| `standard` | `source.standard` | `None` |
| `publisher` | `metadata.publisher.name` | `None` |
| `compliance` | `metadata.compliance` | `[]` |
| `party` | `metadata.party` | `None` |
| `tags` | `metadata.tags` | `[]` |

Les champs de metadonnees optionnels sont remontes en `None` / `[]` quand ils
sont absents -- **jamais inventes** (R4). Les lignes sont triees par `agent_id`.

### Sortie de l'endpoint

`GET /registry/agents` renvoie :

```json
{ "generated": true, "count": <int>, "agents": [ <registry_row>, ... ] }
```

### Page console

Route `/agent-registry` (libelle de navigation **Registry**),
`console/src/pages/agent-registry/index.tsx`, via `getAgentRegistry()`
(`console/src/api/client.ts`, `GET /registry/agents`). La page affiche un tableau
(`agent`, `kind`, `version`, `party`, `compliance`, `publisher`, `tags`) avec un
filtre **Party** (`all` / `1p` / `3p`). Aide : topic `agent_registry`
(`console/src/components/help/helpTopics.tsx`).

## Catalogue declaratif -- ce qu'il fait

### Source et projection invariante

`recette/api/routers/catalog_registry.py` lit un fichier de registre JSON local
(par defaut `corpus/catalog/agent-registry.json`, surchargeable par
`INSPECT_IA_AGENTS_CATALOG_REGISTRY`) et le PROJETTE via `_project()` sur une vue
strictement invariante :

```json
{
  "version": "<str>",
  "summary": { "total": <int>, "unique": <int>, "with_tools": <int>, "tags": [<str>...] },
  "agents": [ { "name", "version", "publisher_name", "description", "tags", "tool_count" } ]
}
```

- `total` = nombre d'entrees, `unique` = noms distincts, `with_tools` = entrees
  dont `len(associated_tools) + len(foundry_tools) > 0`, `tags` = union triee et
  dedupliquee.
- La projection est une **fonction pure** du JSON (tags tries + dedupliques,
  agents dans l'ordre du registre) : meme registre -> resume byte-stable (I4). Le
  champ `generated_at` est de la metadonnee operationnelle et n'entre jamais dans
  la projection.
- Aucune valeur opaque n'est exposee (R20).

Endpoint : `GET /catalog/summary`.

### Moteur Rust natif et accord croise

`GET /catalog/rust-summary` execute le binaire compile
`discoveryprobe/target/release/discoveryprobe-catalog` (surchargeable par
`INSPECT_IA_AGENTS_CATALOG_RUST_BIN`) sur le meme fichier de registre, sans shell,
avec des arguments fixes issus de la configuration -- jamais d'entree de requete
(`subprocess.run([str(binary), str(registry)], timeout=10)`). Sortie :

```json
{ "available": <bool>, "engine": "discoveryprobe-catalog (Rust)",
  "summary": {...}?, "reason": "<str>"?, "agreement": <bool>?, "python_summary": {...}? }
```

`agreement` vaut `true` ssi le resume invariant Rust est egal a la projection
Python : c'est la garantie d'accord croise entre les deux moteurs (le Rust
`DiscoverySummary` et la projection Python partagent les memes invariants).

Le binaire se construit par `cargo build --release -p discoveryprobe-catalog` ;
en CLI il s'utilise `discoveryprobe-catalog <registry.json>` (imprime le resume
invariant).

### Page console

Route `/registry` (libelle de navigation **Catalogue**),
`console/src/pages/registry/index.tsx`, via `getCatalogSummary()` et
`getCatalogRustSummary()`. La page affiche les compteurs (Agents / Uniques / Avec
outils / Tags), l'union de tags, une carte par agent (`RegistryAgentCard.tsx`, un
agent sans outil est affiche distinctement, jamais masque) et un panneau du
moteur Rust avec un voyant `accord Rust == Python` / `DESACCORD Rust/Python`, ou
`binaire non compile` si le moteur est absent.

## Rafraichir le catalogue (la seule operation reseau)

L'API du catalogue lit un fichier LOCAL pour rester deterministe et hors-ligne
(I4 / R20). La synchronisation est une etape explicite, pilotee par l'operateur,
fournie par `recette/catalog_sync.py` :

```
python -m recette.catalog_sync
```

- Source : `INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL` (schemes autorises :
  `http`, `https`, `file`). Jamais d'URL en dur (R5). Un `file://` rend la sync
  exercable sans reseau.
- Destination : `INSPECT_IA_AGENTS_CATALOG_REGISTRY` ou par defaut
  `corpus/catalog/agent-registry.json`.
- La source doit etre un objet JSON portant un tableau `entries`, sinon le
  fichier local est laisse intact et `CatalogSyncError` est levee.

## Flux

```mermaid
flowchart TD
  subgraph Registre_genere
    M1["Manifests corpus<br/>(agents git + sujets MAF)"] -->|discover_agent_dirs / discover_maf_dirs| RB["build_agent_registry()<br/>registry_row (pur)"]
    RB --> RA["GET /registry/agents<br/>{generated, count, agents}"]
    RA --> UI1["Console /agent-registry<br/>(libelle Registry)"]
  end
  subgraph Catalogue_declaratif
    SRC["Source distante<br/>(http/https/file)"] -->|python -m recette.catalog_sync| FILE["corpus/catalog/agent-registry.json<br/>(fichier local)"]
    FILE -->|_project (pur)| CS["GET /catalog/summary<br/>resume invariant"]
    FILE -->|discoveryprobe-catalog| CR["GET /catalog/rust-summary<br/>+ accord croise"]
    CS --> UI2["Console /registry<br/>(libelle Catalogue)"]
    CR --> UI2
  end
```

## Comportements fail-safe

- **Catalogue absent / illisible / malforme** : `_load_catalog()` retourne un
  catalogue VIDE (`version ""`, resume a zero, agents `[]`) avec un avertissement
  journalise -- jamais une 500.
- **Moteur Rust non compile / en erreur / timeout / sortie non-JSON** :
  `GET /catalog/rust-summary` renvoie `available: false` avec une `reason` --
  jamais une 500, jamais un resultat fabrique. La page laisse le panneau Rust en
  etat indisponible.
- **Sync invalide** (source absente, scheme non supporte, source injoignable,
  payload non conforme) : `CatalogSyncError` levee et journalisee ; le bon fichier
  local n'est jamais ecrase par un registre partiel ou corrompu.
- **Metadonnees de registre absentes** : remontees en `None` / `[]` (registre
  genere) ou champ vide (`—` cote UI) -- jamais inventees.

## Invariants

- **I1 (immutabilite)** -- les deux registres sont en lecture seule ; aucun
  UPDATE/DELETE n'est implique. Le registre genere est une projection derivee,
  reconstructible des manifests (jetable).
- **I4 (replay deterministe)** -- `registry_row` et `_project` sont des fonctions
  pures (tri par `agent_id`, tags tries + dedupliques) : meme entree -> sortie
  byte-stable. Le moteur Rust calcule les memes invariants (accord croise). La
  seule operation reseau (sync) est sortie du chemin de requete.
- **R20 (ground-truth invariant)** -- le catalogue n'expose que des proprietes
  invariantes (comptes, noms distincts, couverture d'outils, union de tags),
  jamais de valeur opaque ni de score exact.

## Verifications rapides

```
curl -s http://127.0.0.1:8090/registry/agents | head
curl -s http://127.0.0.1:8090/catalog/summary | head
curl -s http://127.0.0.1:8090/catalog/rust-summary | head
```

L'API se lance via `./recette.sh platform up` (port canonique 8090, R19). Tests
de reference : `tests/test_api_registry.py`, `tests/test_api_catalog_summary.py`,
`tests/test_api_catalog_rust.py`, `tests/test_catalog_sync.py`.

## Voir aussi

- `docs/runbooks/github-discovery-recette.md` -- la recette de discovery.
- `.claude/rules/recette-corpus.md` -- les trois formes d'un agent, discovery vs
  identification, ground-truth invariant.
- `.claude/rules/maf-standard.md` -- les sujets MAF agreges dans le registre genere.
