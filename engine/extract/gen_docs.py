"""Generate messy, vendor-native source documents for the v2 extraction test.

Same underlying facts as case_v1 (BlueRidge Mechanical), but delivered the way
insureds actually deliver them: three payroll systems with different layouts,
column names, and name conventions; SSNs scattered through the registers; a
Form 941 and SUTA report as text; a GL export with its own headers.

The extraction layer must normalize ALL of this into the engine's canonical
case format — and the v1 engine must then reproduce the exact same 20 findings.
"""
import csv, json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs_v2")
os.makedirs(OUT, exist_ok=True)

# ---- ADP-style export: pipe-delimited, "Last, F." names, SSNs, footer total ----
with open(os.path.join(OUT, "adp_payroll_export.txt"), "w") as f:
    f.write("ADP Workforce Now (r) - Payroll Register Export\n")
    f.write("Company: BLUERIDGE MECHANICAL CONTRACTORS INC   Period: policy year ending 02/01/2026\n")
    f.write("Generated: 08/20/2026 -- CONFIDENTIAL\n")
    f.write("\n")
    f.write("File #|Employee Name|SSN|Home Dept|State Worked|Gross Pay|O.T. Premium|Officer\n")
    f.write("001482|Marsh, T.|000-14-8200|ADMIN|NY|182,000.00|0.00|Y\n")
    f.write("001519|Chen, L.|000-15-1900|HVAC-INSTALL|NY|68,800.00|5,400.00|N\n")
    f.write("001533|Novak, R.|000-15-3300|HVAC-INSTALL|PA|63,200.00|4,480.00|N\n")
    f.write("\n")
    f.write("TOTAL||||314,000.00 (gross)||\n")

# ---- Gusto-style CSV: its own headers, per-employee OT itemization flag ----
with open(os.path.join(OUT, "gusto_payroll_report.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["employee_name", "ssn", "work_state", "role", "total_wages", "overtime_premium", "ot_itemized"])
    w.writerow(["D. Ruiz", "000-16-0400", "TX", "installer", "56400.00", "3560.00", "no"])
    w.writerow(["A. Boone", "000-16-2200", "TX", "sales", "49200.00", "0.00", "yes"])
    w.writerow(["S. Adeyemi", "000-16-4700", "NJ", "installer", "64000.00", "3760.00", "yes"])

# ---- QuickBooks-style text summary: two-column-ish, officer marked in name ----
with open(os.path.join(OUT, "qb_payroll_summary.txt"), "w") as f:
    f.write("BlueRidge Mechanical Contractors Inc\n")
    f.write("QuickBooks Payroll Summary - policy year ending 02/01/2026\n")
    f.write("\n")
    f.write("Name                          SSN            State   Dept       Gross\n")
    f.write("P. Marsh (Officer)            000-17-0900    FL      Admin      120,000.00\n")
    f.write("K. Ilsley                     000-17-3800    WA      Install    55,600.00\n")
    f.write("\n")
    f.write("Report total gross wages: 175,600.00\n")

# ---- Form 941 roll-up (text) ----
with open(os.path.join(OUT, "form_941_rollup.txt"), "w") as f:
    f.write("FORM 941 ROLL-UP -- four quarters, policy year ending 02/01/2026\n")
    f.write("Employer: BlueRidge Mechanical Contractors Inc  EIN: 00-0000000\n")
    f.write("Line 1   Number of employees ..................... 8\n")
    f.write("Line 2   Wages, tips, and other compensation ..... 671,600.00\n")
    f.write("Line 3   Federal income tax withheld ............. 84,120.00\n")

# ---- SUTA wage report (text) ----
with open(os.path.join(OUT, "suta_wage_report.txt"), "w") as f:
    f.write("STATE UNEMPLOYMENT WAGE REPORT ROLL-UP - policy year ending 02/01/2026\n")
    f.write("Employer account: 0000000-0\n")
    f.write("Total wages reported ......... 671,600.00\n")
    f.write("Employee count ............... 8\n")

# ---- GL export: its own column names ----
with open(os.path.join(OUT, "gl_export.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Txn Date", "Vendor", "Description", "Amt", "COI on File", "Job State", "Materials Documented"])
    w.writerow(["2025-06-14", "Garden State Mech LLC", "sub - ductwork install", "52300.00", "N", "NJ", "N"])
    w.writerow(["2025-09-03", "Keystone Duct Co", "sub - fabrication + install", "18000.00", "N", "PA", "Y"])
    w.writerow(["2025-11-21", "Empire Sheet Metal", "sub - rooftop units", "27650.00", "Y", "NY", "N"])

# ---- policy declarations (from the carrier assignment, not the insured) ----
with open(os.path.join(OUT, "policy_dec.json"), "w") as f:
    json.dump({
        "insured": "BlueRidge Mechanical Contractors Inc (fictional)",
        "effective_date": "2025-02-01",
        "expiration_date": "2026-02-01",
        "estimated_annual_premium": 26500,
        "governing_class": "5537",
        "class_rates_per_100": {"5537": 9.44, "8810": 0.28, "8742": 0.51},
        "period": "final audit, policy year ending 2026-02-01",
        "as_of_date": "2026-08-25",
        "weeks_in_period": 52,
        "insured_noncompliant": True,
        "contact_attempts_documented": 1,
        "dept_class_map": {
            "ADMIN": "8810", "HVAC-INSTALL": "5537",
            "installer": "5537", "sales": "8742",
            "Admin": "8810", "Install": "5537"
        }
    }, f, indent=2)

# ---- ground truth (TEST-ONLY sidecar; never present in production) ----
with open(os.path.join(OUT, "ground_truth.json"), "w") as f:
    json.dump({
        "expected_employees": 8,
        "expected_register_total": 659200.00,
        "expected_941": 671600.00,
        "expected_ssns_tokenized": 8,
        "expected_findings": [
            "MONO-WA", "TRIANGLE-941",
            "OT-STATE-PA-R.Novak", "OT-RECORDS-TX-D.Ruiz", "OT-STATE-NJ-S.Adeyemi",
            "OFFICER-VERIFY-NY", "OFFICER-VERIFY-FL",
            "SUB-NOCOI-NJ", "SUB-NOCOI-PA",
            "AUDITTYPE-FL", "AUDITTYPE-NJ", "AUDITTYPE-NY", "AUDITTYPE-PA", "AUDITTYPE-TX",
            "DEADLINE-NY", "ANC-NA-TX",
            "ANC-NOTELIGIBLE-FL", "ANC-NOTELIGIBLE-NJ", "ANC-NOTELIGIBLE-NY", "ANC-NOTELIGIBLE-PA"
        ]
    }, f, indent=2)

print("docs_v2 written:", sorted(os.listdir(OUT)))
