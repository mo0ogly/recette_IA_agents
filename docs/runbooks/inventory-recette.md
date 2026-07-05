# Runbook -- Inventaire des agents (discoveryprobe-inventory)

Comment un developpeur utilise l'outil `discoveryprobe-inventory` pour identifier en
detail les agents IA d'un arbre source, reconnaitre leur **passeport**
(`.inspect_ia_agents/manifest.json`), reperer les **shadow agents** (code d'agent sans
passeport) et detecter la **communication multi-agents** (graphe declare vs observe).

> Concept fondateur (source de verite) :
> `docs/plans/2026-07-04-discoveryprobe-inventory-design.md`. Cet outil complete la
> recette de detection de surface (`docs/runbooks/surface-detection-recette.md`) : la
> sonde eBPF prouve qu'un agent est VU ; l'inventaire dit en detail QUI il est, ce
> qu'il DECLARE et s'il est CONFORME.

## Ce que fait l'outil

`discoveryprobe-inventory` est un **correlateur central** (crate Rust, lib + binaire)
qui produit un rapport `AgentInventory` deterministe (I4) a partir de trois entrees :

1. un **scan statique** de l'arbre source (les passeports parses + le code d'agent sans
   passeport, detecte par heuristiques : imports SDK, entrypoint) ;
2. le **graphe declare** de handoffs (les manifests + les `team.json` d'orchestration
   MAF) ;
3. une **observation runtime** optionnelle (`--capture`), l'`ObservedInput` JSON drainee
   depuis la sonde (actions, egress, IPC inter-agents).

La correlation (`correlate.rs`) est une **fonction pure** : zero I/O, zero horloge (I4).
Toutes les donnees observees arrivent comme fichier d'entree. Deux scans identiques
produisent un JSON byte-identique (test de replay).

### Les trois etats du passeport (invariant central)

Chaque agent porte un `passport.kind` -- la **seule source de verite** que le scanner
emet, jamais re-derivee ailleurs :

| Etat | Sens | Signal |
|------|------|--------|
| `present` | `.inspect_ia_agents/manifest.json` present ET valide contre `corpus/schemas/agent-manifest.schema.json` | le manifest est parse a fond (kind, identite, capability_scope, handoffs) |
| `absent` | code d'agent detecte, AUCUN manifest dans l'arbre -- le **shadow agent** | `Absent` porte l'**evidence** (imports PyGithub / SDK LLM, entrypoint, env provider) : aucune revendication sans preuve (R13) |
| `invalid` | un manifest existe mais echoue la validation de schema | les **erreurs** de validation sont surfacees, jamais un booleen nu |

`present` ne signifie pas `Conform`. La conformite est un axe distinct :
`Conform` | `NotObserved` | `Violations`. Un scan **statique seul** (sans `--capture`)
ne peut JAMAIS conclure `Conform` -- il rend `NotObserved` (fail-safe, jamais un faux
"conforme").

### Communication multi-agents

Le rapport porte un `comm_graph` a quatre listes :

- `declared_edges` : les handoffs des manifests + des `team.json` (l'union dedupee) ;
- `observed_edges` : les aretes inter-agents correlees depuis l'IPC runtime
  (pid -> agent via l'arbre de fork) ;
- `undeclared_edges` : `observed - declared` = les **handoffs non declares** (violation
  `UndeclaredHandoff`) ;
- `via_gateway_edges` : une arete dont la destination est un agent **passerelle** connu
  (LiteLLM, mitmproxy -- entree de config R5, jamais en dur) est rangee ici, pas comme un
  handoff direct non declare.

Limite documentee (jamais cachee) : la sonde voit l'**arete**, pas le contenu (TLS/payload
invisible -- la topologie suffit pour "y a-t-il de la comm multi-agents" + la conformite
des handoffs).

## La CLI

Un binaire de workspace, sans dependance d'arg-parsing (JSON sur stdout, erreurs sur
stderr ; codes de sortie 0 succes, 2 usage, 1 autre) :

```
discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>] [--trust <pubkeys.json>] [--now <rfc3339>]
```

| Argument | Role |
|----------|------|
| `<path>` | l'arbre source a scanner (`scan::scan_tree_attested`) |
| `--capture <file.json>` | un fichier `ObservedInput` JSON (observation runtime). Absent = scan statique seul, dont la conformite ne peut jamais etre `Conform` |
| `--team <dir>` | un repertoire parcouru recursivement (trie) pour ses `team.json`. Le graphe declare = passeports + teams |
| `--out <file>` | ecrit le JSON dans ce fichier au lieu de stdout |
| `--trust <pubkeys.json>` / `--now <rfc3339>` | keyring + horloge injectee OPTIONNELS pour l'axe **attestation** (passeport signe). Sans les deux, un `passport.json` present est le fail-safe `untrusted`. Detail : `docs/runbooks/passport-recette.md` |

