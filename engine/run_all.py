"""Master test runner — every suite in the stack, one verdict.

  1. v1 engine on the hand-built multi-state case (20 findings exact)
  2. v2 document extraction pipeline (6 checks)
  3. v2.1 hybrid payroll-API pipeline (8 checks incl. negative tests)
  4. 50-file re-audit flow (50 per-file self-tests, false-positive discipline)
  5. robustness suite (engine guards + extraction fuzzing)
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python"

SUITES = [
    ("engine v1 multi-state case", [PY, "audit_engine.py"], HERE),
    ("v2 document extraction",     [PY, "pipeline.py"], os.path.join(HERE, "extract")),
    ("v2.1 hybrid API pipeline",   [PY, "pipeline_v21.py"], os.path.join(HERE, "extract")),
    ("50-file re-audit flow",      [PY, "reaudit.py"], os.path.join(HERE, "reaudit")),
    ("robustness suite",           [PY, "tests_robustness.py"], HERE),
]

results, ok = [], True
for name, cmd, cwd in SUITES:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    passed = r.returncode == 0
    ok = ok and passed
    results.append((name, passed, r))

print("=" * 62)
print("AUDIT HOUSE — FULL TEST MATRIX")
print("=" * 62)
for name, passed, r in results:
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if not passed:
        tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
        for line in tail:
            print(f"         {line}")
print("-" * 62)
print(f"{'ALL SUITES PASS' if ok else 'SUITE FAILURES — see above'}")
sys.exit(0 if ok else 1)
