# E2E Tests (Playwright)

## Test Structure

- `nrw/setup/` — runs once before all specs: one database reset for every country any scenario needs
- `nrw/scenarios.ts` — named database states (countries, mock scenario, view time) and the expected values specs assert on
- `nrw/fixtures.ts` — `test` with the `nrwPage` fixture, and `useScenario()`
- `nrw/pages/NrwPage.ts` — page object: navigation, and composes the components
- `nrw/pages/components/` — locators and actions per screen region (events panel, event detail, exposed admin areas, map, layer panel)
- `nrw/helpers/` — API utilities (reset, mock, events, view time) and enums
- `nrw/tests/` — specs, one per user flow

## Conventions

### One spec file per user flow

Name spec files after what the user does (`EventSelection`, `ExposedAdminAreas`), not after a region of the screen or a data scenario. A flow usually changes several regions at once (e.g. drilling down updates the event card, the map and the URL), so a test may assert on any of them.

### Scenarios

The database is reset once per run, in `nrw/setup/`. Each spec calls `useScenario()` at the highest level that shares the same state. It loads the scenario's events with `mockDb()` and pins "now" for the API and the browser.

- State the scenario explicitly in every spec — including `noEvents` — so a spec never depends on what ran before it.
- Add a new scenario to `nrw/scenarios.ts`, including the countries it needs (they are added to the reset automatically).
- Keep expected data (event names, exposed admin areas, numbers) in `nrw/scenarios.ts`, never inline in specs. The mock data doubles as demo data and changes over time.

### Locators

Prefer role and accessible name (`getByRole`, `getByText`). Fall back to CSS-module class substrings (`[class*="nrw-event-card"]`) only where the frontend offers nothing better, and keep them in `nrw/pages/components/`.

### Screenshot assertions

The map is a canvas, so screenshots are the only way to check what it draws.

- Put a screenshot in its own test, tagged with `visualTest` (`@visual`), in the spec of the flow it captures — not at the end of a functional test. A design change then fails only the screenshot test.
- Scope screenshots to the map element by default; assert everything else functionally.
- Keep full-page screenshots to the few states that guard the overall layout (currently "all events" and "event opened"). Every frontend design change breaks them, so do not add more lightly.

Reference screenshots are committed under `__screenshots__/`. Run `npm run test:update-snapshots` to regenerate all baselines after intentional UI changes (see the README for per-file and per-test updates).
