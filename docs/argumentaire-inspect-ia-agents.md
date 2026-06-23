# inspect_ia_agents -- argumentaire de presentation interne

> Support pour presenter l'application en interne : ce qu'elle prouve, pourquoi
> elle compte, et les pistes de recherche qu'elle ouvre. Cible : equipe technique,
> securite (RSSI), direction produit.

## Le pitch en une phrase

Les agents IA agissent sur des systemes reels (git, identite, finance, cloud) via
des echanges reseau qu'aujourd'hui personne n'observe ni ne controle ; inspect_ia_agents
rend ces echanges **lisibles**, demontre qu'on peut les **influencer** (red-team), et
prouve qu'un controle **deterministe** -- identite verifiee apres decouverte, regles
d'activite versionnees -- est la seule reponse auditable.

## Le probleme

Un agent IA n'est pas un script : il **decide** quoi faire a chaque etape, puis **agit**
sur un systeme externe. Trois angles morts :

1. **On ne voit pas ce qu'il fait vraiment.** L'intention vit dans l'echange reseau
   (action + ressource + reponse du serveur), pas dans les logs applicatifs.
2. **On ne sait pas s'il reste dans son perimetre.** Un agent "read-only" qui se met a
   ecrire, a changer d'identite, ou a spammer est indetectable sans referentiel.
3. **On ne peut pas auditer la decision.** Sans determinisme, impossible de rejouer
   "pourquoi cette action a ete autorisee" -- donc impossible de prouver une conformite.

## La demonstration, en 5 temps

### 1. Comprendre les mecanismes de communication agent <-> serveur

Chaque effet de bord passe par un proxy mediatise (`ExternalSystemProxy`, invariant I5)
qui capture l'echange complet sous forme de **`ProxyTrace`** : la requete
(`action_type` + `resource` + `request_payload`) ET la `response` du serveur, avec un
`side_effect_hash` deterministe et un numero de sequence monotone. Le cockpit affiche ce
log reseau (onglet Agents / `/proxy`).

> Ce qu'on montre en demo : lancer un agent, voir en direct chaque appel
> agent -> serveur et la reponse, sans instrumenter l'agent. La com devient lisible.

### 2. Montrer qu'on peut influencer cette communication (red-team)

La red-team modelise comment un adversaire detourne la communication, de facon
**deterministe et rejouable** (corpus `corpus/sim/`) :

| Mecanisme | Effet sur la com | Standard (OWASP Agentic 2026) |
|-----------|------------------|-------------------------------|
| **Context / tool poisoning** | La reponse d'un outil est empoisonnee et pilote la decision suivante de l'agent | ASI06 / MITRE `AML.T0110` |
| **Handoff overreach** | L'agent transfere vers un agent non declare | ASI07 |
| **Tool misuse / code exec** | L'agent invoque un outil hors `capability_scope` | ASI02 / ASI05 |
| **Identity mismatch** | L'agent agit sous une identite divergente de celle declaree | ASI03 |
| **Approval bypass** | Une action sensible passe sans approbation | ASI09 |
| **Crescendo coercion** | 4 phases d'escalade (rapport -> sondage -> autorite/urgence -> pression max) | ASI01 |

> Ce qu'on montre : un agent benin, soumis a une injection, derive vers une action
> hors perimetre -- et la gate red-team le **rattrape** (scorecard caught/missed,
> ventilation OWASP). Preuve que la menace est concrete ET detectable.

### 3. D'ou la necessite d'un controle deterministe

La decision de gouvernance est une **fonction pure** :
`decide(event, policy_version, catalog) -> allow | deny | escalate`. Aucune horloge,
aucun random, aucune I/O dans le chemin de decision (invariant I4) ; l'horloge est une
horloge logique injectee, l'`event_id` derive d'une sequence. Consequence :

- **Meme stream d'evenements + meme version de policy => meme verdict, byte-identique.**
- On peut **rejouer** n'importe quelle decision passee pour audit forensique.
- La version de policy appliquee est enregistree avec la decision : changer la policy
  ne reecrit pas l'histoire (event store append-only hash-chaine, invariant I1).

> L'argument securite : sans determinisme, "l'IA a decide" est inverifiable. Avec, chaque
> verdict est reproductible et opposable.

### 4. Le passeport crypto : gouverner seulement apres decouverte

On ne peut gouverner que ce qu'on a d'abord **cartographie**. La sequence proposee :

