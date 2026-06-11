# CHECK QUERIES -- Commandes et queries d'audit

> Ce fichier contient toutes les commandes grep/count, checks backend/frontend,
> et queries SQL utilisees dans les phases C.1 et C.2 du cycle PDCA.

## Checks securite automatiques (C.1)

| Check ID | Type | Query / Commande | Target | Scope |
|----------|------|-------------------|--------|-------|
| SEC-01 | grep_count | `grep -rnE "fetch\(['\"]https?://" {scope}/services/ --include="*.ts"` | 0 | Frontend -- fetch() avec URL hardcodee (base URL doit venir de la config, R5) |
| SEC-02 | grep_count | `grep -rn "localhost:8081" {scope}` | 0 | Tous -- URLs hardcodees |
| SEC-03 | grep_count | `grep -rn "console.log" {scope}/src/ --include="*.ts" --include="*.tsx"` | 0 | Frontend -- console.log (utiliser un logger structure, R6) |
| SEC-04 | grep_count | `grep -rn "println!\|eprintln!\|dbg!" {scope}/src/ --include="*.rs"` (exclure tests) | 0 | Backend -- logging via println au lieu de tracing |
| SEC-05 | grep_count | `grep -rnE "format!.*(SELECT\|INSERT\|UPDATE\|DELETE)" {scope} --include="*.rs"` | 0 | Backend -- SQL injection (dynamic query au lieu de bind params sqlx/diesel) |
| SEC-06 | command | `cargo audit 2>&1 \| grep -cE "Severity: (high\|critical)"` | 0 | Backend -- RUSTSEC advisories vulnerables (deps) |
| SEC-07 | grep_count | `grep -rn "dangerouslySetInnerHTML" {scope} --include="*.tsx" \| grep -v "DOMPurify"` | 0 | Frontend -- XSS sans DOMPurify |
| SEC-08 | grep_count | `grep -rnE "\.unwrap\(\)\|\.expect\(\|panic!" {scope}/src/ --include="*.rs"` (exclure tests + `// SAFETY`) | 0 | Backend -- panic sur chemin faillible (I1/failure-modes) |
| SEC-09 | adoption | `grep -rl "HelpButton" {scope}/*.tsx` vs `grep -rl "export default" {scope}/*.tsx` | 100% | Frontend -- composants sans HelpButton |
| SEC-10 | sql_count | `SELECT component, tab_key FROM ui_help_content WHERE component LIKE '{module}%'` | Toutes tabs couvertes | DB -- ecrans/tabs sans aide |

## Checks backend (C.2)

| Check ID | Type | Commande | Expected |
|----------|------|----------|----------|
| TST-01 | command | `cargo build 2>&1 \| tail -3` | exit 0 |
| TST-02 | command | `cargo clippy --all-targets --all-features -- -D warnings` | 0 warnings |
| TST-03 | count | `grep -rlE "#\[cfg\(test\)\]\|#\[test\]\|#\[tokio::test\]" {scope} --include="*.rs" \| wc -l` | > 10 |
| TST-04 | command | `cargo test` (ou `cargo nextest run` si dispo) | PASS |

## Checks frontend (C.2)

| Check ID | Type | Commande | Expected |
|----------|------|----------|----------|
| TST-05 | command | `cd agentrail-console && npm run build` | exit 0 |
| TST-06 | count | `find {scope} -name "*.test.ts" -o -name "*.test.tsx" \| wc -l` | > 10 |
| TST-07 | command | `cd agentrail-console && npm test -- --coverage --watchAll=false` (si tests existent) | PASS |

## Checks UI Help (C.1 -- BLOQUANT)

| Check | Query | Condition FAIL |
|-------|-------|----------------|
| Composants vs HelpButton | `grep -rl "export default" {scope}/*.tsx` vs `grep -rl "HelpButton" {scope}/*.tsx` | composants > HelpButton |
| Entrees EN en base | `SELECT count(*) FROM ui_help_content WHERE component LIKE '{module}%' AND language='en'` | count = 0 |
| Entrees FR en base | `SELECT count(*) FROM ui_help_content WHERE component LIKE '{module}%' AND language='fr'` | count = 0 |
| Parite EN/FR | Comparer les deux counts ci-dessus | EN != FR |
| HelpButton par tab | Pour chaque composant avec tabs : verifier que `HelpButton` a un `tabKey` dynamique | tabKey manquant ou statique |

## Checks pre-flight (P.0 -- BLOQUANT)

