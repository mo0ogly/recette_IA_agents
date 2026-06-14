# Agentic Core -- Socle commun APEX & PDCA v6.0

> Reference partagee. Ne pas dupliquer dans les SKILL.md -- les referencer.

---

## 1. Memoire 3 niveaux

### Niveau 1 : Memoire de travail (session)

Fichiers produits pendant la session, perdus si pas commites.

| Artefact | PDCA path | APEX path | Format |
|----------|-----------|-----------|--------|
| action_journal.jsonl | `pdca/{perimetre}/cycle_{N}/` | `_alire/temp/apex/{task-id}/` | 1 JSON/ligne par action |
| FILE_TRACKER.json | idem | idem | Kanban fichiers |
| manifeste.jsonl | idem | idem | Trace fichiers produits |
| swarm_memory.json | idem | idem | Memoire partagee inter-agents |
| C_SCORECARD.json | idem | -- | Scores par domaine (PDCA) |

**action_journal.jsonl schema :**
```json
{
  "timestamp": "ISO8601",
  "session": "pdca-{perimetre}-{cycle} | apex-{YYYYMMDD}-{slug}",
  "phase": "PLAN|THINK|DO|CHECK|ACT|FINALIZE | INIT|OBSERVE|THINK|BUILD|RECETTE|COMPLETE",
  "step": 3,
  "agent_role": "COLLECTOR|ANALYST|PLANNER|EXECUTOR|MEMORY|LIBRARIAN",
  "action": "EDIT_FILE|CREATE_FILE|RUN_BUILD|RUN_TEST|DELEGATE_AGENT|REPLAN|LOG_DECISION|RESEARCH_CODEBASE|RESEARCH_WEB|EVALUATE_ALTERNATIVE|ADVERSARIAL_CRITIQUE",
  "tool": "Read|Edit|Write|Bash|Grep|Glob|Agent|WebSearch|WebFetch|manual",
  "input": "file:line ou commande",
  "output": "resume du resultat",
  "autonomy": "AUTONOMOUS|SUPERVISED",
  "approval": "user_confirmed|user_rejected|N/A",
  "security": "CLEAR|ALERT:type",
  "status": "success|partial|failure",
  "file": "path ou null"
}
```

**Quand logger :** File create/modify/delete, build/test execution, agent delegation, gate pass/fail, replanification, score calculations, commit, research actions, alternative evaluations.

**Quand NE PAS logger :** File reads pendant exploration, grep sans resultat, raisonnement interne, formatage.

**FILE_TRACKER.json schema :**
```json
{
  "schema": "lia-file-tracker-v1",
  "session": {
    "id": "apex-20260402-slug | pdca-grc-001",
    "skill": "apex|pdca",
    "skill_version": "6.0",
    "task": "description",
    "scope": "crates/gateway/src/discovery/*",
    "status": "IN_PROGRESS|COMPLETED|ABANDONED|REMASTERED",
    "cycle": 1,
    "plan_ref": "_alire/tracking/PLAN_*.md"
  },
  "stats": {
    "total": 12, "pending": 1, "in_progress": 2,
    "done": 8, "blocked": 0, "abandoned": 1, "remastered": 0
  },
  "files": [
    {
      "id": "F001", "path": "crates/gateway/src/foo.rs",
      "type": "rust", "status": "PENDING|IN_PROGRESS|DONE|BLOCKED|ABANDONED|REMASTERED",
      "priority": "P0|P1|P2|P3",
      "action": "CREATE|MODIFY|DELETE|AUDIT|REVIEW",
      "phase": "EXECUTE|BUILD|CHECK", "step": "E.1",
      "agent": "main|cve-research-agent|...",
      "created_at": "ISO8601", "updated_at": "ISO8601",
      "lines_before": 0, "lines_after": 145,
      "gate_passed": true, "commit": "abc1234",
      "notes": "what/why"
    }
  ],
  "retex_checkpoints": [
    {
      "id": "RX001", "phase": "BUILD", "step": "3",
      "timestamp": "ISO8601",
      "pattern": "nom court",
      "observation": "ce qui s'est passe",
      "frequency": "once|recurring|systematic",
      "improvement": "action proposee",
      "target": "ADD_TO_SKILL|ADD_TO_HOOK|ADD_TO_PDCA_CHECK|DOCUMENT_ONLY",
      "confidence": "high|medium|low"
    }
  ],
  "recovery": {
    "last_completed_step": "BUILD",
    "next_step": "RECETTE",
    "checkpoint_at": "ISO8601",
    "context": "resume libre",
    "blocked_by": "null ou description",
    "uncommitted_files": ["path1"]
  }
}
```

