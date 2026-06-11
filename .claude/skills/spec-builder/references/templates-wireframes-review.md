# Wireframes & Review Templates -- Spec-Builder Reference

## Wireframe Textual Template (Phase 6)

```markdown
## Ecran : {Module} Dashboard

### Layout
- Header : Titre + bouton "New Assessment" + bouton "Export"
- Body : Tabs (Overview | Assessments | Risk Matrix | Reports)

### Tab : Overview
+--------------------------------------------------+
| KPI Bar                                          |
| [Total: 42] [Critical: 5] [High: 12] [Open: 28] |
+--------------------------------------------------+
| Risk Matrix 5x5          | Recent Activity       |
| (composant RiskMatrix)   | - Item 1 (2h ago)     |
|                          | - Item 2 (5h ago)     |
+--------------------------------------------------+

### Tab : Assessments
- DataGrid MUI v7 (colonnes : Name, Status, Score, Date, Actions)
- Filtres : Status dropdown, Date range
- Actions par ligne : View, Edit, Archive
- Pagination serveur

### Composants React
| Composant | Reutilise depuis | Nouveau |
|-----------|-----------------|---------|
| RiskMatrix | grc/ebios/EbiosRiskMatrix.tsx (adapt 5x5) | Non |
| ExportPanel | grc/ebios/EbiosExportPanel.tsx | Non |
| Dashboard | - | Oui (~800 lignes) |
| Wizard | grc/ebios/EbiosWorkshopStepper.tsx (adapt N phases) | Non |
```

### Wireframe Rules LIA-SEC

- Specify MUI v7 components used (DataGrid, Tabs, Dialog, etc.)
- Indicate reusable components from other modules
- Estimate lines of code per component
- Specify API endpoints called by each screen
- **MANDATORY: Client selector** dropdown at top of each main screen (loaded from GET /api/clients)
- **MANDATORY: Client filter** in each DataGrid list (Client + Quadrigramme column)
- **MANDATORY: Creation workflow** must start with Client + Perimeter choice BEFORE business data
- **MANDATORY: Exports** must include client quadrigramme in header/filename

---

## UI Help Content Template (Phase 6b)

Bilingual format (1 EN + 1 FR entry per screen/tab):

```markdown
## UI Help Content

| Component | Tab | Lang | Title | Description |
|-----------|-----|------|-------|-------------|
| {module}_dashboard | overview | en | Dashboard Overview | This tab provides... |
| {module}_dashboard | overview | fr | Vue d'ensemble | Cet onglet fournit... |
| {module}_dashboard | trend | en | Risk Trend | Historical view... |
| {module}_dashboard | trend | fr | Tendance des risques | Vue historique... |
```

### UI Help Rules

- Language: **English AND French** (2 entries per screen/tab)
- PostgreSQL table: `ui_help_content` (column `language`: 'en' or 'fr')
- Every new screen MUST have help in both languages (no empty HelpButton)
- New components added in DB appear **automatically** in HelpContentEditor (Admin)
- Use `/create-ui-help` to insert in DB after implementation
- Reference: `_alire/01_DOCUMENTATION/dev/UI_HELP_SYSTEM.md`
- **CRITICAL: UI Help MUST be inserted in the SAME wave as frontend components, NOT in a separate wave.**

### 3 Mandatory Levels

1. **Data in DB**: INSERT in `ui_help_content` for EACH tab in EN + FR
2. **`?` icon in EACH tab**: `<HelpButton component="xxx" tabKey="yyy" />` next to each tab title. If a component has 4 tabs, there are 4 HelpButtons.
3. **Admin editable**: entries appear automatically in HelpContentEditor (Admin)

### HelpButton Pattern (reference: CVE Explorer)

```tsx
import HelpButton from '../../common/HelpButton';

// In each Tab panel, next to the title:
<Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
    <Typography variant="h6">Overview</Typography>
    <HelpButton component="iso27005_dashboard" tabKey="overview" />
</Box>
```

**If using MUI Tabs:**
- Place HelpButton IN each TabPanel content (not in Tab header)
- `tabKey` changes per active tab
- Alternative: single dynamic HelpButton `tabKey={currentTab}` if tabs are state-managed

