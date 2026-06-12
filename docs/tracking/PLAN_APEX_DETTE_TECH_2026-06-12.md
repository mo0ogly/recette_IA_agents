# Plan : APEX -- resorption dette technique plateforme recette
Date : 2026-06-12
Session : apex-20260612-dette-tech
Status : TERMINE
Invariants concernes : I4 (determinisme domaines lab), I5 (routage proxy)

## Objectif
Resorber les 7 items de dette identifies par les reviews du cycle precedent, plus
verifier le support multi-providers simultane (demande utilisateur "les providers
c'est multiple"). Baseline : main propre, 422 tests Python OK / 90 console OK / tsc clean.

## THINK -- alternatives de lotissement
- A (retenue) : 4 lots thematiques par zone de code (config-store, lab/proxy, llm/CLI,
  console) + 1 verification multi-provider. Un subagent par lot, sequentiel (pas de
  course git), recette bloquante a la fin. Pros : diffs cohesifs, reviews ciblees.
  Cons : moins parallele.
- B (rejetee) : 7 commits item par item en parallele swarm. Rejet : courses sur
  l'index git entre agents committeurs, deja observe sur ce repo.
- C (rejetee) : tout en un seul agent. Rejet : depasse le budget contexte d'un agent.

## Sous-taches
- [ ] S1 INIT : menage process + pre-flight (FAIT : 0 zombie, 422 OK, tsc OK)
- [ ] S2 lot config-store : (i1) update_server -- changement de mode purge les champs
      de l'ancien mode, valeur null dans le patch = suppression de cle (auth_env
      vidable) ; (i6) delete_agent strict 404 comme delete_server (route + store).
      Fichiers : recette/api/config_store.py, recette/api/routers/config.py, tests.
- [ ] S3 lot lab/proxy : (i2) actions de lecture canoniques dans le domaine github
      (read_repo, list_repos, open_pr, open_issue, comment_issue, merge_pr, push,
      manage_webhook -- purs, deterministes I4) ; (i7) 127.0.0.1 partout (router
      proxy aligne sur ServerManager). Fichiers : recette/lab/domains/github_devops.py,
      recette/platform/proxy/router.py, tests.
- [ ] S4 lot llm/CLI : (i5) factorisation des 4 sous-classes OpenAI-wire (attributs
      de classe BASE_URL/ENV_KEY + __init__ partage, noms de classes conserves) ;
      (i4) CLI --provider 8 choix + --base-url. Fichiers : recette/llm.py,
      recette/__main__.py, tests.
- [ ] S5 lot console : (i3) filtre event_id -- param query backend /audit/events +
      page Audit lit ?event_id= (useSearchParams) + liens preuve de la page Verdicts
      pointes vers /audit?event_id=X. Fichiers : recette/api/routers/audit.py,
      console/src/pages/audit/index.tsx, console/src/pages/verdicts/index.tsx, tests.
- [ ] S6 multi-providers simultanes : test e2e -- 2 ai_backends differents en config,
      campagne avec 2 agents references chacun sur son backend, les 2 steps executes
      chacun via SON provider (stubs HTTP locaux distincts, asserts sur les 2 ports).
      Fichiers : tests/test_api_campaigns.py (+ runners si defaut trouve).
- [ ] S7 RECETTE bloquante : ruff sur fichiers touches, suite Python complete,
      vitest + tsc, flux runtime live (curl API comme D5), regression baselines
      (>= 422 / >= 90, zero nouveau fail). RETEX affiche.

## Decisions prises
- update_server : mode change => purge champs des autres modes ; null = suppression
  de cle. Choisi contre "PUT = remplacement total" pour ne pas casser le client
  console existant (PUT partiel utilise partout).
- delete_agent passe strict (404 sur id inconnu) : aligne sur delete_server, le
  laxisme masquait les bugs d'appelant.
- 127.0.0.1 retenu (pas localhost) : evite la resolution IPv6 ::1 divergente.

## Ecarts et replanification
- S6 : aucun defaut de routage trouve -- le runner resout deja le backend par agent
  dans la boucle per-step. Le test prouve le comportement existant (2 providers en
  une campagne, 2 stubs distincts hits une fois chacun).
- AJOUT mid-cycle (S8) : la validation live avec la vraie cle Groq a revele un defaut
  reel hors des 7 items -- StdlibHttpClient n'envoyait pas de User-Agent, Cloudflare
  (api.groq.com) bloquait avec HTTP 403 code 1010. curl passait, urllib non. Fix :
  User-Agent par defaut "agentrail-recette/0.1" (override possible). Sans la cle reelle,
  les stubs offline n'auraient jamais montre ce blocage (R14 valide : la verification
  live attrape ce que les tests a stub ne voient pas).

## Resultat
8 lots livres, 12 commits, 483 tests Python OK / 92 console OK / ruff / tsc clean.
Tous les items verifies en live (curl sur API reelle) : i1 (purge champs + null-clear),
i6 (404), i2 (read_repo/open_pr 200), i3 (filtre event_id 1 match / 0 unknown),
i7 (run routed via 127.0.0.1, read_repo 200), i4 (CLI 8 providers + base-url).
Validation provider reel : backend Groq test ok:true 198ms, agent reel pilote par
Groq -> tool-calls routes via proxy vers mock github (200). Defaut Cloudflare/UA
trouve et corrige pendant la RECETTE live.
