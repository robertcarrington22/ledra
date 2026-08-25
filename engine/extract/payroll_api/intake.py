"""Payroll API intake — validated consent -> provider pull -> canonical register rows.

Normalization rules (the domain logic that makes API data audit-grade):
  - Gross = statement gross_pay; cross-checked against the earnings sum
  - OT: only an earnings line whose PREMIUM PORTION is identified counts as a
    per-employee breakout (ot_detail Y). An unallocated OT bucket is NOT a
    breakout — the NCCI records rule needs the premium portion, so those rows
    carry ot_detail N and the engine's records-deficiency denial still fires.
  - Officer flag from title (President/Officer/CEO/Treasurer/Secretary) —
    confirmed against the policy dec downstream by the human reviewer
  - Class codes resolve through the same dept->class map as document intake
"""
from datetime import date
from .providers import ConsentRecord, FinchStyleProvider

OFFICER_TITLES = ("president", "officer", "chief executive", "treasurer", "secretary")

def pull_via_api(fixtures_dir, consent_raw, as_of_iso, dept_class_map):
    consent = ConsentRecord(consent_raw).validate(date.fromisoformat(as_of_iso))
    provider = FinchStyleProvider(fixtures_dir)

    directory = {p["individual_id"]: p for p in provider.directory(consent)}
    statements = provider.pay_statements(consent)

    rows, notes = [], []
    for s in statements:
        person = directory.get(s["individual_id"])
        if person is None:
            notes.append(f"statement {s['individual_id']} has no directory entry — routed to review")
            continue
        earn_sum = sum(e["amount"] for e in s["earnings"])
        if abs(earn_sum - s["gross_pay"]) > 0.01:
            notes.append(f"{s['individual_id']}: earnings sum {earn_sum:.2f} != gross {s['gross_pay']:.2f} — routed to review")
            continue
        ot_amount, ot_detail = 0.0, "Y"
        for e in s["earnings"]:
            if e["type"].startswith("overtime"):
                ot_amount += e["amount"]
                if not e.get("premium_portion_identified", False):
                    ot_detail = "N"   # an OT bucket is not an OT breakout
        dept = person["department"] if person["department"] in dept_class_map else person["department"].upper()
        cls = dept_class_map.get(person["department"]) or dept_class_map.get(dept)
        if cls is None:
            if person["department"] == "SALES":
                cls = dept_class_map.get("sales")
        if cls is None:
            notes.append(f"{s['individual_id']}: no class mapping for dept '{person['department']}' — routed to review")
            continue
        rows.append({
            "employee": f"{person['first_name']} {person['last_name']}",
            "state": person["location"]["state"],
            "class_code": cls,
            "gross_wages": f"{s['gross_pay']:.2f}",
            "ot_premium_pay": f"{ot_amount:.2f}",
            "ot_detail_by_employee": ot_detail,
            "is_officer": "Y" if any(t in person["title"].lower() for t in OFFICER_TITLES) else "N",
        })
    coverage = {
        "provider": consent.raw["provider"],
        "connection_id": consent.raw["connection_id"],
        "consent": {k: consent.raw[k] for k in ("authorized_by", "method", "granted_at", "expires_at", "scopes")},
        "individuals_in_directory": len(directory),
        "rows_normalized": len(rows),
        "api_gross_total": round(sum(float(r["gross_wages"]) for r in rows), 2),
        "review_notes": notes,
    }
    return rows, coverage
