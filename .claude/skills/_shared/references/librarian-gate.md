# Librarian Gate -- Reference partagee APEX & PDCA v6.0

> Checklist BLOQUANTE en fin de cycle. Aucun commit final sans toutes les cases cochees.

---

## Checklist (BLOQUANTE)

```
[ ] 1. PLAN A JOUR     : _alire/tracking/PLAN_{APEX|PDCA}_{NAME}_{DATE}.md (Status: TERMINE)
[ ] 2. RETEX ECRIT     : _alire/02_LOGS/Journals/retex/RETEX_{SKILL}_{DATE}.md
[ ] 3. RETEX AFFICHE   : contenu du RETEX AFFICHE dans la conversation (pas juste ecrit en fichier)
[ ] 4. TRACEABILITY GATE (BLOQUANT, c54+) :
                         python3 /opt/inspect_ia_agents/dev/scripts/verify_cycle_traceability.py \
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
[ ] 9. DOCS-SITE (SI DOC MODIFIEE) : Si un .md a ete cree/modifie sous docs/ (hors
                         docs/plans, docs/tracking, docs/screenshots, exclus du site) :
                         ./recette.sh docs-build  (Docusaurus build des DEUX locales fr+en)
                         Sortie REQUISE : "[SUCCESS] Generated static files" (build/ = fr,
                         build/en = en) + "docs-build OK". Le site surface docs/ (runbooks +
                         architecture + ADR + provenance) ; pas de rsync/VPS dans ce repo.
                         i18n : docs/ = source fr (defaut) ; le miroir anglais vit dans
                         docs-site/i18n/en/docusaurus-plugin-content-docs/current/ (1:1).
                         Une doc fr nouvelle/modifiee doit AUSSI etre repercutee dans le
                         miroir en (sinon /en/docs sert la version fr ou 404).
[ ] 9b. DIAGRAMMES (SI MERMAID ARCHITECTURE.md MODIFIE) : les blocs mermaid de
                         docs/ARCHITECTURE.md sont GENERES (source unique Python). Ne jamais
                         editer le mermaid a la main (il serait ecrase). Editer
                         scripts/diagrams/architecture.py (labels fr) ; pour un label
                         nouveau/modifie, ajouter la paire fr->en dans
                         scripts/diagrams/architecture_i18n.py ; puis :
                         python3 scripts/gen_diagrams.py --write   (reinjecte fr + en)
                         python3 scripts/gen_diagrams.py --check    (gate de drift, exit 0
                         requis : "in sync: N diagrams x 2 locales (fr, en)").
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

RETEX traceability gap :
- Plusieurs cycles marathon ont produit du travail reel SANS produire PLAN+RETEX ;
  seule la trace forensique (audit-block grep) a permis une reconstruction retroactive.
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
