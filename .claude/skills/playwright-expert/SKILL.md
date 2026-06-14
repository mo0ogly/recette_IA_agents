---
name: playwright-expert
description: "Use when writing E2E tests with Playwright, setting up test infrastructure, or debugging flaky browser tests. Invoke to write test scripts, create page objects, configure test fixtures, set up reporters, add CI integration, implement API mocking, or perform visual regression testing. Trigger terms: Playwright, E2E test, end-to-end, browser testing, automation, UI testing, visual testing, Page Object Model, test flakiness."
license: MIT
metadata:
  author: https://github.com/Jeffallan
  version: "1.1.0"
  domain: quality
  triggers: Playwright, E2E test, end-to-end, browser testing, automation, UI testing, visual testing
  role: specialist
  scope: testing
  output-format: code
  related-skills: test-master, react-expert, devops-engineer
---

# Playwright Expert (LIA-SEC Edition)

## LIA-SEC Adaptations (MANDATORY)

- **Target URL** : `https://inspect-ia-agents.tech/` (prod) ou `http://localhost:3000/` (dev local sur VPS)
- **Existing skill** : `webapp-testing` (Playwright MCP intégré) -- utiliser ce skill-là pour
  debug interactif ; `/playwright-expert` pour écrire des suites E2E pérennes
- **R17 Contract Gate** (BLOCKING) : tout composant qui appelle une API doit avoir un
  Playwright smoke test post-deploy -- pas juste un unit test
- **Authentication** : login via `/api/auth/login` puis JWT en `Authorization: Bearer` header
  ou cookie `httpOnly` ; voir `auth_session_middleware.go` pour les routes publiques
- **Page Object Model** : localisateurs stables via `data-testid` (pas de CSS fragile),
  attendre les états réseau via `page.waitForResponse('**/api/...')`
- **Selectors MUI v7** : préférer `getByRole`/`getByLabel` aux sélecteurs de classe MUI
  (les classes `Mui*-xxx-123` changent à chaque rebuild Vite)
- **Captures pour RETEX** : `page.screenshot({ path: '_alire/temp/pdca-cycleN-screenshot.png' })`
  à ajouter systématiquement aux findings PDCA / APEX
- **No flakiness** : `waitForLoadState('networkidle')` + timeout explicite ; jamais de `sleep()` ;
  retry via `test.describe.configure({ retries: 2 })` en CI uniquement
- **VPS deploy gate** : après `./deploy.sh`, Playwright smoke test obligatoire
  (gate Phase 4 `/apex`, gate CHECK C.2 `/audit-pdca`)
- **Companion skills** : `/webapp-testing` (MCP interactif), `/test-first` (enforce tests),
  `/react-recette` (audit frontend), `/audit-pdca` (orchestration)

---

## Core Workflow

1. **Analyze requirements** - Identify user flows to test
2. **Setup** - Configure Playwright with proper settings
3. **Write tests** - Use POM pattern, proper selectors, auto-waiting
4. **Debug** - Run test → check trace → identify issue → fix → verify fix
5. **Integrate** - Add to CI/CD pipeline

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Selectors | `references/selectors-locators.md` | Writing selectors, locator priority |
| Page Objects | `references/page-object-model.md` | POM patterns, fixtures |
| API Mocking | `references/api-mocking.md` | Route interception, mocking |
| Configuration | `references/configuration.md` | playwright.config.ts setup |
| Debugging | `references/debugging-flaky.md` | Flaky tests, trace viewer |

## Constraints

