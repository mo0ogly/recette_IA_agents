# Librarian Gate -- Reference partagee APEX & PDCA v6.0

> Checklist BLOQUANTE en fin de cycle. Aucun commit final sans toutes les cases cochees.

---

## Checklist (BLOQUANTE)

```
[ ] 1. PLAN A JOUR     : _alire/tracking/PLAN_{APEX|PDCA}_{NAME}_{DATE}.md (Status: TERMINE)
[ ] 2. RETEX ECRIT     : _alire/02_LOGS/Journals/retex/RETEX_{SKILL}_{DATE}.md
[ ] 3. RETEX AFFICHE   : contenu du RETEX AFFICHE dans la conversation (pas juste ecrit en fichier)
[ ] 4. TRACEABILITY GATE (BLOQUANT, c54+) :
                         python3 /opt/agentrail/dev/scripts/verify_cycle_traceability.py \
                           --scope {SCOPE_SLUG} --from-cycle {N} --to-cycle {N}
                         Exit 0 REQUIS (PLAN + RETEX presents pour le cycle courant).
                         Exit 1 (PARTIAL) ou 2 (MISSING_BOTH) sur le cycle courant = STOP commit
                         et completer le cycle. Cycle marathon legacy = exit 2 sur range
                         historique acceptable si TRACEABILITY_GAP_{slug}_{range}_{DATE}.md
                         document existe.
                         Reference incident : c53 c10-c14 traceability gap (5 cycles
                         marathon 2026-05-13 sans PLAN/RETEX, decouvert et documente
                         retroactivement).
[ ] 5. INDEX MAJ       : _alire/tracking/INDEX.md (ajouter plan + RETEX)
[ ] 6. DASHBOARD MAJ   : pdca/{perimetre}/DASHBOARD.md (si PDCA)
[ ] 7. DOC LIBRARIAN   : doc_classifier.py init + doc_librarian.py reindex (si doc creee)
[ ] 8. UI HELP (BLOQUANT) : INSERT ui_help_content + verify SELECT pour CHAQUE composant *Tab/*Panel/*Dashboard/*Editor/*Manager/*Status cree. Contenu 200-800 car., anglais (R8). HelpButton sans contenu DB = PLACEHOLDER INTERDIT (R4). Cycle NE PEUT PAS fermer si manquant.
[ ] 9. DOCS-SITE (SI DOC MODIFIEE) : Si un .md a ete cree/modifie dans _alire/01_DOCUMENTATION/ :
                         cd docs-site && npm run build:search (Docusaurus + Pagefind)
                         rsync -avz --delete docs-site/build/ /opt/agentrail/source/docs-site/
                         Verifier : curl -s -o /dev/null -w "%{http_code}" https://agentrail.example/docs/ = 200
[ ] 10. COMMIT PROPRE  : fichiers de session uniquement (pas git add -A)
                         Stager UNIQUEMENT les fichiers de la session
[ ] 11. PUSH           : max 5 commits non pushes
```

---

## Regles Go (skills qui produisent du code Go)

- **Noms de fonctions** : TOUJOURS prefixer avec le module (`treatmentTruncate`, pas `truncate`) pour eviter collisions avec 600+ fichiers Go
- **Imports** : verifier que CHAQUE import est utilise AVANT d'ecrire le fichier (le hook PostToolUse bloque sur import inutile)
- **Pre-commit** : stager uniquement les fichiers de la session. Les fichiers pre-existants avec hardcodings bloquent le hook `security_check.sh`

---

## Regles Doc (R15)

Si une documentation a ete creee dans `_alire/01_DOCUMENTATION/` :
1. VERIFIER si le doc existe deja : `find _alire/01_DOCUMENTATION/ -name "*{module}*"`
2. INITIALISER metadata : `python3 .claude/skills/doc-code/scripts/doc_classifier.py init {file} --type {TYPE}`
3. REINDEXER : `python3 .claude/skills/doc-code/scripts/doc_librarian.py reindex _alire/01_DOCUMENTATION/ -o _alire/01_DOCUMENTATION/INDEX.md`
4. Nommage obligatoire : `{module}_{type}_en.md` (type = api|arch|tech|user|sec|spec)

---

## Pourquoi cette gate existe

RETEX 2026-04-01 :
- Plans perdus dans `.claude/plans/` (jamais commites), RETEX eparpilles dans 2 repertoires
- Impossible de retrouver l'historique des 100+ cycles PDCA sans fouiller manuellement
- Sans cette gate, chaque session perd de l'information qui ne sera jamais retrouvee
- Les collisions de noms de fonctions Go (truncate, nilIfEmpty) ont cause 3 iterations de build
- Les fichiers owned par `ubuntu` sur le VPS bloquent git pull pendant 30+ minutes

RETEX 2026-05-13/14 (incident c53 traceability gap) :
- 5 cycles marathon (c10-c14, scope liaprobe-fingerprint-rebuild) ont produit du
  travail reel (2666 file renames c11, 36 rebrand audit blocks c13) SANS produire
  PLAN+RETEX. Trace forensique seule (audit-block grep) a permis reconstruction
  retroactive en c53.
- Sans gate verifiee par script, la discipline librarian-gate s'erode silencieusement
  pendant les sessions marathon. Le gate item 4 (TRACEABILITY GATE) est automatise
  via `scripts/verify_cycle_traceability.py` (exit 2 si gap consecutif detecte).
- APEX Phase 0 INIT execute aussi un scan HISTORIQUE preventif (cycles precedents
  du meme scope) pour surfacer les gaps anciens avant que le nouveau cycle commence.

---

## References

- Index consolide : `_alire/tracking/INDEX.md`
- Template plan : `_alire/tracking/PLAN_TEMPLATE.md`
- RETEX : `_alire/02_LOGS/Journals/retex/` (repertoire unique)
- Doc librarian : `.claude/skills/doc-code/scripts/doc_librarian.py`
- VPS ownership : `_alire/01_DOCUMENTATION/user-guides/vps_deployment_guide_user_en.md`