Le binaire porte aussi deux sous-commandes passeport (`passport issue`, `passport
verify`) documentees dans `docs/runbooks/passport-recette.md`.

Flags verifies dans `discoveryprobe/discoveryprobe-inventory/src/main.rs` (const `USAGE`
et `parse_args`).

### Forme de l'entree `--capture` (ObservedInput)

Le fichier `--capture` est un `ObservedInput` (voir `src/model.rs`) : `recordings`
(captures par agent), `observed_edges` (aretes pre-correlees, unionees avec celles
derivees de l'IPC), `observed_principals` (`(agent_id, principal observe)`), `ipc` (les
`IpcEvents` reconcilies), `forks` (`(parent_pid, child_pid)`), `pid_agents`
(`pid -> agent_id`), `gateways` (les agents traites comme passerelles). Tout est
optionnel (`#[serde(default)]`) sauf `recordings` : une capture hook-only ne porte
aucun IPC.

### Forme de la sortie (AgentInventory)

```
AgentInventory {
  schema_version,                       // "1.0"
  agents: [ AgentRecord {
    agent_id, passport, kind, declared, observed, conformity, evidence
  } ],                                  // trie par agent_id (I4)
  comm_graph { declared_edges, observed_edges, undeclared_edges, via_gateway_edges },
  summary { with_passport, without_passport, invalid_passport, violation_count }
}
```

Chaque valeur d'enum est un objet **tagge par `kind`** (le passeport, la conformite, les
violations) : le consommateur dispatche sur `value["kind"]`, jamais par devinette de
forme.

## Exemples (verifies dans les tests de la CLI)

Scan statique du corpus PR-bot (un agent, jamais `Conform` en statique) :

```
discoveryprobe-inventory scan corpus/repos/gh-pr-bot/repo
```

Ajouter un graphe declare depuis un repertoire d'equipe MAF :

```
discoveryprobe-inventory scan corpus/repos/gh-pr-bot/repo --team corpus/maf_orchestration/correct/finance-approval-handoff-correct
```

Correler avec une observation runtime (l'agent devient `Conform` si l'action observee est
dans son scope) :

```
discoveryprobe-inventory scan corpus/repos/gh-pr-bot/repo --capture discoveryprobe/discoveryprobe-inventory/tests/fixtures/capture-pr-bot.json
```

## Comment la recette consomme l'inventaire

- **Le pont Python** `recette/inventory_bridge.py` (`parse_inventory`) est une frontiere :
  il mappe l'`AgentInventory` en objets `DiscoveryRisk` + un champ `passport_status`
  (issu directement de `passport.kind`, jamais re-derive). Une entree malformee leve un
  `ValueError` clair -- jamais une liste vide silencieuse (fail-safe).
- **L'adaptateur de reference** (`ReferenceSourceScanAdapter`) produit les memes champs :
  l'outil Rust et l'oracle de reference doivent converger sur le meme ground-truth.
- **Le ground-truth de discovery** porte l'invariant `passport_status` (jamais une valeur
  opaque comme `canonical_agent_id` ou un score exact -- R20). Le harnais assert la
  presence/absence du passeport, les types de violation et les comptes d'aretes.

### Les sujets du corpus

Deux sujets ground-truth mono-axe (R20) exercent la reconnaissance de passeport :

- `corpus/repos/gh-shadow-agent/` -- vrai code d'agent GitHub (lit des repos, ouvre des
  PR) SANS `.inspect_ia_agents/` -> attendu `passport_status: "absent"`. Le scanner doit
  detecter l'agent par le fallback code ET signaler le passeport absent : detecter le code
  mais faire silencieusement confiance au passeport manquant est la faute que ce sujet
  garde.
- `corpus/repos/gh-invalid-passport/` -- un `manifest.json` present mais amoindri (objet
  `agent.identity` manquant) : il parse en JSON mais echoue la validation -> attendu
  `passport_status: "invalid"`. Un manifest casse rapporte comme invalide, jamais
  silencieusement traite comme une declaration valide.

## Le second axe : l'attestation (passeport signe)

L'inventaire porte DEUX axes orthogonaux. Le passeport-manifest ci-dessus
(`present` / `absent` / `invalid`) dit ce que l'agent DECLARE. Un **second axe,
independant**, dit ce qu'une AUTORITE atteste : l'`attestation` d'un
`.inspect_ia_agents/passport.json` SIGNE, avec quatre etats `trusted` / `untrusted` /
`unsigned` / `malformed`. Le scan l'emet par agent quand on lui passe un keyring et une
horloge injectee (`scan --trust <pubkeys.json> --now <rfc3339>`) ; sans les deux, un
passeport present est le fail-safe `untrusted` (jamais `trusted` sans keyring). Les deux
axes sont independants : un shadow-agent (`absent`) peut porter un credential `trusted`,
un manifest `present` peut etre `unsigned`.

