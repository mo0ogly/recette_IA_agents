# RETEX -- Recette par campagnes (scenarios BNP + couverture 118 actions)

Date : 2026-06-13
Perimetre : modele de campagne, scenarios BNP 5.2/5.3, couverture catalogue, skill
recette-campaign-builder, validation live Groq.
Invariants concernes : I1 (audit chain), I2 (mediation), I4 (replay deterministe), I6 (blocage approbation).

> Format : RETEX par VAGUES. Chaque vague = un increment livre + verifie. La derniere section
> est une PROCEDURE D'AUTO-AMELIORATION reutilisable pour les vagues suivantes.

---

## Vague 1 -- Analyse : 7 scenarios BNP -> modele de campagne

- **Fait** : cartographie de `recette/campaign.py` (deja existant), du catalogue 11 domaines (==
  11 domaines BNP), de l'engine de policy. Plan ecrit (`PLAN_APEX_bnp-7-scenarios-campaigns`).
- **Decouverte cle** : `PolicyRule.verdict` accepte ALLOW et l'engine le retourne -> ALLOW sur
  action sensible = **regle de bundle, zero modif moteur/catalogue**. Debloque 6/7 scenarios.
- **Contrainte dure** : `decide()` deny toute action absente du catalogue -> ALLOW/ESCALATE sur
  action neuve exigent de cataloguer d'abord ; DENY sur action inconnue passe gratis.
- **Lecon** : observer l'existant AVANT de concevoir. Le modele de campagne et le catalogue
  etaient deja la ; la tache etait du mapping data, pas un build from scratch.

## Vague 2 -- Champs d'aide dans le modele

- **Fait** : `objective` + `teaching` (campagne) + `rationale` (par action) dans `campaign.py`,
  rendus dans le report, valides type-only (non-bloquant). Pure doc, hors chemin de decision (I4 sauf).
- **Verifie** : 26 tests OK, ruff+mypy clean, render live affiche les champs.
- **Lecon** : un champ d'aide explicatif vit AVEC la data (le runner/API le sert), pas dans un
  doc separe a resynchroniser. Le verdict reste la verite ; l'aide explique, ne decide pas.

## Vague 3 -- 9 campagnes BNP (7 securite 5.2 + 2 business 5.3)

- **Fait** : `campaigns/bnp/sec-1..7` + `biz-8..9`, harness deterministe `run_bnp_scenarios.py`
  (catalogue etendu in-memory + bundle `bnp-v1`).
- **Verifie** : `ALL PASS -- 9 campaigns`, chaine d'audit intacte.
- **Lecons** :
  - **deny-by-default = feature** : scenario 6 (virement) passe sans aucune regle (role non-privilegie).
  - Verdicts contextuels (montant>5000, host partage) NON modelises -> assertes par `(role,action)`,
    contexte en `rationale`. Ne PAS ajouter de logique seuil (casserait I4).
  - Steps C4 omis (hors referentiel 118) -- sinon l'engine les deny (unknown->deny).

## Vague 4 -- Recette live Groq

- **Fait** : cle Groq -> `backend_secrets.json` (R8, secret store concu), `.env` supprime ;
  `run_bnp_live_all.py` (vrai modele propose, gateway gouverne, ToolSpecs construits depuis la
  campagne pour atteindre mcp/comms/compliance/github-gov).
- **Verifie** : 22/22 steps, 0 mismatch, 0 leak ; le modele manipule TENTE l'exfiltration, le
  gateway la refuse (these BNP prouvee live, I2/I5).
- **Lecons** :
  - Secret store **par backend** > `.env` (fallback). `api_key or env` -- la cle saisie gagne.
  - llama-3.3 **boucle** sur le 1er tool -> retirer le tool appele force la couverture.
  - Live = demo non-deterministe ; le deterministe reste la recette I4 rejouable.

## Vague 5 -- Skill `recette-campaign-builder` (+ OODA + eval)

- **Fait** : skill encodant tous les gotchas du moteur, mode autonome OODA bundle, eval 2 cas
  (4 subagents avec/sans skill), benchmark.
- **Verifie** : 100% pass des deux cotes ; skill ~21% plus rapide.
- **Lecons (honnetes)** :
  - Eval **non-discriminante** sur la correction : le repo contient deja des exemples worked, un
    baseline sonnet egale le skill. Gain mesure = vitesse + discipline, pas correction.
  - **Subagents peuvent committer** (un a fait `89ee5a2`). Verifier qu'aucun artefact temp ni
    fichier tiers n'a ete committe par erreur. Regle sandbox (noms uniques, pas d'edition de
    fichiers committes) indispensable en parallele.

## Vague 6 -- Couverture des 118 actions

