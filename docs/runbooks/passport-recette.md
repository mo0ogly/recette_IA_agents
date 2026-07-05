# Runbook -- Passeport d'agent signe (Contrat 3, axe attestation)

Comment un developpeur emet, verifie et recette un **passeport d'agent** signe
(`.inspect_ia_agents/passport.json`) : l'attestation cryptographique FIGEE qui lie
une identite d'agent a une chaine de mandat (jusqu'a un humain), un scope d'actions
permises et une expiration. C'est l'artefact derriere l'**axe attestation** de la
discovery (`trusted` / `untrusted` / `unsigned` / `malformed`), distinct de l'axe
passeport-manifest de l'inventaire (`present` / `absent` / `invalid`).

> Concept fondateur (source de verite) :
> `docs/plans/2026-07-05-agent-passport-design.md` (Contrat 3 "le passeport"), derive
> de la spec pare-feu de gouvernance des agents (vocabulaire NIST SP 800-207 PEP/PDP).
> Complement de la recette d'inventaire (`docs/runbooks/inventory-recette.md`) : le
> passeport-manifest dit ce que l'agent DECLARE ; le passeport signe dit ce qu'une
> AUTORITE atteste.

## Ce qu'est le passeport

Le passeport est un **tuple signe, fige entre delivrance et expiration** : une
autorite scelle un jeu de revendications (`Claims`) avec sa cle Ed25519, et personne
ne peut ensuite alterer une revendication sans casser la signature. Dans le
vocabulaire de la spec pare-feu (NIST SP 800-207) : la gateway + les proxies (I5)
sont le **PEP** (Policy Enforcement Point), le policy engine deny-by-default est le
**PDP** (Policy Decision Point) ; le passeport est le **credential d'identite** que le
PEP presente au PDP pour lier une action a une identite attestee (I3). La phase 1
(recette, ci-dessous) inspecte des agents NON executes : elle cree l'artefact,
l'inspecteur et l'oracle. La phase 2 fait verifier le passeport par la gateway a
l'enregistrement d'un agent runtime ET a chaque action, en reutilisant le MEME
oracle -- voir le runbook dedie : `docs/runbooks/passport-admission.md`
(admission runtime, modes observe/enforce, deux gardes).