```
DECOUVERTE  ->  LIAISON D'IDENTITE (passeport)  ->  GOUVERNANCE
discovery        I3 : principal/auth_method lie       policy + approbation
(scanne la       cryptographiquement a l'agent         (allow/deny/escalate)
 source)
```

- La **discovery** scanne la source (repo + manifest `.inspect_ia_agents`) et etablit
  l'existence, le perimetre declare et le risque relatif d'un agent -- sur des proprietes
  invariantes, sans observer le runtime.
- Un agent decouvert recoit un **passeport** : une liaison cryptographique a une identite
  (`principal`, `auth_method`). L'invariant I3 impose que **toute action soit liee a cette
  identite** ; une action anonyme ou a l'identite divergente (`identity_mismatch`) est
  rejetee.
- Sans passeport (agent non decouvert / non lie), la plateforme **deny par defaut** :
  pas de gouvernance optimiste.

> Le slogan : "pas de decouverte, pas de passeport ; pas de passeport, pas d'action."

### 5. Creer des regles de controle d'activite des agents

Le controle est exprime, pas code en dur :

- **Catalogue** de **148 actions** gouvernees sur **16 systemes**, chacune portant un
  `risk_level` et une **criticite Annex C** (C1 refus par defaut, C2 escalade
  systematique, C3 conditionnel, C4 autorise+journalise). Referentiel versionne de
  **124** actions sensibles.
- **Policies versionnees** par `(target_system, action_type, role)` -> verdict, en
  **deny-by-default** : une action non couverte est refusee.
- **Escalade bloquante (I6)** : un verdict `escalate` met l'action en attente
  d'approbation et **ne l'execute pas** ; un timeout escalade/freeze, jamais
  d'auto-approve.
- **4 dimensions de jugement** d'un agent (identite, capacites declarees vs reelles,
  conformite policy, comportement attendu) -- mesurables, mono-axe pour les cas negatifs.

> Ce qu'on montre : changer une regle (ex. `merge_pr` du role X passe en escalate),
> relancer la campagne, voir le verdict basculer -- de maniere rejouable.

## Pistes de recherche ouvertes

- **Lisibilite des decisions LLM** : correler le "pourquoi" (action-log par etape) avec
  le "fait" (ProxyTrace) pour expliquer une derive a partir des seules traces.
- **Robustesse aux injections** : etendre le corpus de poisoning (AgentDojo-style) et
  mesurer le taux de detection par mecanisme OWASP ASI.
- **Discovery multi-surface** : au-dela de git, scanner Temporal / OpenAPI / MCP et
  evaluer la couverture d'un scanner sur des proprietes invariantes.
- **Politiques apprises vs declarees** : generer une policy a partir des actions
  observees (moindre privilege) et la comparer a la policy declaree.
- **Orchestration multi-agents** : modeliser les cascades de defaillance (ASI08) et le
  perimetre des handoffs (ASI07) dans des equipes d'agents.
- **Passeport cryptographique reel** : passer de la liaison `principal/auth_method` a une
  signature / mTLS verifiee dans le chemin de decision.

## Ce qui est deja en place (preuves, pas promesses)

- Boucle agent decide -> act avec **31 providers LLM** + mode mock deterministe.
- Lab de **16 systemes** simules, proxy capturant chaque echange.
- **55 campagnes** de recette, **15 scenarios** red-team, **5 repos** de discovery.
- Gates : `./recette.sh test` (offline), `./recette.sh gates`, `python -m recette redteam`
  (gate deterministe sans cle).
- Invariants I1-I6 appliques et testes (immutabilite, mediation, identite, determinisme,
  side-effects mediats, blocage sur approbation).

## Les invariants, en une ligne chacun

- **I1 Immutabilite** : l'event store est append-only, hash-chaine ; correction =
  evenement compensatoire.
- **I2 Mediation** : aucune action externe sans passage par le Control Plane.
- **I3 Identite** : toute action liee cryptographiquement a une identite (le passeport).
- **I4 Determinisme** : meme stream + meme policy => meme verdict, rejouable.
- **I5 Side-effects mediats** : les effets de bord ne passent que par les proxies.
- **I6 Blocage sur approbation** : l'escalade bloque l'execution jusqu'a resolution.

## Reference

Detail technique : [ARCHITECTURE.md](ARCHITECTURE.md). Runbooks :
[platform.md](runbooks/platform.md), [redteam-recette.md](runbooks/redteam-recette.md),
[github-discovery-recette.md](runbooks/github-discovery-recette.md).