- **Fait** : `gen_coverage_campaigns.py` lit le catalogue -> 11 campagnes (1/domaine, role
  privilegie, chaque action assertee a son `verdict_privileged`). Aucun EXTRA requis
  (`baseline_from_catalog` materialise deja les regles privilegiees).
- **Verifie** : deterministe **118/118 ALL PASS** ; live Groq **118/118** atteints, 0 mismatch, 0 leak.
- **REPLAN live** (2 alternatives a chaque fois) :
  1. `max_steps=6` plafonnait les domaines >6 actions -> max_steps derive de la taille de campagne.
  2. `invite_external_user` existe en okta ET slack -> le reverse-map global choisissait okta
     (MISMATCH). Fix : target depuis la campagne, pas un map global.
  3. Groq `tool_use_failed` (schema mal forme) crashait le run -> catch + retry (2) puis skip
     campagne, jamais abort global.
- **Lecon** : "112" etait une approximation de 118. **Verifier le chiffre** (compter le catalogue)
  avant d'agir (R13) -- aucune liste de 112 agents n'existait.

---

## PROCEDURE D'AUTO-AMELIORATION (reutilisable, boucle OODA)

A appliquer pour toute nouvelle vague de campagnes (extension corpus, nouveau domaine, nouvel outil).

```
OBSERVE  -> THINK -> ACT -> RECETTE -> LEARN -> (boucle)
```

1. **OBSERVE (verifier, pas supposer -- R13)**
   - Compter la cible reelle (`load_catalog()`, grep) ; ne jamais agir sur un chiffre approxime.
   - Lire l'existant : une action / un role / une regle est-il deja la ? (grep domaines, bundle).

2. **THINK (mapper avant d'ecrire)**
   - Pour chaque action : verdict attendu vs verdict catalogue par defaut. Classer :
     exists+match / exists+rule / missing+catalog / missing+deny-gratis.
   - Exploiter deny-by-default pour les DENY ; bundle rule pour les ALLOW ; EXTRA_SPECS pour les
     ESCALATE/ALLOW sur actions neuves. JAMAIS de logique seuil dans `decide()` (I4).

3. **ACT (data, pas moteur)**
   - Generer/ecrire les campagnes (1 scenario = 1 fichier, champs d'aide remplis).
   - Editer EXTRA_SPECS/EXTRA_RULES in-memory ; ne PAS toucher `catalog/domains/*.py` committes.

4. **RECETTE (2 niveaux, bloquant)**
   - Deterministe : `run_bnp_scenarios.py --dir <dir>` -> `ALL PASS`. C'est la verite I4.
     Un MISMATCH = mapping faux : corriger le bundle/catalogue, **jamais l'`expect`**.
   - Live Groq (optionnel, demo) : `run_bnp_live_all.py --dir <dir>` -> 0 mismatch, 0 leak.
   - Gates code : ruff + mypy + json valides.

5. **LEARN (capitaliser + auto-corriger l'outillage)**
   - Tout echec live recurrent = un fix d'outillage, pas un contournement ponctuel
     (ex : boucle llama -> tool-removal ; ambiguite cross-domaine -> target-from-campaign ;
     flakiness provider -> retry+skip). Le harness s'ameliore a chaque vague.
   - Mettre a jour ce RETEX (nouvelle vague) et le skill `recette-campaign-builder` si un gotcha
     nouveau apparait (le skill est la memoire long-terme du "comment").
   - Garde-fous permanents : aucun secret committe (`git diff --cached`), aucun fichier tiers
     stage, subagents en sandbox (noms uniques, pas d'edition de committes).

### Criteres de COMPLETE d'une vague
- [ ] Chiffre cible verifie par commande (pas suppose).
- [ ] Toutes les campagnes au vert sur le harness deterministe.
- [ ] (si live) 0 mismatch, 0 effet de bord interdit execute, chaine d'audit intacte.
- [ ] ruff + mypy + json clean ; aucun secret/fichier tiers dans le stage.
- [ ] RETEX mis a jour ; gotcha nouveau -> reporte dans le skill.

---

## Bilan chiffre (cumul session)

- Campagnes : 10 BNP (`campaigns/bnp/`) + 11 couverture (`campaigns/coverage/`) = 21.
- Actions catalogue couvertes : 118/118 (deterministe ET live Groq).
- Outils py : `run_bnp_scenarios.py` (det.), `run_bnp_live_all.py` (live), `run_bnp_live_groq.py`
  (demo cible), `gen_coverage_campaigns.py` (generateur).
- Skill : `recette-campaign-builder` (OODA, references, eval).
- Mismatch : 0. Effets de bord interdits executes : 0. Chaine d'audit : intacte partout.
