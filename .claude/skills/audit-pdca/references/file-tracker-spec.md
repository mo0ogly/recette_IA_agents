# FILE_TRACKER.json — Specification v1.0

Standard de suivi fichier-par-fichier pour les workflows APEX, PDCA, et analyze-repo.
Chaque session produit un fichier `FILE_TRACKER.json` dans son repertoire de travail.

## Emplacement

| Skill | Chemin |
|-------|--------|
| APEX | `_alire/temp/apex/{task-id}/FILE_TRACKER.json` |
| PDCA | `pdca/{perimetre}/cycle_{N}/FILE_TRACKER.json` |
| analyze-repo | `_alire/tracking/TRACKER_ANALYZE_{REPO}_{DATE}.json` |

## Schema JSON

```json
{
  "schema": "lia-file-tracker-v1",
  "session": {
    "id": "apex-20260327-abc123",
    "skill": "apex|pdca|analyze-repo",
    "skill_version": "6.0",
    "task": "Human-readable task description",
    "scope": "cmd/sigma_web/discovery_*",
    "created_at": "2026-03-27T10:00:00Z",
    "updated_at": "2026-03-27T12:30:00Z",
    "status": "IN_PROGRESS|COMPLETED|ABANDONED|REMASTERED",
    "cycle": 1,
    "plan_ref": "_alire/tracking/PLAN_FOO_2026-03-27.md"
  },
  "stats": {
    "total": 12,
    "pending": 1,
    "in_progress": 2,
    "done": 8,
    "blocked": 0,
    "abandoned": 1,
    "remastered": 0
  },
  "files": [],
  "retex_checkpoints": [],
  "recovery": {}
}
```

## Champs `files[]`

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `id` | string | oui | Identifiant unique (`F001`, `F002`, ...) |
| `path` | string | oui | Chemin relatif du fichier (`cmd/sigma_web/foo.go`) |
| `type` | string | oui | Extension : `go`, `ts`, `tsx`, `py`, `yaml`, `json`, `sql`, `md`, `sh` |
| `status` | string | oui | Voir statuts ci-dessous |
| `priority` | string | non | `P0` (critique) / `P1` (haute) / `P2` (moyenne) / `P3` (basse) |
| `action` | string | oui | `CREATE`, `MODIFY`, `DELETE`, `AUDIT`, `REVIEW` |
| `phase` | string | oui | Phase APEX/PDCA en cours (`ANALYZE`, `PLAN`, `EXECUTE`, `VALIDATE`, `CHECK`, `ACT`) |
| `step` | string | non | Sous-etape (`E.1`, `A.2b`, `C.1`) |
| `agent` | string | non | Qui travaille dessus : `main`, `cve-research-agent`, `recipe-tester-agent`, etc. |
| `created_at` | string | oui | ISO 8601 date de premier ajout au tracker |
| `updated_at` | string | oui | ISO 8601 derniere mise a jour |
| `lines_before` | int | non | Nombre de lignes avant modification |
| `lines_after` | int | non | Nombre de lignes apres modification |
| `gate_passed` | bool | non | true si gate de validation passee |
| `commit` | string | non | Hash du commit qui inclut ce fichier |
| `notes` | string | non | Commentaire libre (what/why) |

## Statuts de fichier (Kanban)

```
PENDING --> IN_PROGRESS --> DONE
                |
                +--> BLOCKED --> IN_PROGRESS (unblock)
                |
                +--> ABANDONED (raison documentee dans notes)
                |
                +--> REMASTERED (repris dans un cycle suivant)
```

| Statut | Description |
|--------|-------------|
| `PENDING` | Identifie, pas encore touche |
| `IN_PROGRESS` | En cours de modification/audit |
| `DONE` | Modifie + gate passee + commite |
| `BLOCKED` | Bloque par une dependance ou un bug externe |
| `ABANDONED` | Abandonne (raison dans `notes`) |
| `REMASTERED` | Repris d'un cycle/session precedent, en cours de re-travail |

## Champs `retex_checkpoints[]`

Observations inline pendant le travail — patterns qui vont se reproduire et qu'on peut ameliorer.