**Statuts fichier (Kanban) :**
```
PENDING --> IN_PROGRESS --> DONE
                |
                +--> BLOCKED --> IN_PROGRESS (unblock)
                +--> ABANDONED (raison dans notes)
                +--> REMASTERED (repris cycle suivant)
```

### Niveau 2 : Memoire longue (inter-sessions)

Fichiers persistants, commites, lisibles par les prochaines sessions.

| Artefact | Chemin | Role |
|----------|--------|------|
| RETEX | `_alire/02_LOGS/Journals/retex/RETEX_{SKILL}_{DATE}.md` | Ce qui a marche/echoue |
| decision_log.jsonl | `_alire/02_LOGS/Journals/decision_log.jsonl` | Decisions non-triviales (append-only) |
| DASHBOARD.md | `pdca/{perimetre}/DASHBOARD.md` | Progression multi-cycles |
| SCORING_CONFIG.json | `pdca/{perimetre}/SCORING_CONFIG.json` | Config scoring evolutive |
| A_IMPROVEMENTS.md | `pdca/{perimetre}/cycle_{N}/A_IMPROVEMENTS.md` | Ameliorations cycle N+1 |
| PLAN_*.md | `_alire/tracking/PLAN_{APEX|PDCA}_{NAME}_{DATE}.md` | Plans persistants |
| INDEX.md | `_alire/tracking/INDEX.md` | Index plans et RETEX |
| .claude/memory/ | `/home/liadev/.claude/projects/.../memory/` | Feedback utilisateur |

**decision_log.jsonl schema :**
```json
{
  "timestamp": "ISO8601",
  "session": "apex-slug | pdca-perimetre-cycle",
  "action": "VERBE_COURT",
  "reasoning": "pourquoi ce choix",
  "alternatives_rejected": ["option B rejetee car..."],
  "outcome": "resultat",
  "confidence": "high|medium|low",
  "plan_ref": "PLAN_*.md ou null"
}
```

**Protocole au demarrage :**
1. Charger `DASHBOARD.md` du meme perimetre (si existe)
2. Lire dernier `RETEX_{SKILL}_*.md` du meme domaine
3. Lire `A_IMPROVEMENTS.md` du cycle N-1 (PDCA)
4. Appliquer les ameliorations identifiees
5. NE PAS repeter les erreurs documentees

### Niveau 3 : Action Journal (audit trail, append-only)

Chaque action significative tracee. Non modifiable. Sert de preuve.

**Manifeste JSONL (fin de session) :**
```json
{
  "timestamp": "ISO8601",
  "file": "crates/gateway/src/foo.rs",
  "action": "CREATED|MODIFIED|DELETED|DISABLED",
  "phase": "BUILD|EXECUTE",
  "loc": 145,
  "status": "FINAL|DRAFT|REJECTED",
  "gate": "build_pass|test_pass|manual_review",
  "domain": "security|testing|..."
}
```

**Protocole RETEX sur retex_checkpoints[] :**
1. Grouper par `target`
2. `ADD_TO_SKILL` -> ouvrir SKILL.md et ajouter le check
3. `ADD_TO_HOOK` -> proposer hook dans `.claude/hooks/`
4. `ADD_TO_PDCA_CHECK` -> ajouter dans SCORING_CONFIG.json
5. `DOCUMENT_ONLY` -> inclure dans RETEX

**Recovery (resume) :**
```
Agent reprend -> Lit FILE_TRACKER.json ->
  recovery.last_completed_step
  recovery.next_step
  recovery.context
  recovery.uncommitted_files
  files[status != DONE] = fichiers restants
  files[status == BLOCKED] = verifier si debloque
-> Reprend depuis next_step
```

---

## 2. Perimetre d'autonomie

