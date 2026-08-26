# Ledra

**Ledra (formerly Audit House) — an AI-native premium audit bureau — from market whitespace to working, tested
product in one day, built by directing an agentic AI workflow.**

Workers' compensation premium audit is a legally mandated, multi-million-unit
annual workflow that carriers already outsource — and as of August 2026 it had
zero AI-native vendors. This repo is the product core of an attack on that
market, built end-to-end on August 25, 2026: market investigation → GTM plan →
live prospect operations → the engine itself.

## The arc

| Stage | Output |
|---|---|
| Market investigation | 14 parallel research agents, hundreds of sourced citations → a 12-market whitespace dossier; premium audit ranked #1 (mandatory demand, existing outsourcing spend, no licensing moat, zero AI entrants) |
| GTM plan | ICP ladder (insurtechs → MGAs → regional carriers → state funds), pricing vs. incumbent economics, the 50-file re-audit sales motion, legal/hosting stack with costs |
| Prospect ops | 42-account scored dashboard with live buying signals, named buying centers, five founder-outreach drafts, and a weekly cloud agent that re-verifies every signal |
| Product (this repo) | State-aware audit engine + document extraction + payroll API intake + the re-audit sales artifact, all self-testing |

## The engine

```
engine/
  state_rules.json      rules-as-data: provenance-tagged (sourced/verify),
                        date-VINTAGED values resolved by policy effective date
  audit_engine.py       pure audit() API + CLI worksheet generator
  extract/              format-sniffing adapters (ADP/Gusto/QuickBooks-style,
                        941, SUTA, GL) with SSN tokenization at ingestion
  extract/payroll_api/  Finch-style employer-permissioned intake; consent
                        enforced in the provider; SSN scope forbidden by policy
  reaudit/              the 50-file re-audit flow: engine findings vs. the
                        incumbent vendor's decisions, client-facing report
  run_all.py            five-suite test matrix
  rules_lint.py         schema + provenance census for the rules library
```

Run everything:

```bash
cd engine && python run_all.py
```

Five suites, all passing: the 20-finding multi-state case, document extraction
(6 checks), the hybrid API pipeline (8 checks incl. negative tests), the
50-file re-audit (50 per-file self-tests with false-positive discipline), and
the robustness suite (guards + extraction fuzzing).

## Design principles

- **Rules are data, not code.** Every state rule lives in `state_rules.json`
  with provenance (`sourced` + citation, or `verify` + what to confirm) and
  date vintages — officer payroll tables turn over on per-state policy-year
  cycles (NY Oct 1, CA Sep 1, PA Apr 1…), so values resolve by policy
  effective date, and a policy predating the earliest known vintage routes to
  human review rather than applying the wrong year's table.
- **No silent failure, anywhere.** Unknown document formats are refused;
  malformed lines are reported, never dropped; unresolvable rules route to a
  credentialed reviewer; placeholder values surface in a VERIFY queue on every
  run. The false-positive discipline is tested: 41 clean files must produce
  zero flags.
- **PII discipline as architecture.** SSNs tokenize at ingestion before
  anything downstream touches them; the test suite greps outputs for leaks and
  fails the build. The payroll-API consent object forbids the SSN scope
  outright — audit doesn't need it.
- **Provenance discipline, proven.** During integration, the original New York
  officer values (from careful secondary research) were **refuted by the
  primary source** (NYCIRB Bulletin R.C. 2659) and corrected — the exact
  failure mode behind the industry's ~12% audit error rate, caught by the
  system's own rules before it could reach a worksheet.

## Honest labels

All test data is synthetic and clearly marked (fictional insureds, seeded
errors at the industry's ~12% benchmark rate). The rules library's regulatory
values are REAL — bureau circulars, filed rating-plan PDFs, and state
regulations, cited entry-by-entry. Secondary-sourced values are applied but
flagged `verify` until confirmed bureau-direct.

## Method note

This project was researched, designed, written, and tested in a single day by
directing an agentic AI workflow (Claude): parallel research agents for market
and regulatory evidence, an engineering loop with self-testing at every layer,
and a scheduled cloud agent keeping the prospect dashboard live. The judgment
calls — which market, which wedge, what gets automated vs. routed to humans,
what ships vs. what waits for a licensed source — are the product.
