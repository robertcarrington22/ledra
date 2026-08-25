"""End-to-end v2 pipeline test: vendor documents -> extraction -> v1 engine.

Pass criteria (all must hold):
  1. Every file's format detected; zero unparsed lines across adapters
  2. All SSNs tokenized at ingestion (count matches ground truth); no plaintext
     SSN appears anywhere in the normalized case directory
  3. Extracted register total and 941 match ground truth to the cent
  4. The v1 engine reproduces EXACTLY the same 20 findings from the extracted
     case as it does from the hand-built case_v1 (no misses, no extras)
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import audit_engine
from extractors import extract_case, SSN_RE

def main():
    docs = os.path.join(HERE, "docs_v2")
    out = os.path.join(HERE, "case_v2")
    truth = json.load(open(os.path.join(docs, "ground_truth.json")))

    print("=" * 78)
    print("EXTRACTION STAGE")
    print("=" * 78)
    summary = extract_case(docs, out)
    for r in summary["files"]:
        flag = "" if not r["unparsed_lines"] else f"  !! {len(r['unparsed_lines'])} unparsed lines"
        print(f"  {r['file']:28} -> {r['format']:15} rows={r['rows']}{flag}")
    print(f"  employees={summary['employees']}  register_total=${summary['register_total']:,.2f}"
          f"  ssns_tokenized={summary['ssns_tokenized']}")

    checks = []
    checks.append(("all formats detected, zero unparsed lines",
                   all(not r["unparsed_lines"] for r in summary["files"])))
    checks.append((f"ssns tokenized == {truth['expected_ssns_tokenized']}",
                   summary["ssns_tokenized"] == truth["expected_ssns_tokenized"]))
    leaked = False
    for fname in os.listdir(out):
        if SSN_RE.search(open(os.path.join(out, fname), encoding="utf-8", errors="replace").read()):
            leaked = True
    checks.append(("no plaintext SSN in normalized case dir", not leaked))
    checks.append((f"register total == ${truth['expected_register_total']:,.2f}",
                   abs(summary["register_total"] - truth["expected_register_total"]) < 0.01))
    case = json.load(open(os.path.join(out, "case.json")))
    checks.append((f"941 == ${truth['expected_941']:,.2f}",
                   abs(case["form_941"]["line2_wages_tips_comp"] - truth["expected_941"]) < 0.01))

    print("\n" + "=" * 78)
    print("ENGINE STAGE (v1 engine on extracted case)")
    print("=" * 78)
    engine_rc = audit_engine.run(out)
    checks.append(("engine 20/20 findings on extracted case", engine_rc == 0))

    print("\n" + "=" * 78)
    print("PIPELINE SELF-TEST")
    print("=" * 78)
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print(f"\nV2 PIPELINE: {'ALL CHECKS PASS' if ok else 'FAILED'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
