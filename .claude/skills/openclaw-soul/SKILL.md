---
name: openclaw-soul
description: >
  Creer ou mettre a jour les fichiers SOUL.md des agents OpenClaw de l'equipe LIA-Scan.
  Utiliser quand : modifier le comportement d'un agent Matrix (HERMES, ARGUS, SIGMA-PRIME,
  ATLAS, FORGE-GO, FORGE-REACT, HAWK, NEXUS, PROBE, ORACLE), ajouter un gate obligatoire,
  activer ou desactiver exec, corriger une requete PostgreSQL dans un SOUL.md, changer le
  format de reponse, mettre a jour les technologies couvertes, ou creer un nouveau SOUL.md.
  Invoquer avec : /openclaw-soul [agent] [action] (ex: /openclaw-soul hermes fix-gate,
  /openclaw-soul argus add-exec, /openclaw-soul atlas update-stack)
---

# Skill openclaw-soul

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_OPENCLAW_{AGENT}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Workflow

1. Lire le SOUL.md actuel de l'agent cible
2. Choisir l'archetype depuis `references/archetypes.md`
3. Pour toute requete PostgreSQL : copier depuis `references/postgres-schema.md`
4. Pour les chemins workspaces : verifier dans `references/openclaw-structure.md`
5. Ecrire le SOUL.md complet avec l'outil Write (ecrasement total)
6. Verifier R10 : zero emoji dans le fichier produit

## Chemins SOUL.md

```
~/.openclaw/workspace-lia-rd/SOUL.md          # HERMES
~/.openclaw/workspace-lia-recette/SOUL.md     # ARGUS
~/.openclaw/workspace-sigma-prime/SOUL.md     # SIGMA-PRIME
~/.openclaw/workspace-lia-architect/SOUL.md   # ATLAS
~/.openclaw/workspace-forge-go/SOUL.md        # FORGE-GO
~/.openclaw/workspace-forge-react/SOUL.md     # FORGE-REACT
~/.openclaw/workspace-lia-auditeur/SOUL.md    # HAWK
~/.openclaw/workspace-lia-compliance/SOUL.md  # NEXUS
~/.openclaw/workspace-probe/SOUL.md           # PROBE
~/.openclaw/workspace-oracle/SOUL.md          # ORACLE
```

## References

- `references/archetypes.md` : templates gate, exec patterns, format reponse par archetype
- `references/postgres-schema.md` : schema reel cve_nvd_data, requetes corrigees pret a copier
- `references/openclaw-structure.md` : mapping agents/workspaces/rooms, codes technologies LIA-Scan

## Regles obligatoires pour tout SOUL.md

- R10 : section "R10 - Reponses sans emojis" en fin de fichier, zero emoji partout
- Exec : TOUJOURS `env -u CLAUDECODE` avant tout appel claude CLI
- Exec : parametre `workdir` obligatoire, jamais `cd /path && commande`
- Exec : placeholders lisibles (CVE-XXXX-XXXXX, TECH), pas `$VAR` ambigu
- PostgreSQL : colonnes depuis `references/postgres-schema.md` (cvss_score, pas cvss_v3_score)
- Gate : agents exec autonomes ont un bloc GATE OBLIGATOIRE avant les responsabilites

## Validation post-ecriture

```bash
# Verifier absence emoji
grep -Pc "[\x{1F000}-\x{1FFFF}]|[\x{2600}-\x{27BF}]" ~/.openclaw/workspace-AGENT/SOUL.md
# Resultat attendu : 0
```
