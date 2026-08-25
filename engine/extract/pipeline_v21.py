"""v2.1 hybrid pipeline test: payroll API intake + document fallback -> v1 engine.

The realistic case: the insured authorizes payroll-connect for their main
payroll system (6 of 8 employees, via the Finch-style provider), while the
FL/WA population lives on a separate local payroll and still arrives as a
QuickBooks document — plus 941/SUTA/GL as documents. The pipeline must merge
both intake paths into one canonical case and reproduce the exact 20 findings.

Also exercises the guardrails with NEGATIVE tests:
  - a provider call without validated consent must be refused
  - a consent record requesting the SSN scope must be rejected (data minimization)
  - an API OT bucket without an identified premium portion must NOT count as a
    per-employee breakout (D. Ruiz's records-deficiency denial survives the API)
"""
import copy, csv, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import audit_engine
from extractors import extract_case, SSN_RE
from payroll_api.intake import pull_via_api
from payroll_api.providers import ConsentError, ConsentRecord, FinchStyleProvider

DOC_FILES = ["qb_payroll_summary.txt", "form_941_rollup.txt", "suta_wage_report.txt",
             "gl_export.csv", "policy_dec.json", "ground_truth.json"]

def main():
    docs_all = os.path.join(HERE, "docs_v2")
    fixtures = os.path.join(HERE, "payroll_api", "api_fixtures")
    hybrid = os.path.join(HERE, "hybrid_docs")
    out = os.path.join(HERE, "case_v21")
    checks = []

    # ---- assemble the hybrid document set (main-payroll registers absent) ----
    # OneDrive/Windows can hold locks on recently-touched dirs — overwrite in
    # place rather than rmtree, and only create if absent
    if os.path.isdir(hybrid):
        for f in os.listdir(hybrid):
            if f not in DOC_FILES:
                try:
                    os.remove(os.path.join(hybrid, f))
                except OSError:
                    pass
    else:
        os.makedirs(hybrid)
    for f in DOC_FILES:
        shutil.copy(os.path.join(docs_all, f), os.path.join(hybrid, f))
    truth = json.load(open(os.path.join(docs_all, "ground_truth.json")))
    policy = json.load(open(os.path.join(docs_all, "policy_dec.json")))
    consent = json.load(open(os.path.join(fixtures, "consent.json")))

    print("=" * 78)
    print("GUARDRAIL STAGE (negative tests)")
    print("=" * 78)
    try:
        FinchStyleProvider(fixtures).directory(ConsentRecord(consent))  # not validated
        checks.append(("provider refuses unvalidated consent", False))
    except ConsentError as e:
        print(f"  refused as expected: {e}")
        checks.append(("provider refuses unvalidated consent", True))
    try:
        bad = copy.deepcopy(consent)
        bad["scopes"].append("ssn")
        ConsentRecord(bad).validate(__import__("datetime").date.fromisoformat(policy["as_of_date"]))
        checks.append(("SSN scope rejected (data minimization)", False))
    except ConsentError as e:
        print(f"  rejected as expected: {e}")
        checks.append(("SSN scope rejected (data minimization)", True))

    print("\n" + "=" * 78)
    print("API INTAKE STAGE")
    print("=" * 78)
    api_rows, coverage = pull_via_api(fixtures, consent, policy["as_of_date"], policy["dept_class_map"])
    print(f"  provider={coverage['provider']}  connection={coverage['connection_id']}")
    print(f"  consent: {coverage['consent']['authorized_by']} via {coverage['consent']['method']}")
    print(f"  rows={coverage['rows_normalized']}  api_gross=${coverage['api_gross_total']:,.2f}"
          f"  review_notes={len(coverage['review_notes'])}")
    checks.append(("API intake: 6 rows normalized, zero review notes",
                   coverage["rows_normalized"] == 6 and not coverage["review_notes"]))
    ruiz = next((r for r in api_rows if r["employee"] == "D. Ruiz"), None)
    checks.append(("OT bucket != OT breakout (D. Ruiz ot_detail = N via API)",
                   ruiz is not None and ruiz["ot_detail_by_employee"] == "N"))

    print("\n" + "=" * 78)
    print("DOCUMENT INTAKE STAGE (fallback population)")
    print("=" * 78)
    doc_summary = extract_case(hybrid, out)
    print(f"  doc employees={doc_summary['employees']}  doc register total=${doc_summary['register_total']:,.2f}")

    # ---- merge: API rows + doc rows, duplicate-guarded ----
    reg_path = os.path.join(out, "payroll_register.csv")
    doc_rows = list(csv.DictReader(open(reg_path)))
    dup = {r["employee"] for r in doc_rows} & {r["employee"] for r in api_rows}
    checks.append(("intake paths disjoint (no employee in both)", not dup))
    merged = doc_rows + api_rows
    with open(reg_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["employee", "state", "class_code", "gross_wages",
                                          "ot_premium_pay", "ot_detail_by_employee", "is_officer"])
        w.writeheader(); w.writerows(merged)
    total = sum(float(r["gross_wages"]) for r in merged)
    print(f"  merged employees={len(merged)}  combined register total=${total:,.2f}")
    checks.append((f"merged register == ${truth['expected_register_total']:,.2f} across 8 employees",
                   len(merged) == truth["expected_employees"]
                   and abs(total - truth["expected_register_total"]) < 0.01))
    with open(os.path.join(out, "intake_coverage.json"), "w") as f:
        json.dump({"api": coverage, "documents": {"employees": doc_summary["employees"],
                   "files": [r["file"] for r in doc_summary["files"]]}}, f, indent=2)

    print("\n" + "=" * 78)
    print("ENGINE STAGE (v1 engine on hybrid case)")
    print("=" * 78)
    engine_rc = audit_engine.run(out)
    checks.append(("engine 20/20 findings on hybrid case", engine_rc == 0))

    leaked = any(SSN_RE.search(open(os.path.join(out, f), encoding="utf-8", errors="replace").read())
                 for f in os.listdir(out))
    checks.append(("no plaintext SSN in hybrid case dir", not leaked))

    print("\n" + "=" * 78)
    print("V2.1 PIPELINE SELF-TEST")
    print("=" * 78)
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print(f"\nV2.1 PIPELINE: {'ALL CHECKS PASS' if ok else 'FAILED'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
