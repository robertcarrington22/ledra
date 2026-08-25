"""Generate the v1 multi-state synthetic audit case.

Fictional insured: BlueRidge Mechanical Contractors Inc (HVAC), final audit for
the policy year ending 2026-02-01, employees across NY/PA/TX/NJ/FL/WA.

Seeded conditions the engine must catch (see expected_findings in case.json):
  - 941 wages exceed the register by $12,400 (unrecorded bonus run)
  - PA employee claims OT exclusion WITH proper records -> denied by STATE rule
  - TX employee claims OT exclusion without per-employee breakout -> denied on records
  - NJ employee claims OT exclusion -> routed to human review (state rule unconfirmed)
  - NY officer exceeds the sourced 2026 NY max ($3,400/wk) -> capped
  - FL officer present but FL table unconfirmed -> routed to review
  - WA employee -> monopolistic-state exclusion
  - NJ subcontractor paid $52,300 with no COI -> full charge
  - PA subcontractor no COI but materials documented -> fractional charge (verify)
  - NY 180-day audit completion window blown (expired 2026-02-01, as-of 2026-08-25)
  - Insured partially noncompliant with 1 documented attempt -> ANC not yet
    chargeable (and not available at all in TX)
  - Estimated annual premium $26,500 -> physical-audit threshold met in all states
"""
import csv, json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "case_v1")
os.makedirs(OUT, exist_ok=True)

EMPLOYEES = [
    # employee, state, class_code, gross_wages, ot_premium_pay, ot_detail_by_employee, is_officer
    ["T. Marsh",   "NY", "8810", 182000.00,    0.00, "Y", "Y"],
    ["L. Chen",    "NY", "5537",  68800.00, 5400.00, "Y", "N"],
    ["R. Novak",   "PA", "5537",  63200.00, 4480.00, "Y", "N"],
    ["D. Ruiz",    "TX", "5537",  56400.00, 3560.00, "N", "N"],
    ["A. Boone",   "TX", "8742",  49200.00,    0.00, "Y", "N"],
    ["S. Adeyemi", "NJ", "5537",  64000.00, 3760.00, "Y", "N"],
    ["P. Marsh",   "FL", "8810", 120000.00,    0.00, "Y", "Y"],
    ["K. Ilsley",  "WA", "5537",  55600.00,    0.00, "Y", "N"],
]
MISSING_BONUS = 12400.00
register_total = sum(e[3] for e in EMPLOYEES)

with open(os.path.join(OUT, "payroll_register.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["employee", "state", "class_code", "gross_wages", "ot_premium_pay",
                "ot_detail_by_employee", "is_officer"])
    for e in EMPLOYEES:
        w.writerow([e[0], e[1], e[2], f"{e[3]:.2f}", f"{e[4]:.2f}", e[5], e[6]])

with open(os.path.join(OUT, "gl_cash_disbursements.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "payee", "memo", "amount", "coi_on_file", "work_state", "materials_documented"])
    w.writerow(["2025-06-14", "Garden State Mech LLC", "sub - ductwork install", "52300.00", "N", "NJ", "N"])
    w.writerow(["2025-09-03", "Keystone Duct Co", "sub - fabrication + install", "18000.00", "N", "PA", "Y"])
    w.writerow(["2025-11-21", "Empire Sheet Metal", "sub - rooftop units", "27650.00", "Y", "NY", "N"])

case = {
    "period": "final audit, policy year ending 2026-02-01",
    "as_of_date": "2026-08-25",
    "weeks_in_period": 52,
    "policy": {
        "insured": "BlueRidge Mechanical Contractors Inc (fictional)",
        "expiration_date": "2026-02-01",
        "estimated_annual_premium": 26500,
        "governing_class": "5537",
        "class_rates_per_100": {"5537": 9.44, "8810": 0.28, "8742": 0.51},
    },
    "form_941": {"line2_wages_tips_comp": round(register_total + MISSING_BONUS, 2)},
    "suta_total_wages": round(register_total + MISSING_BONUS, 2),
    "insured_noncompliant": True,
    "contact_attempts_documented": 1,
    "expected_findings": [
        "MONO-WA",
        "TRIANGLE-941",
        "OT-STATE-PA-R.Novak",
        "OT-RECORDS-TX-D.Ruiz",
        "OT-VERIFY-NJ-S.Adeyemi",
        "OFFICER-NY-CAP",
        "OFFICER-VERIFY-FL",
        "SUB-NOCOI-NJ",
        "SUB-NOCOI-PA",
        "AUDITTYPE-FL", "AUDITTYPE-NJ", "AUDITTYPE-NY", "AUDITTYPE-PA", "AUDITTYPE-TX",
        "DEADLINE-NY",
        "ANC-NA-TX",
        "ANC-NOTELIGIBLE-FL", "ANC-NOTELIGIBLE-NJ", "ANC-NOTELIGIBLE-NY", "ANC-NOTELIGIBLE-PA",
    ],
}
with open(os.path.join(OUT, "case.json"), "w") as f:
    json.dump(case, f, indent=2)

print("case_v1 written:", sorted(os.listdir(OUT)))
print(f"register total = {register_total:,.2f}; 941/SUTA = {register_total + MISSING_BONUS:,.2f}")
