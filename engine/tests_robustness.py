"""Robustness suite — the guards, edges, and failure modes beyond the happy path.

Engine edge cases (via the programmatic audit() API):
  R1  officer BELOW the state minimum -> payroll raised to the floor
  R2  sole proprietor at a sourced flat basis -> adjustment computed
  R3  sole proprietor in a state with no confirmed basis -> routed to review
  R4  register EXCEEDS 941 (negative delta) -> review, never auto-charged
  R5  interchange of labor (one employee, two classes) -> review
  R6  zero/empty payroll -> review, not a silent pass
  R7  regression: none of the new guards fire on the clean baseline case

Extraction fuzzing (malformed input must fail LOUDLY, never mis-parse silently):
  F1  unknown file format -> ExtractionError
  F2  malformed ADP line -> lands in unparsed_lines, never silently dropped
  F3  941 missing line 2 -> ExtractionError
  F4  SSNs scrubbed from arbitrary text
  F5  expired consent -> ConsentError

Exit 0 only if every check passes.
"""
import os, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "extract"))
from audit_engine import Rules, audit
from extract.extractors import (ExtractionError, Vault, adapt_adp, adapt_941, detect_format)
from extract.payroll_api.providers import ConsentError, ConsentRecord

POLICY = {"insured": "Edge Case Co (fictional)", "effective_date": "2025-10-15",
          "expiration_date": "2026-06-30", "estimated_annual_premium": 9000,
          "governing_class": "5537", "class_rates_per_100": {"5537": 9.44, "8810": 0.28}}

def case(**over):
    c = {"policy": POLICY, "form_941": {"line2_wages_tips_comp": 0.0}, "suta_total_wages": 0.0,
         "as_of_date": "2026-08-25", "weeks_in_period": 52,
         "insured_noncompliant": False, "contact_attempts_documented": 2}
    c.update(over)
    return c

def emp(name, st, cls="5537", gross=50000.0, ot=0.0, detail="Y", officer="N", role=None):
    e = {"employee": name, "state": st, "class_code": cls, "gross_wages": f"{gross:.2f}",
         "ot_premium_pay": f"{ot:.2f}", "ot_detail_by_employee": detail, "is_officer": officer}
    if role:
        e["entity_role"] = role
    return e

def ids(findings):
    return {f["id"] for f in findings}

checks = []
def check(label, cond):
    checks.append((label, bool(cond)))

def run_case(register, f941=None, gl=None, **over):
    total = sum(float(e["gross_wages"]) for e in register)
    c = case(**over)
    c["form_941"]["line2_wages_tips_comp"] = f941 if f941 is not None else total
    c["suta_total_wages"] = c["form_941"]["line2_wages_tips_comp"]
    return audit(c, register, gl or [], Rules())

# R1: NY officer below the REAL vintage-resolved minimum
# (policy eff 2025-10-15 -> NYCIRB 10/1/2025 vintage: $975/wk -> floor $50,700)
f = run_case([emp("O. Underwood", "NY", cls="8810", gross=30000.0, officer="Y")])
check("R1 officer below NY minimum raised to floor", "OFFICER-NY-MIN" in ids(f))
r1 = next(x for x in f if x["id"] == "OFFICER-NY-MIN")
check("R1 impact = (50,700-30,000) * 0.28% (real NYCIRB vintage)",
      abs(r1["premium_impact"] - (50700 - 30000) * 0.28 / 100) < 0.01)

# R2: NY sole proprietor — real rule: same weekly band as officers (no flat basis)
f = run_case([emp("S. Solo", "NY", gross=40000.0, role="sole_prop")])
check("R2 NY sole prop floored via officer band", "SOLEPROP-NY-MIN" in ids(f))

# R2b: vintage discipline — policy effective BEFORE the earliest NY vintage -> review
early = run_case([emp("O. Early", "NY", cls="8810", gross=30000.0, officer="Y")],
                 policy={**POLICY, "effective_date": "2025-02-01"})
check("R2b pre-vintage policy routes officer to review", "OFFICER-VERIFY-NY" in ids(early))

# R3: sole proprietor in a state with no basis in the library -> review
f = run_case([emp("S. Palm", "MA", gross=40000.0, role="sole_prop")])
check("R3 unknown-state sole prop routes to review", "SOLEPROP-VERIFY-MA" in ids(f))