| Action | Autonome | Escalade |
|--------|----------|----------|
| Lire/explorer code | OUI | - |
| Editer fichier dans scope | OUI | - |
| Creer nouveau fichier | OUI | - |
| Creer fichier de test | OUI | - |
| Build + vet + test | OUI | - |
| Commit (conventionnel) | OUI | - |
| Push | OUI (max 5 non pushes) | - |
| Lancer agents brainstorm | OUI | - |
| Modifier auth/securite | NON | Toujours escalader |
| DDL (ALTER/CREATE TABLE) | NON | Toujours escalader |
| Supprimer fichier/code | NON | Toujours escalader |
| >10 fichiers en 1 batch | NON | Demander confirmation |
| Deployer en production | NON | Toujours escalader |

---

## 3. Model Selection Strategy

| Tache | Modele | Parametre |
|-------|--------|-----------|
| Exploration (Glob/Grep/Read) | **haiku** | `model: "haiku"` |
| Compliance (grep patterns) | **haiku** | `model: "haiku"` |
| Dead code (grep + count) | **haiku** | `model: "haiku"` |
| Documentation (file presence) | **haiku** | `model: "haiku"` |
| Code review OWASP | **sonnet** | `model: "sonnet"` |
| Architecture review | **sonnet** | `model: "sonnet"` |
| UX review | **sonnet** | `model: "sonnet"` |
| Code generation | **sonnet** | `model: "sonnet"` |
| Adversarial critique | **sonnet** | `model: "sonnet"` |
| Orchestration APEX/PDCA | **opus** | herite du parent |

**Regle de selection automatique :**
```
SI domaine contient "compliance|documentation|naming|formatting|dead_code|coverage|presence" :
  model: "haiku"
SI domaine contient "security|owasp|architecture|testing|benchmark|ux|performance|code_quality" :
  model: "sonnet"
SINON :
  model: "sonnet"  # defaut safe
```

**JAMAIS un agent haiku-eligible sur opus. JAMAIS deleguer opus a un agent.**

Cout relatif : haiku ~x1, sonnet ~x5, opus ~x25.

---

## 4. Pre-flight checks

```bash
# Rust build
cargo build --release 2>&1 | grep -E "Compiling|Finished|error"

# Backend health
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/api/health

# Rust lint
cargo clippy --all-targets --all-features -- -D warnings 2>&1 | grep -c '^warning'

# React build (si frontend dans le scope)
cd inspect_ia_agents-console && node node_modules/.bin/vite build 2>&1 | tail -1

# PostgreSQL (si DB dans le scope)
PGPASSWORD="$INSPECT_IA_AGENTS_DB_PASS" psql -h localhost -U inspect_ia_agents -d inspect_ia_agents -c "SELECT 1" 2>/dev/null
```

Si FAIL : STOP, fixer. Exception : si le perimetre EST le composant casse.

**Test pre-flight (WARN, pas BLOCK) :**
```bash
cargo test 2>&1 | grep -E "FAILED|test result: FAILED"
```
Noter les fails pre-existants pour ne pas les compter comme regressions.

---

## 5. Score agentique /50

| Critere | /10 | Description |
|---------|-----|-------------|
| C1 Decomposition | /10 | Sous-taches 3-7, complexite scoree, dependances explicites |
| C2 Planification (inclut THINK) | /10 | Plan cree, research effectuee, 2+ alternatives evaluees, critique adversariale, decision tracee |
| C3 Replanification | /10 | REPLAN declenche sur FAILURE, 2+ alternatives generees, jamais meme action |
| C4 Outillage | /10 | Model haiku/sonnet par tache, skills invoquees correctement, agents delegues efficacement |
| C5 Tracabilite | /10 | action_journal + decision_log + RETEX affiche + swarm_memory + FILE_TRACKER |

**C2 en v6.0** est plus exigeant : pour avoir 10/10 il faut :
- Research codebase effectuee (existant cherche, patterns similaires identifies)
- 2+ alternatives architecturales evaluees avec pros/cons/effort
- Critique adversariale du plan integree (agent Plan sonnet)
- Decision tracee dans decision_log.jsonl avec alternatives_rejected

Un simple "j'ai cree un plan" sans research/alternatives/critique = max 4/10 sur C2.