**Verification:** `grep -r "HelpButton" src/components/grc/{module}/` must return as many lines as specified tabs/screens.

---

## Design Guidelines Template (Phase 6c)

```markdown
## Design Guidelines

### Theme & Colors
- Use `useTheme()` for ALL colors (NEVER hardcode)
- Risk levels: Low=#4CAF50, Medium=#FF9800, High=#F44336, Critical=#9C27B0
- Backgrounds: `theme.palette.background.paper` and `theme.palette.background.default`
- Text: `theme.palette.text.primary` and `theme.palette.text.secondary`

### Layout & Responsive
- Dashboard: Grid responsive `size={{ xs: 12, md: 6, lg: 3 }}` for KPI cards
- DataGrid: `minHeight: 400` + server pagination + sticky header
- Dialogs: `maxWidth="md"` default, `fullWidth`
- Mobile: tabs stacked vertically under 600px

### Required MUI v7 Components
| Component | Usage | Justification |
|-----------|-------|---------------|
| DataGrid | Lists with sort/filter/pagination | LIA-SEC standard |
| Tabs | Multi-section navigation | SMSI/EBIOS consistency |
| Dialog | Create/edit forms | Standard modal pattern |
| Chip | Status badges (colored) | Visual consistency |
| Card | KPI boxes with elevation | Dashboard pattern |

### Accessibility
- `aria-label` on each IconButton
- Tooltips on badges and icons
- Minimum WCAG AA contrast (4.5:1 ratio)
- `tabIndex` on interactive elements

### Animations
- MUI `Fade` or `Grow` transition on dialogs
- `Skeleton` loading during API calls (no generic spinner)
- No hover animation (causes vibration/oscillation, ref FIX_CLICKS_BLOCKED)
```

At implementation: invoke `/frontend-design` for design quality review. Components must be "production-grade" (not generic AI boilerplate).

---

## Code Review Plan Template (Phase 8a)

```markdown
## Code Review Plan

| Vague | Fichiers a reviewer | Focus |
|-------|-------------------|-------|
| Vague 1 (schema) | migration.sql | FK integrity, index, CHECK constraints, idempotence |
| Vague 2 (backend) | {module}_*.go | OWASP (SQL injection, parameterized queries), LogSystemEvent, setCORSHeaders |
| Vague 3 (frontend) | {Module}*.tsx | fetchWithConfig (not raw fetch), customLogger (not console.log), MUI v7 syntax, theme-aware |
| Vague 4 (integration) | All modified files | Regressions, inter-module consistency |
```

**Gate:** `/review` must be invoked after EACH wave. CRITICAL and HIGH findings must be fixed before next wave.

## Frontend Design Quality Checklist (Phase 8b)

```markdown
## Design Quality Checklist

For each React component created:
- [ ] No "generic AI boilerplate" -- design must be distinctive and professional
- [ ] Colors consistent with active theme (useTheme, not hardcode)
- [ ] Responsive: tested at 1280px (desktop), 768px (tablet), 375px (mobile)
- [ ] Loading states: Skeleton during API calls (not generic spinner)
- [ ] Error states: contextual error message + retry button
- [ ] Empty states: illustration or message when no data
- [ ] Animations: Fade/Grow on dialogs, no hover transform (causes vibration)
- [ ] Accessibility: aria-label, tooltips, WCAG AA contrast
- [ ] Consistency: same patterns as existing modules (SMSI, EBIOS, CVE Explorer)
```

**Gate:** After frontend wave, invoke `/frontend-design` in review mode. Components that look like "AI-generated code" must be improved.

## React Best Practices Checklist (Phase 8c)

```markdown
## React Performance Checklist

- [ ] No unnecessary re-renders (React.memo on heavy components)
- [ ] useCallback/useMemo on handlers passed as props
- [ ] Lazy loading of heavy components (React.lazy + Suspense)
- [ ] No complex inline styles (extract to sx or styled)
- [ ] No excessive useState (useReducer if > 5 related states)
- [ ] fetchWithConfig with abort controller (cleanup in useEffect)
```

**Gate:** Invoke `/react-recette` on components to verify React patterns.
