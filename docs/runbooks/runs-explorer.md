# Explorateur de runs -- surface de consultation web pour chercheurs

> Pour l'equipe recherche et recette. Surface web-uniquement permettant de
> parcourir, lire et rejouer chaque run (agent, campagne, mega-campagne, discovery,
> recette-full) sans acces terminal ni parsing manuel de fichiers plats.

## Le probleme resolu

Les resultats de recette etaient ecrits comme fichiers plats dans
`docs/tracking/recette/` et **ecrases a chaque lancement** (le probleme du
clobber `.PRE.bak`). Deux defaillances concretes :

1. Pas d'historique -- un nouveau run detruisait le precedent (aucun euro-datage,
   aucun groupement).
2. Un chercheur avec acces web uniquement ne peut pas atteindre un fichier plat
   sur disque ni analyser manuellement une sortie de mega-campagne. Le resultat
   doit etre navigable, lisible et rejouable depuis une surface web moderne
   (arborescence + Monaco), pas depuis un terminal.

Principe legibility-first (CLAUDE.md) : une surface qu'un tiers n'ayant pas
execute le run ne peut pas observer n'est pas recettable. L'Explorateur de runs
est cette surface observable.

## Surface web-uniquement : pourquoi cette contrainte

Les chercheurs qui evaluent les agents n'ont en general qu'un acces navigateur a
la console. Ils ne peuvent ni se connecter en SSH ni executer des commandes shell.
Le resultat brut d'une mega-campagne SKYNET peut contenir des centaines de
fichiers JSONL impossibles a lire manuellement. L'Explorateur de runs est la
reponse a cette contrainte : tout ce que la recette produit est range, date,
consultable et rejouable via l'interface web -- aucun acces disque requis.

## Structure de stockage euro-datee (3 niveaux)

Les runs vivent sous `docs/tracking/runs/` (repertoire gitignore, memoire de
travail operateur, voir R25) :

```
docs/tracking/runs/
  <categorie>/                         niveau 1 : skynet | campaigns | agents | discovery | recette-full
    <YYYY-MM-DDTHH-MM-SS>_<group-id>/  niveau 2 : groupe = un lancement / batch
      _group.json                      meta du groupe : euro-date, label, liste des runs, statut
      <run-id>/                        niveau 3 : run individuel
        meta.json                      id, kind, euro-date, statut, artefacts + sha256, root_hash, replay_of
        annotations.json               couche MUTABLE : tags, comment, label, retention
        artifacts/                     surfaces FIGEES une fois scellees (*.jsonl, *.json)
        replay.json                    descripteur de replay si le run est rejouable
  latest/<categorie> ->  ...           lien symbolique vers le groupe le plus recent (retro-compat)
```

Une mega-campagne SKYNET est un **groupe unique** contenant autant de runs que
d'agents lances. Les categories reconnues sont : `skynet`, `campaigns`, `agents`,
`discovery`, `recette-full`.

### Euro-date comme metadonnee operationnelle

L'euro-date (`YYYY-MM-DDTHH-MM-SS`) est une metadonnee **operationnelle** (horloge
murale), analogue au `created_at` des runs existants dans `recette/api/runs.py`
(regle maf-standard). Elle n'entre jamais dans un chemin de decision ou de replay
-- le registry ne lit jamais l'horloge de lui-meme ; l'euro-date est passee en
parametre par l'appelant (I4).

## Comment un run est scelle (chaine sha256)

A la fin de son execution, le producteur (runner) scelle le run :

1. Calcul d'un `sha256` par artefact dans `artifacts/`.
2. Concatenation des hashes ordonnes par nom de fichier puis hachage en chaine
   (`root_hash`). Meme logique que `scripts/export_anssi_bundle.py` (fonctions
   `_sha256` / `_chain`).
3. `meta.status` passe a `"sealed"`, les champs `artifacts[].sha256` et
   `root_hash` sont persistes dans `meta.json`.

Le `root_hash` est **infalsifiable** a posteriori : modifier un artefact change
son sha256, donc le root_hash, donc la comparaison echoue. Un run scelle est
tamper-evident.

## Semantique CRUD et reconciliation I1 / R25 (point critique)

| Operation | Ce qui mute | Ce qui reste fige |
|-----------|-------------|-------------------|
| Lecture (`GET`) | -- | tout |
| Annotation (`PATCH`) | `annotations.json` uniquement | `meta.json`, `artifacts/*` inchanges |
| Suppression (`DELETE`) | archive le repertoire du run en `.tar.gz`, puis purge | l'archive reste dans `docs/tracking/runs/_archive/` |
| Replay (`POST .../replay`) | cree un NOUVEAU run euro-date | run parent inchange |

