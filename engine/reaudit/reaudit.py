"""The 50-file re-audit flow: engine findings vs. the incumbent vendor's decisions.

For each file: run the v1.1 engine on the underlying records, then compare
every actionable finding against what the vendor's audit actually did:

  TRIANGLE-941       vs vendor.charged_941_delta      -> missed_941_delta
  OT-STATE/OT-RECORDS vs vendor.ot_exclusions_allowed -> improper_ot_exclusion
  OFFICER-*-CAP      vs vendor.officer_capped         -> officer_cap_not_applied (refund)
  SUB-NOCOI          vs vendor.subs_charged           -> missed_uninsured_sub
  review-severity findings                            -> the review queue, never "vendor error"
  info-severity findings                              -> ignored (not audit decisions)

A discrepancy exists only when the engine's finding and the vendor's decision
DISAGREE — a vendor who denied an exclusion the engine also denies is correct,
and a clean file must produce zero discrepancies. Self-test: found errors match
the seeded ground truth exactly, per file and per type.

Output: results.json (consumed by report_html.py) + console summary.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from audit_engine import Rules, audit

def classify(findings, vendor):
    errors, review = [], []
    for f in findings:
        sev = f["severity"]
        if sev == "info":
            continue
        if sev == "review":
            review.append(f)
            continue
        fid = f["id"]
        if fid.startswith("TRIANGLE-941") and not vendor["charged_941_delta"]:
            errors.append(("missed_941_delta", f))
        elif (fid.startswith("OT-STATE") or fid.startswith("OT-RECORDS")) \
                and f["subject"] in vendor["ot_exclusions_allowed"]:
            kind = "improper_ot_exclusion_state" if fid.startswith("OT-STATE") else "improper_ot_exclusion_records"
            errors.append((kind, f))
        elif "-CAP" in fid and fid.startswith("OFFICER") and not vendor["officer_capped"]:
            errors.append(("officer_cap_not_applied", f))
        elif fid.startswith("SUB-NOCOI") and f["subject"] not in vendor["subs_charged"]:
            errors.append(("missed_uninsured_sub", f))
    return errors, review

def main():
    book = json.load(open(os.path.join(HERE, "book_demo", "book.json")))
    rules = Rules()
    results, ok = [], True
    tot_under, tot_over = 0.0, 0.0

    for f in book["files"]:
        case = {"policy": f["policy"], "form_941": {"line2_wages_tips_comp": f["f941_total"]},
                "suta_total_wages": f["f941_total"], "as_of_date": "2026-08-25",
                "weeks_in_period": 52, "insured_noncompliant": False,
                "contact_attempts_documented": 2}
        findings = audit(case, f["register"], f["gl"], rules)
        errors, review = classify(findings, f["vendor"])
        found_types = sorted(t for t, _ in errors)
        expected = sorted(f["expected_errors"])
        match = found_types == expected and len(review) == len(f["expected_review"])
        ok = ok and match
        under = sum(fd["premium_impact"] for _, fd in errors if fd["premium_impact"] > 0)
        over = sum(-fd["premium_impact"] for _, fd in errors if fd["premium_impact"] < 0)
        tot_under += under
        tot_over += over
        results.append({
            "file_id": f["file_id"], "insured": f["insured"], "state": f["state"],
            "errors": [{"type": t, "finding": fd["finding"], "rule": fd["rule"],
                        "impact": round(fd["premium_impact"], 2)} for t, fd in errors],
            "review": [{"finding": fd["finding"], "rule": fd["rule"]} for fd in review],
            "undercharge": round(under, 2), "overcharge": round(over, 2),
            "self_test": "PASS" if match else f"FAIL (found {found_types}, expected {expected})",
        })

    error_files = [r for r in results if r["errors"]]
    review_files = [r for r in results if r["review"]]
    clean_flagged = [r for r in results if not json.loads(json.dumps(r["errors"])) and r["self_test"] != "PASS"]
    summary = {
        "prospect": book["prospect"], "run_date": "2026-08-25",
        "files": len(results), "files_with_vendor_errors": len(error_files),
        "file_error_rate": round(len(error_files) / len(results), 3),
        "total_errors": sum(len(r["errors"]) for r in results),
        "missed_premium_undercharges": round(tot_under, 2),
        "overcharges_refund_due": round(tot_over, 2),
        "net_premium_impact": round(tot_under - tot_over, 2),
        "review_queue_files": len(review_files),
        "industry_benchmark_error_rate": 0.12,
        "all_self_tests_pass": ok,
    }
    with open(os.path.join(HERE, "results.json"), "w") as fp:
        json.dump({"summary": summary, "results": results}, fp, indent=1)

    print("=" * 74)
    print(f"RE-AUDIT RUN — {book['prospect']}")
    print("=" * 74)
    for r in error_files:
        print(f"{r['file_id']}  {r['insured'][:38]:38} errors={len(r['errors'])}  "
              f"under=${r['undercharge']:,.2f}  over=${r['overcharge']:,.2f}")
        for e in r["errors"]:
            print(f"        [{e['type']}] {e['finding'][:96]}")
    for r in review_files:
        print(f"{r['file_id']}  {r['insured'][:38]:38} -> REVIEW QUEUE ({len(r['review'])})")
    print("-" * 74)
    print(f"files={summary['files']}  error files={summary['files_with_vendor_errors']} "
          f"({summary['file_error_rate']:.0%} vs industry ~12%)  errors={summary['total_errors']}")
    print(f"missed premium (undercharges): ${summary['missed_premium_undercharges']:,.2f}")
    print(f"overcharges (refund due):      ${summary['overcharges_refund_due']:,.2f}")
    print(f"review queue: {summary['review_queue_files']} files")
    print(f"\nSELF-TEST (50 files, per-file type match + clean-file zero-flag): "
          f"{'ALL PASS' if ok else 'FAILURES: ' + str([r['file_id'] + ' ' + r['self_test'] for r in results if r['self_test'] != 'PASS'])}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
