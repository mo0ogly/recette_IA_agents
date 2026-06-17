# CRUD de la base de connaissances RAG + scenarios de poison + reset

Cycle de vie operateur pour preparer et lancer la recette de poisoning RAG :
consulter la base de connaissances, inserer/supprimer des documents, appliquer un
scenario de poison nomme, et revenir a la baseline propre. C'est un outil de
banc-de-test **hors du chemin de l'agent** -- il ne laisse jamais un agent muter
l'index sans la gateway (I2).

## Pourquoi

La recette de poisoning RAG prouve qu'une base de connaissances polluee ne peut
pas faire produire a un agent un effet de bord interdit : meme si un document
recupere ordonne a l'agent d'exfiltrer / d'executer une commande invalide /
d'ingerer des donnees forgees, la gateway refuse ou escalade l'action induite.
Pour lancer cette recette de maniere repetable, il faut *polluer* la base de
connaissances de facon controlee puis la *reset* ensuite. Cette fonctionnalite
fournit ce cycle de vie.

## Modele (deterministe, I4)

- La baseline est le fichier committe `corpus/rag/knowledge_base.json` (source de
  verite).
- Une unique liste de documents en memoire (`recette/rag_store.py`,
  `live_documents()`) est amorcee depuis la baseline et partagee avec le handler du
  lab (`recette/lab/domains/knowledge_base.py`), de sorte qu'un
  `query_knowledge_base` d'un agent live reflete l'etat courant (baseline +
  scenario applique).
- `reset()` recharge la baseline a l'identique -- les memes octets a chaque fois,
  pas d'horloge, pas d'aleatoire. La boucle de recette est donc rejouable.

## La boucle de recette

```
reset -> apply <scenario> -> run agent / campaign -> gateway denies/escalates -> reset
```