### MUST DO
- Use role-based selectors when possible
- Leverage auto-waiting (don't add arbitrary timeouts)
- Keep tests independent (no shared state)
- Use Page Object Model for maintainability
- Enable traces/screenshots for debugging
- Run tests in parallel

### MUST NOT DO
- Use `waitForTimeout()` (use proper waits)
- Rely on CSS class selectors (brittle)
- Share state between tests
- Ignore flaky tests
- Use `first()`, `nth()` without good reason

## Code Examples

### Selector: Role-based (correct) vs CSS class (brittle)

```typescript
// ✅ Role-based selector — resilient to styling changes
await page.getByRole('button', { name: 'Submit' }).click();
await page.getByLabel('Email address').fill('user@example.com');

// ❌ CSS class selector — breaks on refactor
await page.locator('.btn-primary.submit-btn').click();
await page.locator('.email-input').fill('user@example.com');
```

### Page Object Model + Test File

```typescript
// pages/LoginPage.ts
import { type Page, type Locator } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.emailInput = page.getByLabel('Email address');
    this.passwordInput = page.getByLabel('Password');
    this.submitButton = page.getByRole('button', { name: 'Sign in' });
    this.errorMessage = page.getByRole('alert');
  }

  async goto() {
    await this.page.goto('/login');
  }

  async login(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }
}
```

```typescript
// tests/login.spec.ts
import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

test.describe('Login', () => {
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    await loginPage.goto();
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await loginPage.login('user@example.com', 'correct-password');
    await expect(page).toHaveURL('/dashboard');
  });

  test('invalid credentials shows error', async () => {
    await loginPage.login('user@example.com', 'wrong-password');
    await expect(loginPage.errorMessage).toBeVisible();
    await expect(loginPage.errorMessage).toContainText('Invalid credentials');
  });
});
```

### Debugging Workflow for Flaky Tests

```typescript
// 1. Run failing test with trace enabled
// playwright.config.ts
use: {
  trace: 'on-first-retry',
  screenshot: 'only-on-failure',
}

// 2. Re-run with retries to capture trace
// npx playwright test --retries=2

// 3. Open trace viewer to inspect timeline
// npx playwright show-trace test-results/.../trace.zip

// 4. Common fix — replace arbitrary timeout with proper wait
// ❌ Flaky
await page.waitForTimeout(2000);
await page.getByRole('button', { name: 'Save' }).click();

// ✅ Reliable — waits for element state
await page.getByRole('button', { name: 'Save' }).waitFor({ state: 'visible' });
await page.getByRole('button', { name: 'Save' }).click();

// 5. Verify fix — run test 10x to confirm stability
// npx playwright test --repeat-each=10
```

## Output Templates

When implementing Playwright tests, provide:
1. Page Object classes
2. Test files with proper assertions
3. Fixture setup if needed
4. Configuration recommendations

## Decomposition des sous-taches

Au demarrage, decomposer toute demande E2E en sous-taches independantes :

- [ ] Sous-tache 1 : identifier les user flows a tester + les pages/composants impliques
- [ ] Sous-tache 2 : verifier les `data-testid` stables sur les elements cibles (pas de CSS MUI)
- [ ] Sous-tache 3 : creer/maj les Page Object classes dans `tests/pages/`
- [ ] Sous-tache 4 : ecrire les specs (`tests/*.spec.ts`) avec assertions explicites
- [ ] Sous-tache 5 : executer `npx playwright test` -- zero fail, zero flaky
- [ ] Sous-tache 6 : captures RETEX dans `_alire/temp/` (screenshot apres chaque finding)

Sous-taches 3-4 parallelisables par page. Sous-tache 5 depend de 4.

## Plan d'execution

Pour toute suite E2E (> 2 flows ou nouveau module) :

1. Creer `_alire/tracking/PLAN_PLAYWRIGHT_{MODULE}_{YYYY-MM-DD}.md` avant d'ecrire un test.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque flow a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour un smoke test ponctuel post-deploy (R17 E3) : plan inline suffit.

## Adaptation et replanification

Si 2 tests consecutifs restent flaky apres fix ou si le localisateur casse :

- STOP
- Invoquer `/replan` -> produit `PLAN_PLAYWRIGHT_*_REPLAN_*.md`
- NE PAS augmenter les timeouts ou ajouter des retries sans comprendre la cause

Declencheurs typiques :
- Localisateur fragile (classe MUI changeante) -> REPLAN (migrer vers `data-testid` / `getByRole`)
- Test echoue apres deploy (env prod different de local) -> REPLAN (inspecter le diff)
- Auth JWT expire pendant le run -> REPLAN (rafraichir le token dans la fixture)

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Cartographier tests existants + POM avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier `*.spec.ts`, `pages/*.ts` | N/A |
| `Bash npx playwright test` | Executer la suite (local ou CI) | 1 retry env ; echec recurrent -> diagnose |
| `Bash npx playwright show-trace` | Debug flakiness (trace viewer) | N/A |
| `mcp__playwright__*` | Navigation interactif (debug, capture live) via webapp-testing | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(webapp-testing)` | Debug interactif MCP (pas de suite pérenne) | Si investigation live |
| `Skill(test-master)` | Strategie tests globale + coverage | Si besoin de vue d'ensemble |

Selection dynamique : `mcp__playwright__*` pour debug interactif, `npx playwright test` pour suite CI.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix de localisateur (role vs label vs data-testid) + justification
- Strategie d'auth (token fixture vs login flow) + trade-off
- Delegation a `/webapp-testing` pour debug live + raison

Format :
```json
{"timestamp":"...","session":"playwright-{module}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_PLAYWRIGHT_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_PLAYWRIGHT_YYYY-MM-DD.md`.

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `npx playwright test` passe -- zero test en echec
- [ ] Zero flakiness : meme test execute 2x produit le meme resultat
- [ ] Smoke post-deploy valide (R17 E3) : naviguer sur `https://inspect-ia-agents.tech/` ou `:3000` apres deploy
- [ ] Pas de `waitForTimeout()` dans le code livre -- remplacer par `waitFor({ state })` ou `waitForResponse`
- [ ] Screenshots de findings dans `_alire/temp/pdca-cycleN-*.png` (si session PDCA/APEX)
- [ ] Localisateurs stables (`data-testid`, `getByRole`, `getByLabel`) -- zero sélecteur CSS Mui*

Si un gate echoue : STOP, fix la cause racine, re-gate. JAMAIS committer un test flaky.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : flows identifies + pages cartographies ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur flakiness persistante ou localisateur casse ? | /10 |
| C4 Outillage : npx playwright test + trace viewer + webapp-testing selon contexte ? | /10 |
| C5 Tracabilite : decision_log + captures _alire/temp/ + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Knowledge Reference

Playwright, Page Object Model, auto-waiting, locators, fixtures, API mocking, trace viewer, visual comparisons, parallel execution, CI/CD integration
