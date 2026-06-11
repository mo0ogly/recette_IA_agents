# Swarm Memory Protocol v1.0

> Memoire partagee entre agents lances en parallele par APEX ou PDCA.

---

## Artefact : swarm_memory.json

| Skill | Chemin |
|-------|--------|
| PDCA | `pdca/{perimetre}/cycle_{N}/swarm_memory.json` |
| APEX | `_alire/temp/apex/{task-id}/swarm_memory.json` |

---

## Schema JSON

```json
{
  "schema": "lia-swarm-memory-v1",
  "session": "pdca-grc-001-20260410 | apex-20260410-slug",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",

  "context": {
    "objective": "Audit GRC module | Implement export CSV",
    "scope": "crates/gateway/src/grc/ + agentrail-console/src/components/grc/",
    "retex_previous": "Score 72/100, gaps: missing tests, 3 SQLi patterns",
    "known_issues": [
      "discovery.rs a 0 tests (RETEX cycle 3)",
      "input validation manquante dans 2 handlers (RETEX cycle 3)"
    ],
    "files_inventory": {
      "crates/gateway/src/grc/campaign.rs": {"loc": 450, "tests": false, "last_modified": "2026-04-08"},
      "crates/gateway/src/grc/dashboard_config.rs": {"loc": 280, "tests": true, "last_modified": "2026-04-05"}
    }
  },

  "swarm_context_sheet": {
    "parent_behavior": "auto-refresh 30s, error handling centralized",
    "ui_patterns": {
      "error": "<Alert severity='error'>",
      "loading": "CircularProgress",
      "empty": "Typography variant='body2'",
      "feedback": "Snackbar success"
    },
    "mandatory_checklist": [
      "HelpButton component+tabKey (pas helpId)",
      "borderRadius: 1 sur Chip",
      "fontFamily: 'inherit'",
      "customLogger (pas console.log)",
      "fetchWithConfig (pas fetch brut)",
      "MUI Grid v7 size={{ xs: 12, md: 8 }}"
    ],
    "shared_state_contract": "description des props parent, callbacks, ce que l'agent NE doit PAS reimplementer"
  },

  "discoveries": [
    {
      "agent": "security",
      "timestamp": "ISO8601",
      "type": "FINDING|BLOCKER|INFO",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "file": "crates/gateway/src/grc/campaign.rs",
      "line": 145,
      "description": "SQL injection via fmt.Sprintf in handleListCampaigns",
      "impacts_domains": ["security", "architecture"]
    }
  ],

  "file_locks": [
    {
      "file": "crates/gateway/src/grc/campaign.rs",
      "locked_by": "fix-agent-security",
      "since": "ISO8601",
      "reason": "Fixing SQLi B1",
      "status": "LOCKED|RELEASED"
    }
  ],

  "agent_status": [
    {
      "agent": "security",
      "domain": "security",
      "model": "sonnet",
      "status": "PENDING|RUNNING|DONE|FAILED|TIMEOUT",
      "score": null,
      "started_at": "ISO8601",
      "completed_at": null,
      "report_path": null
    }
  ]
}
```

---

## Protocole en 3 temps

### Temps 1 : PRE-LAUNCH (orchestrateur)

L'orchestrateur prepare `swarm_memory.json` AVANT de lancer les agents :