| Champ | Type | Description |
|-------|------|-------------|
| `id` | string | `RX001`, `RX002`, ... |
| `phase` | string | Phase OODA/PDCA ou le pattern a ete observe |
| `step` | string | Sous-etape |
| `timestamp` | string | ISO 8601 |
| `pattern` | string | Nom court du pattern observe |
| `observation` | string | Ce qui s'est passe |
| `frequency` | string | `once`, `recurring`, `systematic` |
| `improvement` | string | Action d'amelioration proposee |
| `target` | string | `ADD_TO_SKILL`, `ADD_TO_HOOK`, `ADD_TO_PDCA_CHECK`, `DOCUMENT_ONLY` |
| `confidence` | string | `high`, `medium`, `low` |

## Champs `recovery`

Checkpoint pour reprendre une session interrompue.

| Champ | Type | Description |
|-------|------|-------------|
| `last_completed_step` | string | Derniere etape terminee avec succes |
| `next_step` | string | Prochaine etape a executer |
| `checkpoint_at` | string | ISO 8601 du dernier checkpoint |
| `context` | string | Contexte libre pour le prochain agent qui reprend |
| `blocked_by` | string | Si bloque, qu'est-ce qui bloque |
| `uncommitted_files` | array | Liste des fichiers modifies non commites |

## Protocole de recovery

Quand un agent reprend une session (`/apex -r {id}` ou nouveau cycle PDCA) :

1. Lire `FILE_TRACKER.json` du repertoire de travail
2. Parser `recovery.last_completed_step` et `recovery.next_step`
3. Lister les fichiers avec `status != DONE` — ce sont les fichiers restants
4. Lister les fichiers `BLOCKED` — verifier si le blocage est leve
5. Lire `recovery.context` — resume de l'etat au moment de l'interruption
6. Reprendre depuis `recovery.next_step`

## Protocole RETEX

En fin de session, scanner `retex_checkpoints[]` :

1. Grouper par `target` (ADD_TO_SKILL, ADD_TO_HOOK, etc.)
2. Pour chaque checkpoint `ADD_TO_SKILL` : ouvrir le SKILL.md concerne et ajouter le check
3. Pour chaque checkpoint `ADD_TO_HOOK` : proposer un hook dans `.claude/hooks/`
4. Pour chaque checkpoint `ADD_TO_PDCA_CHECK` : ajouter dans SCORING_CONFIG.json
5. Pour `DOCUMENT_ONLY` : inclure dans A_RETEX.md / 09-finish.md

## Operations sur le tracker

### Initialisation (debut de session)

```bash
# Generer le FILE_TRACKER.json initial
cat > FILE_TRACKER.json << 'EOF'
{
  "schema": "lia-file-tracker-v1",
  "session": {
    "id": "SKILL-YYYYMMDD-HASH",
    "skill": "apex",
    "skill_version": "6.0",
    "task": "...",
    "scope": "...",
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "status": "IN_PROGRESS",
    "cycle": null,
    "plan_ref": null
  },
  "stats": {"total":0,"pending":0,"in_progress":0,"done":0,"blocked":0,"abandoned":0,"remastered":0},
  "files": [],
  "retex_checkpoints": [],
  "recovery": {"last_completed_step":"INIT","next_step":"ANALYZE","checkpoint_at":"ISO8601","context":"Session initialized"}
}
EOF
```

### Mise a jour d'un fichier

A chaque modification, mettre a jour l'entree dans `files[]` :
- `status` : changer selon l'action
- `updated_at` : horodater
- `gate_passed` : true apres validation gate
- `commit` : hash du commit qui l'inclut

### Checkpoint (avant pause ou interruption)

Mettre a jour `recovery` avec l'etat courant :
- `last_completed_step` : derniere etape terminee
- `next_step` : ce qui reste a faire
- `context` : resume en 1-2 phrases
- `uncommitted_files` : liste des fichiers modifies non commites

### Finalisation (fin de session)

1. Mettre `session.status` a `COMPLETED` ou `ABANDONED`
2. Calculer `stats` finales
3. Mettre a jour `session.updated_at`
4. Scanner `retex_checkpoints` et executer le protocole RETEX