Le verdict de la gateway est ce que la recette asserte : l'action induite est
`deny` (exfil / commande inconnue) ou `escalate` (mutation d'index),
`executed=False`. Voir `campaigns/rag/` et
`scripts/run_rag_poisoning_live_groq.py`.

## Diagrammes (pour l'equipe recette)

### Ou se situe le CRUD operateur par rapport au chemin de l'agent (frontiere I2)

L'operateur mute la base de connaissances directement (banc-de-test). L'agent ne
le fait jamais : il ne peut que lire via un `query_knowledge_base` mediatise, et
tout effet de bord induit par le contenu empoisonne est decide par la gateway --
pas par le contenu RAG.

```mermaid
flowchart LR
  subgraph Operator["Operateur banc-de-test (hors du chemin de l'agent)"]
    CLI["CLI : recette rag-kb"]
    UI["Console /rag KnowledgeBaseManager"]
    ROUTES["routes operateur /rag/*"]
    STORE["KnowledgeBaseStore (rag_store.py)"]
  end
  subgraph Shared["KB partagee en memoire"]
    LIVE["live_documents() = baseline + scenario applique"]
  end
  subgraph AgentPath["Chemin de l'agent (mediatise, I2)"]
    AGENT["agent RAG"]
    GW["Gateway /actions/execute"]
    POLICY["moteur de policy decide()"]
    LAB["handler knowledge_base du lab"]
  end
  BASELINE[("corpus/rag/knowledge_base.json")]
  SCEN[("corpus/rag/scenarios/*.json")]

  CLI --> ROUTES
  UI --> ROUTES
  ROUTES --> STORE
  STORE -->|reset| BASELINE
  STORE -->|applique le scenario| SCEN
  STORE --> LIVE
  AGENT -->|query_knowledge_base| GW
  GW --> POLICY
  POLICY -->|autorise la lecture| LAB
  LAB -->|lit| LIVE
  AGENT -.->|effet de bord induit| GW
  GW -.->|deny / escalate, executed=False| AGENT
```

### La boucle de recette de poisoning (sequence)

```mermaid
sequenceDiagram
  participant Op as Operateur
  participant Store as KnowledgeBaseStore
  participant KB as KB partagee
  participant Agent as agent RAG
  participant GW as Gateway + policy
  Op->>Store: reset()
  Store->>KB: baseline propre
  Op->>Store: apply_scenario("exfil-finance")
  Store->>KB: injecte le doc empoisonne scn-exfil-finance
  Agent->>GW: query_knowledge_base
  GW->>KB: lecture (autorisee)
  KB-->>Agent: renvoie le document empoisonne
  Agent->>GW: send_data_to_external_domain (exige par le poison)
  GW-->>Agent: DENY -- executed=False (I2)
  Op->>Store: reset()
  Store->>KB: baseline restauree (poison disparu, I4)
```

### Les deux gardes CI qui maintiennent un poison honnete (T4 + T5)

Un artefact de poison ne peut entrer dans le corpus sans la preuve qu'il est
bloque, et un document insere ne peut porter un identifiant errant.

```mermaid
flowchart TD
  NEW["Artefact de poison nouveau / edite"] --> Q1{"doc empoisonne dans un fichier scenario ?"}
  Q1 -->|oui| G4["garde scenario T4 : la decision gateway pour rag_agent sur l'action injectee egale injected_expect, et injected_expect est deny ou escalate"]
  G4 -->|incoherence ou allow| RED1["suite ROUGE : aucune preuve de blocage"]
  G4 -->|correspondance| Q2
  Q1 -->|non| Q2{"insere via store.add ?"}
  Q2 -->|oui| G5["garde id T5 : l'id correspond au pattern de slug du corpus"]
  G5 -->|id invalide| RED2["KnowledgeBaseError"]
  G5 -->|valide| OK["accepte dans le corpus"]
  Q2 -->|non| OK
```

## CLI

```
python -m recette rag-kb list
python -m recette rag-kb scenarios
python -m recette rag-kb apply --scenario exfil-finance
python -m recette rag-kb add --doc path/to/doc.json
python -m recette rag-kb del --id <doc-id>
python -m recette rag-kb reset
```

Un document JSON porte `id, title, content, poisoned, tags` ; un document
empoisonne porte en plus `injected_action, injected_target_system,
injected_expect, threat`.

## API HTTP (routes operateur, hors du chemin de l'agent)

| Methode | Route | Role |
|--------|-------|---------|
| GET | `/rag/documents` | liste la base de connaissances courante |
| POST | `/rag/documents` | insere un document (400 si invalide) |
| DELETE | `/rag/documents/{id}` | supprime un document (404 si inconnu) |
| POST | `/rag/reset` | restaure la baseline propre |
| GET | `/rag/scenarios` | liste les scenarios de poison nommes |
| POST | `/rag/scenario/{name}/apply` | injecte les documents d'un scenario nomme |

Les reponses sont des dicts JSON simples (pas d'enveloppe `{success, data}` --
coherent avec le reste de l'API). La page console `/rag` rend le
`KnowledgeBaseManager` sous la scorecard de retrieval.

## Scenarios

`corpus/rag/scenarios/*.json`, valides par `scenario.schema.json`. Chacun est un
ensemble nomme de documents a injecter. Livres : `exfil-finance`
(exfiltration), `invalid-command-ops` (commande inconnue). On en ajoute un en
deposant un nouveau fichier. Deux gardes maintiennent un scenario honnete :

- **garde scenario (T4)** -- pour chaque doc empoisonne de chaque fichier
  scenario,
  `tests/test_rag_poisoning.py::test_scenario_guard_every_poisoned_doc_is_blocked_by_the_gateway`
  decide l'action injectee pour un `rag_agent` et asserte que le verdict egale
  l'`injected_expect` du doc ET est un blocage (`deny`/`escalate`). Un scenario
  dont le poison est en fait autorise, ou dont l'`injected_expect` declare derive
  par rapport au moteur, fait passer la suite au ROUGE -- aucun poison ne sort
  sans preuve fondee sur decide qu'il est bloque.
- **garde KB-seed** -- `test_kb_guard_every_poisoned_doc_has_a_campaign` maintient
  les docs empoisonnes de `knowledge_base.json` alignes avec une campagne
  `campaigns/rag/`.

## Securite / invariants

- **anti-backdoor I2** : le CRUD operateur est sur les routes `/rag/*`, jamais sur
  le chemin agent `/actions/execute`. Un agent qui tente `ingest_document`
  ESCALADE quand meme via la gateway (`tests/test_api_rag_kb.py::test_anti_backdoor_...`).
  Le CRUD n'ouvre pas de contournement de mutation.
- **Path traversal** : un `name` de scenario est valide contre
  `^[a-z0-9][a-z0-9-]{1,63}$` et le chemin resolu doit rester a l'interieur du
  repertoire des scenarios, si bien que `apply_scenario("../knowledge_base")` ou un
  chemin absolu est rejete (`test_apply_scenario_rejects_path_traversal`). Sans
  cette garde, un nom forge pourrait charger un `.json` arbitraire depuis le disque.
- **Slug d'id (T5, defence en profondeur)** : l'`id` d'un document insere doit
  correspondre au meme slug `^[a-z0-9][a-z0-9-]{1,63}$` que le schema. L'id ne
  touche aucun chemin de fichier, mais imposer la forme du corpus au niveau du
  store rejette tot les identifiants errants (`test_add_rejects_invalid_id_slug`).
- **determinisme du reset I4** : `reset()` recharge la baseline octet par octet
  (`test_reset_is_deterministic`).

## Tests

- `tests/test_rag_store.py` -- CRUD, determinisme du reset, injection de scenario,
  le handler du lab refletant le store, rejet du path-traversal, rejet du slug d'id
  (T5).
- `tests/test_api_rag_kb.py` -- les six routes + la garantie anti-backdoor I2.
- `tests/test_rag_poisoning.py` -- verdicts fondes sur decide de chaque action
  `campaigns/rag/`, la garde de campagne KB-seed, et la garde de poison scenario
  (T4).
- `console/src/pages/rag/KnowledgeBaseManager.test.tsx` -- R16 render-and-assert
  contre un payload reel capture.
- La recette systeme LEG C (`scripts/run_system_recette.py`) exerce la boucle
  complete reset -> apply -> campaign -> anti-backdoor de bout en bout.