L'emission (`passport issue`), la verification (`passport verify`, avec son contrat de
codes de sortie et le controle de scope-overreach via `--declared`), les sujets de
corpus attestation (4 positifs `trusted` + 3 negatifs mono-axe) et l'oracle
d'equivalence Rust/Python sont couverts dans un runbook dedie :
`docs/runbooks/passport-recette.md`.

## L'API et la console

- **Endpoint** : `GET /probe/inventory` (`recette/api/routers/probe.py`) fait un **scan
  live a la demande** : il lance le binaire Rust `discoveryprobe-inventory` sur chaque
  arbre d'agent sous `corpus/repos/*/repo` (racine et binaire configurables par
  `INSPECT_IA_AGENTS_INVENTORY_SCAN_ROOT` / `INSPECT_IA_AGENTS_INVENTORY_BIN`, R5), fusionne
  les inventaires et renvoie `{inventory, live: true, engine}` sous la cle `inventory`.
  Quand le fichier de confiance du corpus (`corpus/keys/test-authority.trust.json`) existe,
  le scan est invoque avec `--trust <file> --now <reference>` pour resoudre l'axe
  attestation ; l'horloge de reference est une constante injectee (defaut
  `2027-01-01T00:00:00Z`, surchargeable par `INSPECT_IA_AGENTS_INVENTORY_NOW`, I4/R5).
  Read-only (I1) : le moteur ne fait que lire les sources. Fail-safe (R7) : si le binaire
  n'est pas build (`./recette.sh discovery-build`), la route retombe sur l'echantillon
  committe (`corpus/inventory/sample-inventory.json`) avec `live: false` + `reason` -- le
  panneau rend quand meme, et l'operateur sait que c'est l'echantillon. Un id d'agent derive
  du montage generique (`repo`) est reetiquete par le slug du sujet (ex. `gh-shadow-agent`).
- **Console** : le panneau `InventoryPanel` (page **Probe**) rend, par agent : son
  id, l'**evidence** de code scanne, le **badge de passeport** (present / absent /
  invalide -- keyed off `passport.kind` seul, jamais sur une liste de violations non vide),
  le **badge d'attestation** (trusted / untrusted / unsigned / malformed -- second axe
  orthogonal keye sur `attestation.kind` seul, `docs/runbooks/passport-recette.md`),
  le kind du sujet, et le verdict de conformite. Un badge **LIVE SCAN** (vert) / **SAMPLE**
  (ambre) indique si l'inventaire vient d'un scan live ou de l'echantillon. Sous la table :
  la liste des violations et le graphe de communication (aretes declarees vs observees, non
  declarees en rouge, via-passerelle a part). Aide UI : bouton **? Aide** (topic `inventory`).

## Construire l'outil

L'inventaire est un membre du workspace `discoveryprobe/` (voir
`discoveryprobe/Cargo.toml`). Le build natif hote le compile :

```
./recette.sh discovery-build
```

Cela lance `cargo build --release` dans `discoveryprobe/` et produit le binaire
`discoveryprobe/target/release/discoveryprobe-inventory` (aux cotes de
`discoveryprobe-catalog`). Le crate eBPF privilegie (`discoveryprobe-ebpf`) est EXCLU de ce
build hote (cible differente).

### Le caveat eBPF (comm inter-agents live)

Le scan statique et le `--capture` depuis un fichier ne demandent **aucun privilege**.
Pour alimenter `--capture` avec de la comm inter-agents live, il faut la sonde eBPF, qui
demande `CAP_BPF` (et `cap_dac_read_search` : aya attache un tracepoint en lisant un
fichier root-only). Deux etapes, une seule fois :

```
./recette.sh probe-ebpf-build
./recette.sh probe-grant-caps
```

`probe-ebpf-build` compile l'objet eBPF + le broker CAP_BPF (jamais de chargement, aucun
privilege pour compiler). `probe-grant-caps` accorde les caps au broker (sudo -- l'unique
etape privilegiee, une exigence du kernel) pour que le lanceur le tourne ensuite non
privilegie. Sans caps, l'observation runtime reste vide et la conformite reste
`NotObserved` (fail-safe, jamais "conforme par defaut"). Detail :
`docs/runbooks/ebpf-live-capture.md`.

## Notes

- L'inventaire ne mediatise jamais : la sonde OBSERVE, elle n'execute pas (I5). Le broker
  reste capture-only ; aucune logique metier dans le daemon privilegie.
- Determinisme (I4) : `correlate.rs` est pur, tout est trie/dedupe, deux scans donnent un
  JSON byte-identique (test de replay sur une paire de fixtures figee).
- L'absence de runtime est un mode de premiere classe : scan statique seul, champs
  observes vides, conformite `NotObserved` -- jamais un faux `Conform`.
