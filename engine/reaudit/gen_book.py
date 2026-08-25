"""Generate a synthetic 50-file re-audit book.

Simulates a prospect handing over 50 completed audits from their incumbent
vendor: for each file, the underlying records (register, GL, 941/SUTA) PLUS
the vendor's audit decisions. Errors are seeded at roughly the industry rate
(WCIRB test audits find errors in ~12% of audits): 7 files carry 8 vendor
errors across five error types; 2 files carry a pre-vintage NY officer that
must route to human review (not be called a vendor error); 41 files are clean
and must produce ZERO discrepancies — false-positive discipline is the test.

Everything is fictional and deterministic (seeded RNG).
"""
import json, os, random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "book_demo")
os.makedirs(OUT, exist_ok=True)
rng = random.Random(42)

NAMES = ["Cardinal", "Bluestone", "Harbor", "Summit Ridge", "Ironwood", "Lakeshore", "Redbud",
         "Granite", "Pinehurst", "Fox Hollow", "Copper Creek", "Meridian", "Oakline", "Stonebridge",
         "Riverbend", "Highland", "Cedarworks", "Palmetto", "Bay Colony", "Northfield", "Juniper",
         "Millbrook", "Sagebrush", "Timberline", "Westgate"]
TRADES = [("Plumbing", "5183", 6.20), ("Electrical", "5190", 4.85), ("Landscaping", "0042", 8.12),
          ("HVAC", "5537", 9.44), ("Roofing", "5551", 22.10), ("Janitorial", "9014", 5.05)]
CLEAN_STATES = ["FL", "TX", "WI", "NY", "PA"]

ERROR_PLAN = {
    3:  ["improper_ot_exclusion_state"],      # vendor allowed OT exclusion in PA
    9:  ["missed_uninsured_sub"],
    14: ["missed_941_delta"],
    22: ["officer_cap_not_applied"],          # overcharge -> refund due
    28: ["improper_ot_exclusion_records"],    # TX, no per-employee breakout
    35: ["missed_uninsured_sub"],             # PA, materials documented (fractional)
    41: ["missed_941_delta", "missed_uninsured_sub"],
}
REVIEW_PLAN = {17: "pre_vintage_officer_review", 44: "pre_vintage_officer_review"}

def base_file(i):
    name = f"{NAMES[i % len(NAMES)]} {TRADES[i % len(TRADES)][0]} {'Inc' if i % 2 else 'LLC'}"
    trade, cls, rate = TRADES[i % len(TRADES)]
    st = CLEAN_STATES[i % len(CLEAN_STATES)]
    n_emp = rng.randint(2, 4)
    employees, total = [], 0.0
    for j in range(n_emp):
        gross = round(rng.uniform(38000, 72000), 2)
        total += gross
        employees.append({"employee": f"E{j+1} {name.split()[0]}", "state": st, "class_code": cls,
                          "gross_wages": f"{gross:.2f}", "ot_premium_pay": "0.00",
                          "ot_detail_by_employee": "Y", "is_officer": "N"})
    return {
        "file_id": f"RA-{i+1:03d}", "insured": f"{name} (fictional)", "state": st,
        "class_code": cls, "rate": rate,
        "register": employees, "gl": [],
        "f941_total": round(total, 2),
        "policy": {"insured": f"{name} (fictional)", "effective_date": "2025-10-15",
                   "expiration_date": "2026-06-30",
                   "estimated_annual_premium": round(total * rate / 100, 2),
                   "governing_class": cls, "class_rates_per_100": {cls: rate, "8810": 0.28}},
        "vendor": {"charged_941_delta": False, "ot_exclusions_allowed": [],
                   "subs_charged": [], "officer_capped": False},
        "expected_errors": [], "expected_review": [],
    }

book = []
for i in range(50):
    f = base_file(i)
    errors = ERROR_PLAN.get(i, [])
    for err in errors:
        if err == "improper_ot_exclusion_state":
            e = f["register"][0]
            e["state"] = "PA"
            e["ot_premium_pay"] = f"{rng.uniform(2200, 4800):.2f}"
            f["vendor"]["ot_exclusions_allowed"].append(e["employee"])
        elif err == "improper_ot_exclusion_records":
            e = f["register"][0]
            e["state"] = "TX"
            e["ot_premium_pay"] = f"{rng.uniform(1800, 4200):.2f}"
            e["ot_detail_by_employee"] = "N"
            f["vendor"]["ot_exclusions_allowed"].append(e["employee"])
        elif err == "missed_941_delta":
            delta = round(rng.uniform(6000, 15000), 2)
            f["f941_total"] = round(f["f941_total"] + delta, 2)
            # vendor accepted the register total without reconciling
        elif err == "missed_uninsured_sub":
            materials = (i == 35)
            f["gl"].append({"date": "2026-01-15", "payee": f"Sub-{f['file_id']} LLC",
                            "memo": "subcontract labor", "amount": f"{rng.uniform(14000, 46000):.2f}",
                            "coi_on_file": "N", "work_state": "PA" if materials else f["state"],
                            "materials_documented": "Y" if materials else "N"})
            # vendor never pulled the GL -> subs_charged stays empty
        elif err == "officer_cap_not_applied":
            e = f["register"][0]
            e["state"] = "NY"
            e["is_officer"] = "Y"
            e["class_code"] = "8810"
            e["gross_wages"] = "191000.00"   # over the NY cap of 176,800
            # vendor charged full officer payroll -> officer_capped stays False
            # keep the 941 consistent with the mutated register (the error here
            # is the missing cap, not a reconciliation delta)
            f["f941_total"] = round(sum(float(x["gross_wages"]) for x in f["register"]), 2)
    if i in REVIEW_PLAN:
        # NY officer on a policy effective BEFORE the earliest NYCIRB vintage in
        # the library -> band unresolved -> routed to review, never guessed.
        # (NJ OT no longer works as a review case: NJCRIB Rule 35 was confirmed
        # 8/25/2026, so NJ OT exclusions are now hard denials.)
        f["policy"]["effective_date"] = "2025-05-01"
        first_word = f["insured"].split()[0]
        officer = {"employee": f"OFC {first_word}", "state": "NY", "class_code": "8810",
                   "gross_wages": "52000.00", "ot_premium_pay": "0.00",
                   "ot_detail_by_employee": "Y", "is_officer": "Y"}
        f["register"].append(officer)
        f["f941_total"] = round(sum(float(x["gross_wages"]) for x in f["register"]), 2)
        f["expected_review"] = [officer["employee"]]
    # clean files also get a properly-insured sub sometimes (must NOT flag)
    if not errors and i % 7 == 0:
        f["gl"].append({"date": "2026-02-10", "payee": f"Insured Sub {i} Inc",
                        "memo": "subcontract labor", "amount": f"{rng.uniform(9000, 20000):.2f}",
                        "coi_on_file": "Y", "work_state": f["state"], "materials_documented": "N"})
    f["expected_errors"] = errors
    book.append(f)

with open(os.path.join(OUT, "book.json"), "w") as fp:
    json.dump({"prospect": "Demo Carrier (fictional) — incumbent vendor book",
               "generated": "2026-08-25", "files": book}, fp, indent=1)

n_err = sum(1 for f in book if f["expected_errors"])
print(f"book written: {len(book)} files, {n_err} with seeded vendor errors "
      f"({n_err/len(book):.0%} file error rate), {len(REVIEW_PLAN)} review-queue files")
