# Release-Readiness Rubric

> Companion to `audit_release_readiness` (v0.3.0 phase 11).

The composite gate. One tool, one ship/hold/block verdict, paste
directly into a release PR comment.

## What this answers

> *"Is this code safe to ship?"*

Not a single audit can answer that alone. The composite runs
the four v0.3.0 audit verticals in parallel and aggregates:

```
audit_code_seniority   →  architecture quality
audit_security         →  OWASP MASVS
audit_localization     →  i18n hygiene
audit_dependencies     →  supply chain
audit_test_quality     →  test-suite quality (phase 12.5+)
              ↓ concurrent asyncio.gather
       composite verdict + grade + top_actions
```

Sub-second on a typical app. Pure compute. No device, no
network, no build artifact required.

## The verdict

```
ANY blocker (or critical security finding) → block
no blockers AND composite ≥ 80              → ship
no blockers AND composite < 80              → hold
```

**Block** means: do not merge until the blocker is resolved.
**Hold** means: technically shippable, but the code has enough
mid-tier issues that a senior reviewer would push back.
**Ship** means: no blockers, score ≥ 80, paste the advice line
in the PR and merge.

## The composite letter grade

After computing `weighted_average(domain_scores)`:

| Score | Grade |
|---|---|
| ≥ 90 | A |
| ≥ 80 | B |
| ≥ 70 | C |
| ≥ 60 | D |
| < 60 | F |

## Per-domain score mapping

Each sub-audit reports its own string grade. The composite maps
those to 0–100:

### Seniority
- staff → 100
- senior → 85
- mid → 65
- junior → 40
- needs_review → 0

### Security
- secure → 100
- acceptable → 75
- at_risk → 40
- critical → 0

### Localization
- well_localized → 100
- acceptable → 75
- single_locale → 50
- missing_l10n → 20

### Dependencies
- clean → 100
- acceptable → 75
- at_risk → 40
- blocked → 0

## Default weights

Reflecting the relative risk of shipping with issues in each
domain:

| Domain | Default weight | Rationale |
|---|---|---|
| security | **2.0** | OWASP issues are the most expensive to ship and the hardest to fix in flight |
| dependencies | 1.5 | Supply-chain risk compounds over time |
| seniority | 1.0 | Architectural debt — slow burn |
| localization | 1.0 | Bad UX in non-default locales but won't break the app |

Override any weight per-call to match your team's priorities.

## Cross-domain top_actions

Each domain emits its own `top_actions` (severity-prefixed).
The composite collects all of them, sorts globally by severity
weight, prepends `[domain]` for traceability, and caps at
`max_top_actions` (default 10).

Example output:

```
[security] [critical] hardcoded_api_key ×2 — Move to --dart-define
[localization] [blocker] missing_l10n_key ×3 — Add to .arb file
[dependencies] [serious] dev_dep_in_dependencies ×2 — Move under dev_dependencies
[seniority] [serious] business_logic_in_widget ×1 — Inject Repository via DI
```

## Use in a release PR

```python
result = audit_release_readiness(
    project_path="/path/to/project",
    min_level="junior",        # catch everything
    is_published=True,         # this is a public app
)

print(result.advice)
# SHIP — composite 87/100. Ready to release. Grade: B. 4 findings
# across [seniority, security, localization, dependencies] in 0.78s.
# (seniority=senior · security=secure · localization=well_localized
#  · dependencies=clean)
```

If `verdict == "block"`, the PR template should reject merge.
If `verdict == "hold"`, the PR template should require approval.
If `verdict == "ship"`, auto-approve eligible.

## Per-domain breakdown

Every result includes a `DomainResult` per domain:

```python
@dataclass
class DomainResult:
    domain: str             # 'seniority' / 'security' / etc.
    ran: bool               # False if disabled or errored
    grade: str | None       # the domain's own grade
    score: float            # normalized 0-100
    findings_count: int
    blockers_count: int
    error: str | None       # populated if the audit failed
    advice: str | None      # the domain's own advice line
```

So you can drill into any single domain's contribution.

## Robustness

If one sub-audit fails (e.g. malformed pubspec → audit_dependencies
errors out), the composite still returns. The errored domain is
marked `ran=False, error="..."`. The other domains' scores are
used; the composite weight normalizes only over `ran=True` domains.

This means **you always get a verdict** — never a half-result.

## What this is NOT

- **Not a build runner.** We don't call `flutter build`. If you
  want size analysis, that's a separate phase.
- **Not an accessibility checker by default.** Accessibility
  needs a running device — opt in via the standalone tool.
- **Not opinionated about every weight.** Defaults are sane;
  tune for your team's risk profile.

## Composition with the wider v0.3.0 audit suite

```python
# The composite covers 4 domains.
audit_release_readiness(project_path="...")

# These need device access — invoke separately:
audit_accessibility(...)     # WCAG 2.2 on running UI
analyze_app_size(...)        # needs a build artifact
```

Future: phase 12 `audit_test_quality` joins the composite once
shipped.

## Tuning thresholds for your team

The ship cutoff (composite ≥ 80) is a default. To tighten:

- Set `min_level="senior"` → suppresses junior/mid findings;
  effectively raises the bar
- Increase `weight_security` → more punitive on security issues
- Decrease `weight_localization` → if your app is single-locale
  by design

The rubric is opinionated on purpose. Tune, don't bypass.
