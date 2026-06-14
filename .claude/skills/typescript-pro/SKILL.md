---
name: typescript-pro
description: Implements advanced TypeScript type systems, creates custom type guards, utility types, and branded types, and configures tRPC for end-to-end type safety. Use when building TypeScript applications requiring advanced generics, conditional or mapped types, discriminated unions, monorepo setup, or full-stack type safety with tRPC.
license: MIT
metadata:
  author: https://github.com/Jeffallan
  version: "1.1.0"
  domain: language
  triggers: TypeScript, generics, type safety, conditional types, mapped types, tRPC, tsconfig, type guards, discriminated unions
  role: specialist
  scope: implementation
  output-format: code
  related-skills: fullstack-guardian, api-designer
---

# TypeScript Pro (LIA-SEC Edition)

## LIA-SEC Adaptations (MANDATORY)

- **Stack** : TypeScript 4.9 strict mode, React 19, MUI v7, Vite, in `sigma-react-frontend/`
- **API envelope typing** : every backend response is `{ success: boolean; data: T; error?: string }`.
  Define a generic `ApiResponse<T>` once, UNWRAP `.data` at service layer, never leak envelope to components (R17)
- **fetchWithConfig** : all calls go through `src/config/apiConfig.ts` -- type its return; never `fetch()` brut
- **Discriminated unions** for state machines :
  `type State = {kind:'idle'}|{kind:'loading'}|{kind:'ok',data:T}|{kind:'error',msg:string}`
- **Branded types** for IDs (`CampaignId`, `RuleId`, `CveId`) to prevent cross-domain misuse
- **Runtime validation** at boundaries (Zod or manual) -- types alone are not contracts (R17 / R18)
- **No `any`** in production code ; use `unknown` + narrowing
- **Companion skills** : `/react-expert` (components), `/api-handoff` (contract), `/test-first` (tests),
  `/debug-react` (fix), `/react-recette` (audit OWASP frontend)

---

## Core Workflow

1. **Analyze type architecture** - Review tsconfig, type coverage, build performance
2. **Design type-first APIs** - Create branded types, generics, utility types
3. **Implement with type safety** - Write type guards, discriminated unions, conditional types; run `tsc --noEmit` to catch type errors before proceeding
4. **Optimize build** - Configure project references, incremental compilation, tree shaking; re-run `tsc --noEmit` to confirm zero errors after changes
5. **Test types** - Confirm type coverage with a tool like `type-coverage`; validate that all public APIs have explicit return types; iterate on steps 3–4 until all checks pass

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Advanced Types | `references/advanced-types.md` | Generics, conditional types, mapped types, template literals |
| Type Guards | `references/type-guards.md` | Type narrowing, discriminated unions, assertion functions |
| Utility Types | `references/utility-types.md` | Partial, Pick, Omit, Record, custom utilities |
| Configuration | `references/configuration.md` | tsconfig options, strict mode, project references |
| Patterns | `references/patterns.md` | Builder pattern, factory pattern, type-safe APIs |

## Code Examples

### Branded Types
```typescript
// Branded type for domain modeling
type Brand<T, B extends string> = T & { readonly __brand: B };
type UserId  = Brand<string, "UserId">;
type OrderId = Brand<number, "OrderId">;

const toUserId  = (id: string): UserId  => id as UserId;
const toOrderId = (id: number): OrderId => id as OrderId;

// Usage — prevents accidental id mix-ups at compile time
function getOrder(userId: UserId, orderId: OrderId) { /* ... */ }
```

### Discriminated Unions & Type Guards
```typescript
type LoadingState = { status: "loading" };
type SuccessState = { status: "success"; data: string[] };
type ErrorState   = { status: "error";   error: Error };
type RequestState = LoadingState | SuccessState | ErrorState;

// Type predicate guard
function isSuccess(state: RequestState): state is SuccessState {
  return state.status === "success";
}

// Exhaustive switch with discriminated union
function renderState(state: RequestState): string {
  switch (state.status) {
    case "loading": return "Loading…";
    case "success": return state.data.join(", ");
    case "error":   return state.error.message;
    default: {
      const _exhaustive: never = state;
      throw new Error(`Unhandled state: ${_exhaustive}`);
    }
  }
}
```

