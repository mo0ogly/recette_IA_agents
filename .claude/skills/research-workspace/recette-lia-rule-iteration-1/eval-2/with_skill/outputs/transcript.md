# Transcript - eval-2 : with_skill (recette-lia-rule)

## Contexte initial

Prompt utilisateur :
> "La recette retourne EXIT=1 CRITICAL sur une regle avec deux problemes :
> Phase 4 (qualite donnees test) : 5 cas seulement, requis >= 8.
> Phase 8 (references) : URL 'http://nvd.nist.gov/vuln/detail/CVE-2025-47812' non securisee (HTTP au lieu de HTTPS).
> Comment corriger dans le bon ordre ?"

Skill charge : `recette-lia-rule`

---

## Etape 1 : Lecture du SKILL.md

Le SKILL.md (`/home/mo0ogly/Bureau/vscode_lia_audit/.claude/skills/recette-lia-rule/SKILL.md`) decrit :
- 14 phases de validation Recipe
- Phase 4 : niveau HIGH (>= 8 cas de test)
- Phase 8 : niveau MEDIUM (URLs reelles, >= 2)
- EXIT codes : 0=PASS, 1=CRITICAL, 2=HIGH, 3=MEDIUM
- Priorite corrections : CRITICAL > HIGH > MEDIUM

---

## Etape 2 : Analyse des niveaux de severite

| Probleme | Phase | Niveau declare dans SKILL.md |
|----------|-------|------------------------------|
| 5 cas seulement (requis >= 8) | Phase 4 | HIGH |
| URL HTTP au lieu de HTTPS | Phase 8 | MEDIUM |

Observation critique : le retour utilisateur dit EXIT=1 CRITICAL. Or les deux phases
concernees sont HIGH et MEDIUM, pas CRITICAL. Cela signifie qu'il y a probablement
une TROISIEME cause produisant EXIT=1 (phase 1 ou phase 5, qui sont CRITICAL).
Toutefois, la question porte uniquement sur les corrections des deux problemes nommes.

Priorite d'execution des corrections selon la regle du skill :
CRITICAL > HIGH > MEDIUM

Donc :
1. Corriger Phase 4 FIRST (HIGH, le plus severe des deux problemes cites)
2. Corriger Phase 8 ENSUITE (MEDIUM)
3. Relancer la validation

---

## Etape 3 : Exploration des exemples de test_data existants

Fichiers lus pour identifier les patterns reels :

- `/home/mo0ogly/Bureau/vscode_lia_audit/lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/test_data.json`
  -> Format canonique avec ObjectClass, Hostname, Version, VersionNormalized, _expected_match, _test_description
  -> 16 cas (9 true + 5 false + 2 edge cases) : ratio 56% vulnerable, 44% safe
  -> ObjectClass = "WingFTPServer"

- `/home/mo0ogly/Bureau/vscode_lia_audit/lia_rules/rule_analysis/ADDS/VULN/CVE202521293/test_data.json`
  -> Format avec champs metier (GroupName, MemberType, MemberEnabled, IsPrivilegedAccount)
  -> _test_description presente comme description textuelle du cas
  -> 15 cas (8 true + 7 false) : ratio 53% vulnerable

- `/home/mo0ogly/Bureau/vscode_lia_audit/lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/A-S-WFTP-WingFTP-CVE-2025-47812.yml`
  -> references: utilise https://nvd.nist.gov/... (HTTPS, correct)
  -> Confirm : le schema reference est HTTPS obligatoire

---

## Etape 4 : Construction du plan de correction

### Correction 1 - Phase 4 (FIRST - HIGH)

Etat actuel : 5 cas -> il faut atteindre au minimum 8 cas.
Il faut ajouter 3 cas minimum. La recommandation est d'atteindre >= 10 cas (buffer)
pour eviter de retomber en phase 4 si un cas est retire.

Repartition cible (ratio 60/40 recommande dans le skill) :
- Minimum 8 cas, idealement 10-14
- >= 5 vrais positifs (_expected_match: true)
- >= 3 faux positifs (_expected_match: false)

Cas a ajouter (base sur CVE-2025-47812 / WingFTPServer) :
1. Version boundary exacte (dernier patch - SAFE)
2. Version anterieure additionnelle (VULNERABLE)
3. ObjectClass incorrect (SAFE - faux positif technique)

### Correction 2 - Phase 8 (ENSUITE - MEDIUM)

Etat actuel : `http://nvd.nist.gov/vuln/detail/CVE-2025-47812`
Correction : `https://nvd.nist.gov/vuln/detail/CVE-2025-47812`
Changement : `http://` -> `https://`

---

## Etape 5 : Relancement validation

Commande apres corrections :

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette
./recette_rule_cli/validate_rules_recipe.sh "$RULE_DIR"
```

Resultat attendu si les deux seuls problemes etaient phase 4 + phase 8 :
- Phase 4 : PASS (>= 8 cas)
- Phase 8 : PASS (HTTPS)
- EXIT global dependant des autres phases

---

## Etape 6 : Metriques

- Glob tool calls : 4
- Read tool calls : 6
- Bash tool calls : 2
- Write tool calls : 4
- Critical prioritized (Phase 4 FIRST) : true
- Concrete test cases : true (test_data_additions.json)
- URL fix provided : true
- Rerun command provided : true