Champs signes (`Claims`) : `id`, `tenant`, `delegation` (chaine de mandat), `scope`
(familles d'actions permises), `exp` (expiration RFC 3339 UTC), `spiffe_id`
(optionnel). Le passeport ajoute deux champs NON signes : `signature` (Ed25519 hex) et
`key_id` (version de cle de l'autorite, pour la verification post-rotation).
`additionalProperties: false` -- aucune donnee d'attestation ne peut passer la
frontiere de signature (schema `corpus/schemas/agent-passport.schema.json`).

### La forme canonique signee (ce que couvre la signature)

La signature couvre les **`Claims` uniquement**, jamais `signature`/`key_id`. Les
octets signes (`agent-passport/src/canonical.rs`) sont un objet JSON compact, cles en
**ordre d'octets croissant** : `delegation`, `exp`, `id`, `scope`, `spiffe_id`,
`tenant`. Le `spiffe_id` absent (`None`) est OMIS (pas de cle nulle). Cette forme
fige est identique cote Rust et cote oracle Python -- c'est le socle de l'equivalence.

### Deux axes orthogonaux (a ne jamais confondre)

L'inventaire porte DEUX axes independants, chacun keye sur son propre `kind`, jamais
re-derive de l'autre :

| Axe | Source | Etats (`kind`) | Ce qu'il dit |
|-----|--------|----------------|--------------|
| **Passeport-manifest** | `.inspect_ia_agents/manifest.json` (NON signe) | `present` / `absent` / `invalid` | ce que l'agent DECLARE, et si sa declaration valide le schema |
| **Attestation** | `.inspect_ia_agents/passport.json` (SIGNE) | `trusted` / `untrusted` / `unsigned` / `malformed` | ce qu'une AUTORITE atteste, et si la signature/expiration/delegation tiennent |

Les deux sont orthogonaux : un agent peut etre un shadow cote manifest (`absent`) tout
en portant un credential `trusted`, ou porter un manifest `present` tout en etant
`unsigned`. Aucun axe n'implique l'autre ; la console montre les deux badges cote a
cote.

## Le crate exportable `agent-passport`

`discoveryprobe/agent-passport/` est une **lib Rust pure, embarquable** : zero I/O,
zero horloge (l'horloge est un input injecte, I4), zero mock, zero valeur en dur. Elle
expose deux fonctions et leurs types.

- **Emission** : `issue(claims: Claims, signing_key: &SigningKey, key_id: &str) ->
  Result<Passport, PassportError>` -- calcule les octets canoniques, signe en Ed25519,
  scelle le `Passport`.
- **Verification** : `verify(passport: &Passport, trust: &TrustStore, now:
  &Timestamp, declared: Option<&DeclaredScope>) -> Verdict` -- ne retourne JAMAIS
  d'erreur et ne panique JAMAIS (frontiere fail-safe du crate). Un `Verdict` est soit
  `Trusted`, soit `Untrusted { reasons }` avec TOUTES les raisons applicables,
  accumulees puis triees (verdict rejouable, I4).

Les raisons d'`untrust` (enum `UntrustReason`, tagge par `kind` en snake_case) :

| Raison (`kind`) | Sens |
|-----------------|------|
| `bad_signature` | la signature Ed25519 ne verifie pas contre la cle de confiance |
| `expired` | `exp <= now` (expire a l'instant exact `exp`) |
| `empty_delegation` | la chaine de mandat est vide -- aucun principal |
| `no_human_principal` | la chaine ne se termine pas sur un humain (entree terminale prefixee `human:` OU contenant `@`) |
| `scope_overreach` | le scope declare demande des familles absentes du scope signe -- porte `extra` (les familles en trop, triees) |
| `unknown_key_id` | le `key_id` est absent du trust store ; la signature n'a pas pu etre verifiee |
| `malformed_field` | un champ n'a pu etre interprete -- porte `field` (ex. `exp`) |

C'est le crochet de phase 2 : la gateway reutilisera `verify` pour un deny-by-default
si `untrusted`/`unsigned`/`absent`.

## Emission -- `passport issue`

Le consommateur d'I/O du crate pur est le binaire `discoveryprobe-inventory`. La
sous-commande `passport issue` lit la graine de signature Ed25519 (seed 32 octets, en
hex = 64 caracteres) depuis la variable d'environnement `INSPECT_IA_AGENTS_PASSPORT_KEY`
(jamais loggee ni echoee, R8), scelle les revendications et ecrit le passeport.

```
discoveryprobe-inventory passport issue <tree> --agent-id <id> --tenant <t> --scope <a,b,c> --delegation <x,human:alice> --exp <rfc3339> --key-id <k> [--spiffe-id <spiffe://...>] [--out <file>]
```

| Flag | Role |
|------|------|
| `<tree>` | l'arbre d'agent (racine de sortie par defaut) |
| `--agent-id` | identifiant d'agent (`id`) -- REQUIS |
| `--tenant` | tenant proprietaire -- REQUIS |
| `--scope` | familles d'actions permises (CSV) -- REQUIS |
| `--delegation` | chaine de mandat (CSV, se termine sur un humain) -- REQUIS |
| `--exp` | expiration RFC 3339 UTC -- REQUIS |
| `--key-id` | version de cle de l'autorite qui scelle -- REQUIS |
| `--spiffe-id` | identite SPIFFE optionnelle (`spiffe://...`) |
| `--out` | fichier de sortie (defaut : `<tree>/.inspect_ia_agents/passport.json`) |

Fail-safe : la graine est resolue et le passeport scelle+encode AVANT toute ecriture
disque -- aucun fichier passeport n'est produit sur un chemin d'erreur. Codes de
sortie : 0 succes, 2 usage, 1 autre.

Exemple (autorite de test du corpus, graine publique de `.env.example`) :

```
export INSPECT_IA_AGENTS_PASSPORT_KEY=46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e
discoveryprobe/target/release/discoveryprobe-inventory passport issue corpus/repos/gh-pr-bot/repo --agent-id "acme-dependency-pr-bot[bot]" --tenant acme --scope read_repo,open_pr --delegation "acme-platform-team,human:alice" --exp 2030-01-01T00:00:00Z --key-id test-authority-1 --spiffe-id spiffe://acme/agent/dependency-pr-bot
```

> Source de la cle (R18) : la graine vit dans `.env` ; la cle de test du corpus est
> **publiquement connue** dans `.env.example` (autorite de test, rien a faire tourner,
> rien a rotationner -- elle ne signe que des fixtures). Voir `corpus/keys/README.md`.

## Verification -- `passport verify`

Le verificateur fail-safe lit un passeport EXISTANT, charge un fichier de confiance
(`--trust`, un objet JSON `{ "<key_id>": "<pubkey_hex>", ... }`) dans un `TrustStore`,
et le confronte a une horloge INJECTEE (`--now`, I4 -- jamais `SystemTime::now`) et a
un scope declare optionnel (`--declared`).

```
discoveryprobe-inventory passport verify <tree> --trust <pubkeys.json> --now <rfc3339> [--declared <a,b,c>]
```

| Flag | Role |
|------|------|
| `<tree>` | l'arbre dont on verifie `.inspect_ia_agents/passport.json` |
| `--trust` | le fichier de confiance `{ key_id: pubkey_hex }` -- REQUIS |
| `--now` | l'horloge injectee RFC 3339 UTC pour le controle d'expiration -- REQUIS |
| `--declared` | scope declare (CSV) pour le controle de scope-overreach -- optionnel |

Le JSON du verdict est le produit (imprime dans tous les cas sur stdout) ; le **code
de sortie est le portail** :

| Code | Sens |
|------|------|
| `0` | `trusted` |
| `3` | `untrusted` (verdict imprime avec ses raisons -- ce N'EST PAS une erreur) |
| `2` | erreur d'usage/config (mauvais flag, `--trust` illisible/malforme, `--now` invalide) |
| `1` | io/autre (passeport absent ou non parsable) |

Exemple -- verifie contre le fichier de confiance committe (doit imprimer
`{"kind":"trusted"}`) :

```
discoveryprobe/target/release/discoveryprobe-inventory passport verify corpus/repos/gh-pr-bot/repo --trust corpus/keys/test-authority.trust.json --now 2027-01-01T00:00:00Z
```

### Le scope-overreach ne se voit qu'avec `--declared`

Le controle de scope est le SEUL a dependre de `--declared`. Un `verify` NU (sans
`--declared`) ne verifie que signature + expiration + delegation. Pour
`gh-passport-scope-overreach`, cela donne `trusted` (exit 0). En passant les actions
du manifest (`read_repo,push`) via `--declared`, le passeport dont le scope signe ne
couvre que `read_repo` devient `untrusted` avec raison `scope_overreach`, `extra
['push']` (exit 3) :

```
discoveryprobe/target/release/discoveryprobe-inventory passport verify corpus/repos/gh-passport-scope-overreach/repo --trust corpus/keys/test-authority.trust.json --now 2027-01-01T00:00:00Z --declared read_repo,push
```

Le ground-truth `attestation_status: "untrusted"` de ce sujet REFLETE le verdict
verify-avec-declared ; l'oracle applique les capacites du manifest comme scope declare.

## L'axe attestation dans le scan + l'API

### `scan --trust --now`

La sous-commande `scan` emet desormais un `attestation` par agent (orthogonal a l'axe
passeport-manifest). Il est calcule comme `passport verify` mais avec `declared = None`
(le scan couvre signature/expiration/delegation, jamais le scope-overreach -- celui-ci
demande les capacites declarees, hors du scan) :

```
discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>] [--trust <pubkeys.json>] [--now <rfc3339>]
```

Sans `--trust` ET `--now`, un `passport.json` present est le fail-safe `untrusted`
(`unknown_key_id`) : le scan ne revendique JAMAIS `trusted` sans keyring injecte. I4 :
`--now` est la seule horloge.

L'`Attestation` du modele de scan porte quatre etats : `trusted`,
`untrusted { reasons }`, `unsigned` (pas de fichier passeport), `malformed { message }`
(fichier present mais illisible/non parsable).

### `GET /probe/inventory`

L'endpoint (`recette/api/routers/probe.py`) fait un scan live a la demande sur chaque
arbre sous `corpus/repos/*/repo`. Quand le fichier de confiance du corpus existe, il
invoque le binaire avec `--trust corpus/keys/test-authority.trust.json --now
<reference>` de sorte qu'un passeport signe resolve son attestation. L'horloge de
reference est une constante injectee (defaut `2027-01-01T00:00:00Z`, surchargeable par
`INSPECT_IA_AGENTS_INVENTORY_NOW`, R5) : fixe, jamais `datetime.now()`, pour que les
verdicts d'attestation restent deterministes (I4). Le fichier de confiance n'a PAS de
surcharge d'env -- c'est un artefact de corpus fixe, pas un bouton d'operateur. Le
`summary` agrege quatre compteurs d'attestation : `attested_trusted`,
`attested_untrusted`, `unsigned`, `attested_malformed`.

### La console

Le panneau `InventoryPanel` (page **Probe**) rend, par agent, un **badge
d'attestation** SECOND et ORTHOGONAL au badge de passeport-manifest. Il est keye sur
`attestation.kind` SEUL (les quatre etats `trusted` / `untrusted` / `unsigned` /
`malformed`). Le badge `untrusted` surface ses raisons typees (le POURQUOI, avec le
`extra` de `scope_overreach` et le `field` de `malformed_field`) ; le badge
`malformed` surface son message de lecture/parse.

## Les sujets du corpus + l'oracle d'equivalence

Quatre positifs `trusted` + trois negatifs mono-axe (R20) exercent l'axe attestation.
Seuls les positifs a manifest valide (identite presente) sont signes et de confiance ;
leur `discovery-ground-truth.json` porte `attestation_status: "trusted"`.

| Sujet | attestation_status | Axe (mono) |
|-------|--------------------|------------|
| `gh-pr-bot` | `trusted` | positif |
| `gh-readonly-reporter` | `trusted` | positif |
| `gh-admin-overreach` | `trusted` | positif |
| `gh-supply-chain-compromise` | `trusted` | positif |
| `gh-passport-expired` | `untrusted` | `expired` |
| `gh-passport-tampered` | `untrusted` | `bad_signature` |
| `gh-passport-scope-overreach` | `untrusted` | `scope_overreach` (verify-avec-declared) |

Chaque negatif casse EXACTEMENT UN axe ; tous les autres axes de discovery restent
conformes (le scanner detecte l'agent, surface ses action_patterns, emet une policy).

**L'oracle d'equivalence** (`recette/adapters.py::attest_passport`, teste par
`tests/test_passport_equivalence.py`) est un troisieme oracle independant. Le test
epingle l'equivalence sur TROIS fronts pour chaque sujet portant un passeport signe :

1. statut/raisons de l'oracle Python == verdict du `passport verify` Rust (pilote en
   sous-processus sur le binaire release ; si le binaire est absent, cette jambe est
   sautee, jamais traitee en `trusted`) ;
2. statut de l'oracle Python == `attestation_status` du ground-truth committe (le
   corpus est le troisieme oracle).

`--declared` est applique des DEUX cotes pour CHAQUE sujet (les familles d'actions du
manifest) : sans lui, le Rust rapporterait `trusted` pour `gh-passport-scope-overreach`
alors que l'oracle rapporte `untrusted` -- une fausse divergence. Le controle Ed25519
demande l'extra `[bundle]` (`cryptography`) ; sans lui l'oracle leve `ImportError` et
les asserts crypto sont sautes explicitement, jamais silencieusement traites en
`trusted` (fail-safe I4).

## Modes fail-safe (jamais fail-open)

- **Pas de keyring** (scan/endpoint sans `--trust`/`--now`) -> un passeport present est
  `untrusted` (`unknown_key_id`), jamais `trusted`.
- **Passeport corrompu** (present mais illisible/non parsable au scan) -> `malformed`.
- **Passeport absent** -> `unsigned`.
- **`key_id` inconnu du trust store** -> `unknown_key_id`, signature non verifiee.
- **`cryptography` absent** (oracle Python) -> `ImportError`, asserts crypto sautes,
  jamais `trusted` par defaut.

En cas de doute, l'attestation se ferme (`untrusted`/`unsigned`/`malformed`), jamais
`trusted`.

## Reproduire le keyring de test

La graine 32 octets est le SHA-256 d'une phrase fixe, donc tout le keyring est
reproductible depuis la documentation seule (R4) :

```
phrase = "inspect_ia_agents corpus test authority passport seed v1"
seed   = sha256(phrase) = 46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e
```

Regenerer la graine depuis la phrase :

```
python3 -c "import hashlib; print(hashlib.sha256(b'inspect_ia_agents corpus test authority passport seed v1').hexdigest())"
```

Deriver la cle publique (doit egaler `corpus/keys/test-authority.pub` et la valeur du
fichier de confiance) :

```
python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; seed=bytes.fromhex('46b780099aa6e71c37b3c87ac32872cd1cfdbcd1276e598aa8e7e083fd24150e'); print(Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw().hex())"
```

Le fichier de confiance committe (`corpus/keys/test-authority.trust.json`) mappe
`test-authority-1` -> `83448c3dcc62fd545ec7e6f06a168ea48470ebc1b2630fd49facec0f3b0373cd`.
Detail complet : `corpus/keys/README.md`.

## Caveat : NE PAS regenerer `gh-passport-tampered`

`corpus/repos/gh-passport-tampered/` est un artefact **deliberement altere a la main**
(negatif mono-axe `bad_signature`). Il a ete emis comme un passeport valide par
`test-authority-1`, puis une revendication signee a ete modifiee APRES signature
(`tenant` change de `acme` a `acme-evil` sans re-signer). La signature reste un hex de
128 caracteres structurellement valide (schema-valide) mais ne matche plus les
revendications -> `verify` => `untrusted` raison `bad_signature`.

Lancer `passport issue` ou tout outil de regeneration sur cet arbre **DETRUIT le sujet
de test** (il re-signerait les revendications alterees, effacant le defaut). Le fichier
`.inspect_ia_agents/DO-NOT-REGENERATE.md` de l'arbre le documente. En cas d'ecrasement
accidentel, restaurer depuis git : `git checkout HEAD -- .inspect_ia_agents/passport.json`.

## Construire l'outil

Le binaire est produit par le build natif hote du workspace `discoveryprobe/` :

```
./recette.sh discovery-build
```

Cela lance `cargo build --release` et produit
`discoveryprobe/target/release/discoveryprobe-inventory`. Le crate `agent-passport`
(lib pure) en est une dependance de workspace.

## Notes

- Determinisme (I4) : `verify` est une fonction pure, horloge et trust injectes ; les
  raisons sont triees, le verdict serialise est byte-stable. L'endpoint fige l'horloge
  de reference.
- I3 : le passeport lie une action a une identite d'agent attestee (chaine de mandat
  jusqu'a un humain).
- R8 : la cle vit dans l'environnement (`.env`) ; la cle de test du corpus est publique
  par conception, jamais un secret de production.
- Le passeport est fige entre delivrance et expiration : jamais mute (une correction =
  un nouveau passeport, coherent avec I1).