# R4: register exceeds 941 -> review, no auto-charge
f = run_case([emp("A. One", "FL", gross=100000.0)], f941=90000.0)
check("R4 negative 941 delta routes to review", "TRIANGLE-941-NEG" in ids(f))
check("R4 no positive-delta finding fired", "TRIANGLE-941" not in ids(f))
check("R4 zero premium impact (review only)",
      next(x for x in f if x["id"] == "TRIANGLE-941-NEG")["premium_impact"] == 0.0)

# R5: interchange of labor
f = run_case([emp("D. Dual", "FL", cls="5537", gross=30000.0),
              emp("D. Dual", "FL", cls="8810", gross=20000.0)])
check("R5 interchange split routes to review", "INTERCHANGE-D.Dual" in ids(f))

# R6: zero payroll
f = run_case([])
check("R6 empty register flagged", "ZERO-PAYROLL" in ids(f))

# R6b: CA uninsured sub with documented materials -> NO percentage shortcut
# exists in CA (actual-remuneration basis, LC 2750.5) -> review, not a charge
f = run_case([emp("W. Coast", "CA", gross=52000.0)],
             gl=[{"date": "2026-01-10", "payee": "Golden Gate Sub LLC",
                  "memo": "sub - install w/ materials", "amount": "20000.00",
                  "coi_on_file": "N", "work_state": "CA", "materials_documented": "Y"}])
check("R6b CA materials sub routes to review (no fraction rule)", "SUB-REVIEW-CA" in ids(f))
check("R6b no SUB-NOCOI-CA charge fired", "SUB-NOCOI-CA" not in ids(f))

# R7: clean baseline produces none of the new findings
f = run_case([emp("C. Clean", "FL", gross=52000.0),
              emp("B. Basic", "TX", gross=48000.0, ot=1200.0, detail="Y")])
new_ids = {i for i in ids(f) if i.startswith(("OFFICER-", "SOLEPROP", "TRIANGLE-941-NEG",
                                              "INTERCHANGE", "ZERO-PAYROLL"))}
check("R7 clean case fires no new guards", not new_ids)

# ---- extraction fuzzing ----
scratch = os.path.join(HERE, "extract", "fuzz_tmp")
os.makedirs(scratch, exist_ok=True)

# F1: unknown format
p = os.path.join(scratch, "mystery.dat")
open(p, "w").write("some totally unknown export\n1,2,3\n")
check("F1 unknown format refused", detect_format(p, open(p).read(1024)) is None)

# F2: malformed ADP line -> unparsed, not dropped
p = os.path.join(scratch, "bad_adp.txt")
open(p, "w").write("File #|Employee Name|SSN|Home Dept|State Worked|Gross Pay|O.T. Premium|Officer\n"
                   "001|Broken, Row|000-99-0000|ADMIN|NY|not_a_number\n")
try:
    report = {}
    rows = adapt_adp(p, Vault(), {"ADMIN": "8810"}, report)
    check("F2 malformed ADP line reported unparsed", report["unparsed_lines"] and not rows)
except Exception:
    check("F2 malformed ADP line reported unparsed", False)

# F3: 941 with no line 2
p = os.path.join(scratch, "bad_941.txt")
open(p, "w").write("FORM 941 ROLL-UP\nLine 1 Number of employees .... 3\n")
try:
    adapt_941(p, {})
    check("F3 941 missing line 2 raises", False)
except ExtractionError:
    check("F3 941 missing line 2 raises", True)

# F4: SSN scrub
v = Vault()
scrubbed = v.scrub("call 000-11-2222 and 000-33-4444 re: wages")
check("F4 SSNs scrubbed from text", "000-11-2222" not in scrubbed and len(v.map) == 2)

# F5: expired consent
try:
    ConsentRecord({"employer": "x", "authorized_by": "y", "method": "z", "provider": "p",
                   "connection_id": "c", "scopes": ["company", "directory", "pay_statements"],
                   "granted_at": "2026-01-01", "expires_at": "2026-02-01"}).validate(date(2026, 8, 25))
    check("F5 expired consent rejected", False)
except ConsentError:
    check("F5 expired consent rejected", True)

# ---- report ----
print("=" * 70)
print("ROBUSTNESS SUITE")
print("=" * 70)
ok = True
for label, passed in checks:
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    ok = ok and passed
print(f"\nROBUSTNESS: {'ALL CHECKS PASS' if ok else 'FAILED'} ({len(checks)} checks)")
sys.exit(0 if ok else 1)