**Reconciliation avec I1 :** les artefacts et le `root_hash` dans `meta.json`
sont traites comme figés (meme principe que l'event store append-only). La seule
couche mutable est `annotations.json` (tags, commentaire, label, retention) -- le
U dans CRUD. La suppression est licite parce que `docs/tracking/` est une **memoire
de travail gitignore** (R25), pas le store d'evenements audite et committe (qui
reste, lui, append-only I1). Un DELETE n'efface jamais un evenement de l'event
store -- il archive et purge une copie de travail locale.

## Replay -- recompute pur, jamais un appel live

Un run est rejouable si son `kind` dispose d'un replayer :

| Kind | Replayer |
|------|----------|
| `scorecard` / `govscore` | `recette_govscore.py` -- recompute pur des scores |
| `agent` | `recette agent replay <recording>` avec `ReplayLlm` -- zero cle, zero appel reseau |
| `exchange` | Re-passage du lab mock deterministe + comparaison `proxy_traces` |

Le replay **ne mute jamais le run parent**. Il cree un run enfant euro-date dont
`meta.replay_of` pointe sur le parent. Le replay est une **fonction pure** :
meme (artefact, version de policy) => resultat identique (I4).

Les kinds sans replayer enregistre retournent une erreur `422 not replayable`.

## Surface API `/results` (JSON brut, sans enveloppe)

L'API est du JSON brut -- aucune enveloppe `{success, data}` (coherent avec
`console/src/api/client.ts`).

| Verbe + chemin | Role |
|----------------|------|
| `GET /results/tree` | arborescence categorie > groupe > run |
| `GET /results/{id}` | meta + annotations + liste des artefacts |
| `GET /results/{id}/artifact/{name}` | octets bruts de l'artefact (vers Monaco) |
| `POST /results` | enregistrer un run ou groupe (appele par les runners) |
| `PATCH /results/{id}` | mettre a jour `annotations.json` (tags/comment/label/retention) |
| `DELETE /results/{id}?confirm=true` | archiver puis purger le run (confirm obligatoire) |
| `POST /results/{id}/replay` | spawner un run enfant euro-date avec `meta.replay_of` |

Protection contre la traversee de chemin : le nom d'artefact est resolu contre
le `realpath` du repertoire `artifacts/` du run ; toute tentative d'echappement
retourne `400`.

Le prefix `/results` est utilise (et non `/runs`) car `/runs` est deja occupe
par `recette/api/routers/runs.py` (lancement / arret d'agent).

La racine du registry est configuree par la variable d'environnement
`INSPECT_IA_AGENTS_RUNS_ROOT` (defaut : `docs/tracking/runs/`) -- jamais en dur
dans le code (R5).

## Interface console -- route `/runs`

La page est accessible depuis la navigation principale sous le lien **Runs**.

### Volet gauche -- arborescence

Un composant `RunTree` recursif affiche la hierarchie :

```
skynet
  2026-06-25T14-30-00_megacamp  [sealed, 12 runs]
    agent-1  [sealed]
    agent-2  [sealed]
    ...
campaigns
  2026-06-25T09-00-00_sec-1
    run-1    [sealed]
```

Chaque noeud porte un badge de statut (`running` / `sealed`) et une icone de
kind. Cliquer un run le charge dans le volet droit.

### Volet droit -- Monaco + onglets

| Onglet | Contenu |
|--------|---------|
| Content | Monaco (lecture seule, json/jsonl) sur l'artefact selectionne |
| Meta | id, euro-date, kind, sha256 par artefact, root_hash, parent_group, replay_of |
| Annotations | tags, commentaire, label, retention -- editables (PATCH) |
| Replay | bouton de replay + descripteur ; lien vers le run enfant cree |

Controles CRUD : renommer/tagger/retention (PATCH), supprimer (DELETE, dialogue de
confirmation), rejouer (POST). Chargement paresseux de l'artefact a la selection
(safe sur de grands JSONL). Null-guard sur chaque fetch : un run en cours d'ecriture
s'affiche sans crash.

## Immutabilite vs annotations -- regle a retenir

- `artifacts/` et les champs sha256/root_hash de `meta.json` : **figés, jamais
  modifies** apres le scellement.
- `annotations.json` : **mutable** -- la seule couche de metadonnees que les
  chercheurs peuvent enrichir (tags de classification, notes, politique de
  retention).
- Supprimer un run (`DELETE`) archive la copie de travail locale -- cela
  n'affecte en rien l'event store audite committe.

## Voir aussi

- `docs/plans/2026-06-25-runs-explorer-design.md` -- design de reference.
- `docs/plans/2026-06-25-runs-explorer.md` -- plan d'implementation (Tasks 1-13).
- `.claude/rules/agentic-traceability.md` (R25) -- `docs/tracking/` gitignore,
  memoire de travail, jamais committe.
- `.claude/rules/recette-and-test-constraints.md` (R20) -- gates de recette.
- `docs/runbooks/platform.md` -- lancement des services via `./recette.sh`.