### Custom Utility Types
```typescript
// Deep readonly — immutable nested objects
type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object ? DeepReadonly<T[K]> : T[K];
};

// Require exactly one of a set of keys
type RequireExactlyOne<T, Keys extends keyof T = keyof T> =
  Pick<T, Exclude<keyof T, Keys>> &
  { [K in Keys]-?: Required<Pick<T, K>> & Partial<Record<Exclude<Keys, K>, never>> }[Keys];
```

### Recommended tsconfig.json
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "isolatedModules": true,
    "declaration": true,
    "declarationMap": true,
    "incremental": true,
    "skipLibCheck": false
  }
}
```

## Constraints

### MUST DO
- Enable strict mode with all compiler flags
- Use type-first API design
- Implement branded types for domain modeling
- Use `satisfies` operator for type validation
- Create discriminated unions for state machines
- Use `Annotated` pattern with type predicates
- Generate declaration files for libraries
- Optimize for type inference

### MUST NOT DO
- Use explicit `any` without justification
- Skip type coverage for public APIs
- Mix type-only and value imports
- Disable strict null checks
- Use `as` assertions without necessity
- Ignore compiler performance warnings
- Skip declaration file generation
- Use enums (prefer const objects with `as const`)

## Output Templates

When implementing TypeScript features, provide:
1. Type definitions (interfaces, types, generics)
2. Implementation with type guards
3. tsconfig configuration if needed
4. Brief explanation of type design decisions

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour cartographier les types existants (`src/types/`, `src/services/`)
- [ ] Sous-tache 2 : identifier les violations (any, envelopes non typees, boundaries sans runtime validation)
- [ ] Sous-tache 3 : design des types publics (ApiResponse<T>, branded IDs, discriminated unions)
- [ ] Sous-tache 4 : implementation avec type guards + runtime validation aux boundaries
- [ ] Sous-tache 5 : `npx tsc --noEmit` gate -- zero erreur avant de continuer
- [ ] Sous-tache 6 : verification qu'aucun `any` n'a ete introduit

Sous-taches 1-2 parallelisables. Sous-tache 5 depend de 4.

## Plan d'execution

Pour tout refactor de types ou ajout de feature typee non trivial (> 2 fichiers ou nouveau domaine) :

1. Creer `_alire/tracking/PLAN_TYPESCRIPT_PRO_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire une ligne.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une modification ponctuelle (1 fichier, type guard isole) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: `tsc` echoue + fix qui casse autre chose) :

- STOP
- Invoquer `/replan` -> produit `PLAN_TYPESCRIPT_PRO_*_REPLAN_*.md`
- NE PAS improviser un contournement (`as unknown as T`, double-cast)

Declencheurs typiques :
- Cascade d'erreurs tsc apres un refactor de type -> REPLAN
- Type guard ne couvre pas un cas runtime -> REPLAN
- Discriminated union incompatible avec l'existant -> REPLAN

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Explorer types existants + patterns avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier `.ts` / `.tsx` | N/A |
| `Bash npx tsc --noEmit` | Type-check (gate bloquant) | echec -> diagnose, pas de retry aveugle |
| `Bash grep -rn "any"` | Detecter introductions de `any` dans le changeset | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(react-expert)` | Apres types, pour les composants | Si composant implique |
| `Skill(react-recette)` | Audit OWASP frontend avant commit | Obligatoire si `.tsx` |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix d'architecture de types (branded vs opaque, union discriminee vs flag boolean)
- Rejet d'une alternative (ex: Zod vs manuel, `satisfies` vs `as`)
- Trade-offs (runtime validation cout vs type safety gain)

Format :
```json
{"timestamp":"...","session":"typescript-pro-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_TYPESCRIPT_PRO_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_TYPESCRIPT_PRO_YYYY-MM-DD.md`.

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `cd /opt/lia-sec/dev/sigma-react-frontend && npx tsc --noEmit` exits 0 (zero erreur)
- [ ] `grep -rn ": any" --include="*.ts" --include="*.tsx" src/` -- zero nouveau `any` introduit
- [ ] Discriminated unions utilisees pour tout state machine (pas de flag booleans multiples)
- [ ] Runtime validation presente aux boundaries API (`ApiResponse<T>` unwrap au service layer)
- [ ] Aucun `as X` sans type guard adjacent justifie

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : outils choisis dynamiquement + tsc gate + no-any check invoques ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Knowledge Reference

TypeScript 5.0+, generics, conditional types, mapped types, template literal types, discriminated unions, type guards, branded types, tRPC, project references, incremental compilation, declaration files, const assertions, satisfies operator