| Check | Commande | Condition FAIL |
|-------|----------|----------------|
| Rust build | `cargo build 2>&1 \| tail -1` | exit != 0 (erreur de compilation) |
| Rust lint | `cargo clippy --all-targets -- -D warnings 2>&1 \| grep -c "warning:"` | > 0 (warnings clippy) |
| React build | `cd agentrail-console && node node_modules/.bin/vite build 2>&1 \| tail -1` | Pas "built in" |
| PostgreSQL | `psql -U agentrail -d agentrail -c "SELECT 1" 2>/dev/null` | exit != 0 |
| Backend health | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/api/health` | != 200 (warning, pas bloquant si audit offline) |

## Checks dead code triage (C.0 -- OBLIGATOIRE)

| Check | Commande | Description |
|-------|----------|-------------|
| Warnings dead_code compilateur | `cargo build 2>&1 \| grep -E "never used\|dead_code"` | Liste symboles non utilises |
| Extraire symboles Rust | `grep -rnE "pub (fn\|struct\|enum\|trait) " {fichier}.rs \| sed -E 's/.*pub (fn\|struct\|enum\|trait) ([a-zA-Z0-9_]+).*/\2/'` | Liste symboles publics |
| Compter appels externes | `grep -rn "symbol_name" src/ --include="*.rs" \| grep -v {fichier}.rs \| wc -l` | 0 = dead code |
| Ratio dead code | `(fichiers 0 appels / fichiers total) * 100` | > 10% = FAIL (HYG-03) |

Classification :

| Categorie | Critere | Action |
|-----------|---------|--------|
| ACTIF | Symboles appeles ailleurs | Inclure dans scoring |
| PROTOTYPE | Code propre, routes commentees, 0 appels | Exclure, signaler |
| DEAD | 0 appels, code obsolete | Exclure, proposer .disabled |

## Checks code hygiene (C.1 -- domaine code_hygiene)

| Check ID | Type | Query / Commande | Target | Scope |
|----------|------|-------------------|--------|-------|
| HYG-01 | grep_count | `grep -rnE "todo!\(\)\|unimplemented!\(\)\|StatusCode::NOT_IMPLEMENTED" src/ --include="*.rs"` | 0 | Backend -- handlers stub / non implementes |
| HYG-02 | grep_count | `cargo build 2>&1 \| grep -cE "never used\|unused import\|unused variable"` | 0 | Backend -- code/imports morts (compilateur) |
| HYG-03 | dead_code_ratio | Script triage C.0 ci-dessus | < 10% | Backend -- ratio dead code |
| HYG-04 | grep_count | `grep -Prn '[\x{1F600}-\x{1F64F}\x{1F300}-\x{1F5FF}\x{1F680}-\x{1F6FF}]' src/ agentrail-console/src/` | 0 | Tous -- emoji |
| HYG-05 | grep_count | `grep -rn '<Grid item \|<Grid.*item ' agentrail-console/src/ --include="*.tsx"` | 0 | Frontend -- ancienne syntaxe MUI v5 |
| HYG-06 | grep_count | `grep -rn "fontFamily:.*'monospace'\|fontFamily:.*'Arial'" agentrail-console/src/components/ --include="*.tsx"` | 0 | Frontend -- polices hardcodees |
| HYG-07 | manual | `grep -rn 'Chip' agentrail-console/src/components/{perimetre}/ --include="*.tsx"` -> verifier borderRadius: 1 | Tous Chip = borderRadius: 1 | Frontend -- pas d'ovales |
| HYG-08 | grep_count | `grep -rn "mockData\|MOCK_\|fakeData\|dummyData\|lorem ipsum\|example\.com" src/ agentrail-console/src/` | 0 | Tous -- donnees fictives |

## Checks design quality (C.1 -- /frontend-design audit)

| Check | Description | Condition FAIL |
|-------|-------------|----------------|
| Design generique | Design generique/boilerplate AI ? | Oui = FAIL |
| Theme-aware | Couleurs via `useTheme`, pas hardcodees | Hardcode = FAIL |
| Responsive | `Grid size={{ xs, md, lg }}` (MUI v7) | Absent = FAIL |
| States | Loading/Error/Empty states presents | Manquant = FAIL |
| Accessibilite | aria-label, tooltips, contraste | Absent = FAIL |

## Checks recette AgentRail (C.2 -- si applicable)

| Check | Commande | Quand |
|-------|----------|-------|
| Recipe | `./validate_rules_recipe.sh {rule_dir}` | 41 checks |
| Ultimate | `./validate_rules_ultimate.sh {rule_dir}` | 91 checks |
| ReportRule | `./validate_reportrules.sh {rule_dir}/R-*.json` | 8 checks |

## Formule de scoring (C.3)

```
Pour chaque domaine :
  score_domaine = agent_score * (1 - penalite_secu - penalite_tests)
  score_pondere = score_domaine * weight / 100

score_global = SUM(score_pondere)

SI cycle > 1 :
  CHARGER cycle_{N-1}/C_SCORECARD.json
  CALCULER delta par domaine
  DETECTER regressions (score baisse > 5 points)
  CALCULER tendance (improving / stable / declining)
```
