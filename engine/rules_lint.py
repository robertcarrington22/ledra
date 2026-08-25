"""Rules library linter — schema validation + provenance census for state_rules.json.

Run after any rules edit. Checks:
  - every entry is {value, provenance[, source, note]} with provenance in {sourced, verify}
  - every 'sourced' entry carries a source citation
  - every 'verify' entry carries a note saying what to confirm
  - no unknown top-level keys; states are 2-letter codes
Prints the provenance census (sourced vs verify, per state) — the number that
should go UP as real regulatory data replaces placeholders.
"""
import json, os, sys

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_rules.json")
raw = json.load(open(PATH))
problems, sourced, verify = [], 0, 0

def check_table(scope, table):
    global sourced, verify
    for key, entry in table.items():
        if not isinstance(entry, dict) or "provenance" not in entry \
                or ("value" not in entry and "vintages" not in entry):
            problems.append(f"{scope}.{key}: entry must be {{value|vintages, provenance, ...}}")
            continue
        if "vintages" in entry:
            vs = entry["vintages"]
            if not vs or any("effective" not in v or "value" not in v for v in vs):
                problems.append(f"{scope}.{key}: each vintage needs {{effective, value}}")
            if [v["effective"] for v in vs] != sorted(v["effective"] for v in vs):
                problems.append(f"{scope}.{key}: vintages must be in ascending effective order")
            if "unit" not in entry:
                problems.append(f"{scope}.{key}: vintaged entry must declare its unit (weekly/annual)")
        prov = entry["provenance"]
        if prov == "sourced":
            sourced += 1
            if not entry.get("source") and not entry.get("note"):
                problems.append(f"{scope}.{key}: sourced but no source citation")
        elif prov == "verify":
            verify += 1
            if not entry.get("note"):
                problems.append(f"{scope}.{key}: verify but no note on what to confirm")
        else:
            problems.append(f"{scope}.{key}: provenance '{prov}' not in {{sourced, verify}}")

check_table("default_ncci", raw["default_ncci"])
per_state = {}
for st, table in raw["states"].items():
    if len(st) != 2 or not st.isupper():
        problems.append(f"states.{st}: not a 2-letter state code")
    before = verify
    check_table(f"states.{st}", table)
    per_state[st] = sum(1 for e in table.values() if isinstance(e, dict) and e.get("provenance") == "verify")

print("=" * 56)
print("RULES LIBRARY LINT — state_rules.json")
print("=" * 56)
print(f"version: {raw['_meta'].get('version')}  compiled: {raw['_meta'].get('compiled')}")
print(f"entries: {sourced + verify}  sourced: {sourced}  verify: {verify}  "
      f"({sourced / max(1, sourced + verify):.0%} sourced)")
open_verify = {st: n for st, n in per_state.items() if n}
print(f"states with open VERIFY items: {open_verify or 'NONE'}")
if problems:
    print("\nPROBLEMS:")
    for p in problems:
        print(f"  - {p}")
print(f"\nLINT: {'CLEAN' if not problems else 'FAILED'}")
sys.exit(0 if not problems else 1)