1. Creer avec :
   - `context.objective` (de la tache)
   - `context.retex_previous` (charge du RETEX N-1)
   - `context.known_issues` (extraites du RETEX N-1 et DASHBOARD.md)
   - `context.files_inventory` (LOC, tests, deps -- depuis l'inventaire Phase OBSERVE/P)
   - `swarm_context_sheet` (conventions obligatoires)
   - `discoveries`: [] (vide)
   - `file_locks`: [] (vide)
   - `agent_status`: 1 entree par agent, status PENDING

2. Injecter dans CHAQUE prompt agent :
```
SHARED MEMORY: Lis {path}/swarm_memory.json au demarrage.
- context.known_issues = ne pas re-decouvrir ce qui est deja connu
- context.retex_previous = ne pas repeter les erreurs documentees
- swarm_context_sheet = conventions obligatoires
- discoveries[] = ce que les autres agents ont deja trouve

ECRIRE tes decouvertes dans ton rapport au format :
## Discoveries
- [FINDING|BLOCKER|INFO] [CRITICAL|HIGH|MEDIUM|LOW] file:line description (impacts: domain1, domain2)

L'orchestrateur integrera tes discoveries dans swarm_memory.json.
```

### Temps 2 : PENDANT L'EXECUTION (agents)

**Agents brainstorm (read-only) :**
- Lisent `swarm_memory.json` au demarrage
- Prennent en compte `known_issues` et `retex_previous`
- Ajoutent leurs `discoveries` dans leur rapport (format structure)
- NE MODIFIENT PAS `swarm_memory.json` directement (risque conflit)

**Agents fix (write) :**
- Lisent `file_locks[]` AVANT de modifier un fichier
- Si fichier locke par un autre agent : SKIP, signaler dans le rapport
- Demandent a l'orchestrateur de locker le fichier AVANT modification
- L'orchestrateur libere apres gate passee

### Temps 3 : POST-COLLECT (orchestrateur)

```
1. Collecter tous les rapports agents
2. Parser la section ## Discoveries de chaque rapport
3. Merger dans swarm_memory.json discoveries[]
4. Dedupliquer (meme file + meme description = 1 finding)
5. Croiser : si Agent A a un BLOCKER impactant le domaine d'Agent B,
   relancer Agent B avec la decouverte injectee (1 relance max)
6. Mettre a jour agent_status[] (DONE/FAILED + score + report_path)
7. Produire CONSOLIDATED.md avec discoveries unifiees
```

---

## Regles de concurrence

| Situation | Regle |
|-----------|-------|
| 2 agents lisent meme fichier (audit) | OK, pas de conflit |
| 2 agents veulent modifier meme fichier (fix) | file_locks : premier arrive, premier servi |
| 1 agent trouve un BLOCKER pour un autre domaine | Marquer impacts_domains, orchestrateur relance si necessaire |
| 1 agent echoue | Les autres continuent, agent_status mis a jour |
| Timeout agent | swarm_memory.json reste valide, agent marque TIMEOUT |
| Agent retourne 0 findings mais Health Scan montre des gaps | Flag pour review manuelle |

---

## Integration avec les autres memoires

| Memoire | Relation avec swarm_memory |
|---------|---------------------------|
| action_journal.jsonl | L'orchestrateur logge chaque DELEGATE_AGENT et chaque POST-COLLECT |
| FILE_TRACKER.json | Les file_locks sont coherents avec les statuts FILE_TRACKER |
| decision_log.jsonl | Le choix de relancer un agent apres BLOCKER = decision non-triviale |
| CONSOLIDATED.md | Produit depuis les discoveries de swarm_memory |
| C_SCORECARD.json | Les scores agents dans agent_status alimentent la scorecard |

---

## Difference v5.0 vs v6.0

**v5.0 (sans swarm_memory) :**
```
Agent Security: "3 SQLi trouvees"
Agent Testing:  "0 tests" (ne sait pas que Security a trouve des SQLi)
Agent Archi:    "code propre" (ne sait pas les deux autres)
Orchestrateur:  consolide 3 rapports independants, doublons
```

**v6.0 (avec swarm_memory) :**
```
Orchestrateur:  cree swarm_memory avec RETEX N-1 "3 SQLi cycle precedent"
Agent Security: lit known_issues, verifie si corrigees, trouve 1 nouvelle, ajoute discovery
Agent Testing:  lit context + discoveries, voit SQLi, verifie tests du handler
Agent Archi:    lit context + discoveries, note "handler non teste + vuln active"
Orchestrateur:  consolide, zero doublon, agents ont travaille avec le contexte
```
