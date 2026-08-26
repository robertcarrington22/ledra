# Ledra engine

State-aware deterministic core for AI-native workers' comp premium audits.
v1, August 25, 2026. Companion to The Audit House GTM plan.

## Run it

```bash
python gen_case.py      # writes the multi-state synthetic case to case_v1/
python audit_engine.py  # runs the audit; exit 0 only if the self-test passes
```

## What v1 does

- **Rules as data** (`state_rules.json`): a default NCCI profile plus per-state
  overrides for NY, CA, PA, DE, NJ, TX, WI, FL and the four monopolistic states
  (OH, WA, WY, ND). Resolution order: state override → NCCI default.
- **Provenance discipline**: every value is tagged `sourced` (citation attached)
  or `verify` (structural placeholder). The engine applies `verify` values but
  reports them in a VERIFY QUEUE — no unconfirmed number ever hides in a
  worksheet. Findings the rules can't decide route to a credentialed human
  reviewer (`review` severity) instead of guessing.
- **Checks**: 941/SUTA/register triangle reconciliation · state-resolved OT
  exclusion (PA/DE deny outright; records-deficiency denial elsewhere; NJ routes
  to review) · state officer min/max caps (NY 2026 table sourced) · uninsured
  subcontractor charges with materials-fraction handling · monopolistic-state
  guard · physical-audit threshold determination · NY 180-day completion clock ·
  ANC eligibility (two documented attempts; unavailable in TX/AK).
- **Worksheet**: findings grouped by state, each citing evidence, action, rule,
  provenance, and premium impact — built to be re-performable by a bureau test
  auditor (the WCIRB PAAP standard).
- **Self-test**: the synthetic case (`gen_case.py`) seeds 20 conditions across
  six states; the engine must catch exactly those — no misses, no false
  positives. This is the regression suite; every new rule ships with a seeded
  case.

## v2: the document extraction layer (`extract/`)

Vendor-native documents in, canonical case out — the layer that feeds the
engine from what insureds actually send.

```bash
cd extract
python gen_docs.py      # writes messy vendor-format source docs to docs_v2/
python pipeline.py      # extraction -> normalization -> v1 engine, end to end
```

- **Format-sniffing adapters** for three payroll-export styles (ADP-like
  pipe-delimited with "Last, F." names and footer totals; Gusto-like CSV with
  its own headers; QuickBooks-like fixed text), plus Form 941, SUTA report, and
  GL export parsers. Unknown formats fail LOUDLY and route to manual intake —
  the pipeline never guesses.
- **SSN tokenization at ingestion**: SSNs are replaced with deterministic
  tokens before any downstream processing (in production, before any model
  call, with the vault in KMS-backed storage). The pipeline self-test greps
  the normalized output for plaintext SSNs and fails if any leak.
- **Extraction report** per file: format detected, rows, per-document totals,
  and every unparsed line — nothing is silently dropped.
- **`ScannedDocAdapter`** is the deliberate plug point for the OCR/LLM parser
  (Reducto/Bedrock-class under zero-retention terms). It raises rather than
  guesses: scanned ingestion ships in v2.1 with its own eval set.
- **Pass criteria** (all enforced by `pipeline.py`): zero unparsed lines, all
  SSNs tokenized, no plaintext SSN in the case dir, register/941 totals match
  ground truth to the cent, and the v1 engine reproduces the exact same 20
  findings from extracted documents as from the hand-built case.

## v2.1: the payroll API intake layer (`extract/payroll_api/`)

Employer-permissioned payroll pulls (Finch-style) replacing the document chase
for covered employees, merged with document intake for everyone else.

```bash
cd extract/payroll_api && python gen_api_fixtures.py   # mock sandbox fixtures
cd .. && python pipeline_v21.py                        # hybrid end-to-end test
```

- **Provider abstraction** (`providers.py`): every call requires a VALIDATED
  consent record — enforced in the provider, not left to caller discipline.
  `FinchStyleProvider` mocks the sandbox shapes (company/directory/
  pay-statements); the live client is a credentials swap plus HTTP, not a
  redesign. Worker-permissioned providers (Argyle/Pinwheel-class) are an
  explicit v2.2 stub — different consent model, refuses rather than pretends.
- **Consent as a first-class object**: required scopes checked, the consent
  window checked against the pull date, the authorization trail (who, how,
  when) recorded into the case's `intake_coverage.json` — and the SSN/identity
  scopes are FORBIDDEN by policy: audit intake never needs them (data
  minimization, tested negatively).
- **Domain nuance encoded**: an API overtime bucket whose premium portion is
  not identified does NOT count as a per-employee breakout — the NCCI
  records-deficiency denial survives API intake (tested: D. Ruiz).
- **Hybrid merge**: API rows + document rows, duplicate-guarded, with a
  coverage report (6 of 8 employees via API in the test case; FL/WA arrive by
  document). The v1 engine reproduces the exact 20 findings on the merged case.

## The 50-file re-audit flow (`reaudit/`)

The sales artifact, as a working pipeline: re-audit a prospect's completed
vendor audits, compare engine findings against the vendor's actual decisions,
and generate the client-facing findings report.

```bash
cd reaudit
python gen_book.py      # synthetic 50-file vendor book, ~12-14% seeded error rate
python reaudit.py       # engine re-audit + vendor-decision comparison + self-test
python report_html.py   # renders the client-facing findings report (HTML)
```

- **Discrepancy = disagreement, not finding.** A vendor who denied an
  exclusion the engine also denies is *correct*; only decisions that contradict
  an engine finding become errors. Review-severity findings go to the review
  queue and are never called vendor errors — no guesses in the error list.
- **False-positive discipline is the test**: 41 clean files must produce zero
  flags, and every seeded error must be found per file, per type (all 50
  self-tests pass).
- **Five error types modeled** (the ones test audits actually find): missed
  941 deltas, OT exclusions allowed against state rules, OT allowed without
  per-employee breakout, officer caps not applied (overcharges — refunds due),
  and uninsured subcontractor payments never swept from the GL.
- Uses the v1.1 programmatic API (`audit()` returns findings with `subject`),
  added in this release so harnesses can call the engine without the CLI.

## Before production

1. Clear the VERIFY QUEUE: load current officer min/max tables for every
   written state, confirm NJ OT treatment against the NJCRIB manual, confirm
   the CA USRP physical-audit threshold, and confirm per-state
   materials-fraction rules for uninsured subs.
2. License the NCCI Scopes/Atlas content and the independent-bureau manuals —
   the classification layer (v2) retrieves against them; codes are never
   freeform-generated.
3. v2 roadmap: document-extraction front end (payroll register/941/SUTA
   parsers), classification engine with confidence-gated review, GL audits,
   payroll-API intake, and the QA sampling program.

## Layout

```
engine/
  state_rules.json   # the rules library (data, with provenance)
  audit_engine.py    # the engine
  gen_case.py        # synthetic case generator (seeds the expected findings)
  case_v1/           # generated test case (register, GL, 941/SUTA, policy)
```
