"""Audit House engine v1.1 — state-aware premium audit core.

v1 proved state-resolved rules (see README). v1.1 splits the engine into a
programmatic API and a CLI so other harnesses (the 50-file re-audit flow, the
future QA sampler) can call it directly:

  audit(case, register, gl, rules) -> findings   # pure: no I/O, no printing
  run(case_dir)                                  # CLI: load, audit, worksheet, self-test

Findings carry a `subject` (employee or payee) so downstream harnesses can map
them to a vendor's audit decisions without parsing prose.
"""
import csv, json, os, sys
from datetime import date

def money(x): return f"${x:,.2f}"

# ---------------- rules resolution ----------------
class Rules:
    def __init__(self, path=None):
        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_rules.json")
        raw = json.load(open(path))
        self.default = raw["default_ncci"]
        self.states = raw["states"]
        self.verify_hits = []   # (state, key, value, note)

    def get(self, state, key, default_value=None, on_date=None):
        """Resolve a rule for a state: state override -> NCCI default -> fallback.
        Vintaged entries resolve by `on_date` (policy effective date, ISO string):
        the latest vintage effective on/before that date wins; a date before the
        earliest known vintage resolves to None and is VERIFY-queued — the
        engine routes to review rather than applying the wrong policy year."""
        for scope, table in ((state, self.states.get(state, {})), ("default", self.default)):
            if key in table:
                entry = table[key]
                if entry.get("provenance") == "verify":
                    self.verify_hits.append((state, key, entry.get("value"),
                                             entry.get("note", "confirm against current tables")))
                if "vintages" in entry:
                    vs = sorted(entry["vintages"], key=lambda v: v["effective"])
                    if on_date is None:
                        return vs[-1]["value"], entry
                    chosen = None
                    for v in vs:
                        if v["effective"] <= on_date:
                            chosen = v
                    if chosen is None:
                        self.verify_hits.append((state, key, None,
                                                 f"no vintage on/before {on_date}; earliest known is {vs[0]['effective']}"))
                        return None, entry
                    return chosen["value"], entry
                return entry.get("value"), entry
        return default_value, None

    def monopolistic(self, state):
        v, _ = self.get(state, "monopolistic", False)
        return bool(v)

# ---------------- the audit (pure) ----------------
def audit(case, register, gl, rules):
    findings = []

    def add(fid, sev, state, finding, evidence, action, impact, rule_cite, subject=None):
        findings.append({"id": fid, "severity": sev, "state": state, "finding": finding,
                         "evidence": evidence, "action": action, "premium_impact": impact,
                         "rule": rule_cite, "subject": subject})

    rates = case["policy"]["class_rates_per_100"]
    gov_class = case["policy"]["governing_class"]

    # policy effective date drives vintage resolution (officer tables etc. turn
    # over on per-state policy-year cycles). Fallback: expiration minus one year.
    eff_date = case["policy"].get("effective_date")
    if not eff_date:
        exp_d = date.fromisoformat(case["policy"]["expiration_date"])
        eff_date = exp_d.replace(year=exp_d.year - 1).isoformat()

    # ---- guard: monopolistic states ----
    in_scope = []
    for e in register:
        st = e["state"]
        if rules.monopolistic(st):
            add(f"MONO-{st}", "high", st,
                f"{e['employee']} works in {st}, a monopolistic state fund jurisdiction — payroll is out of scope for this policy's audit.",
                f"payroll_register.csv state={st}",
                f"Exclude from auditable payroll; confirm insured carries {st} state-fund coverage.",
                0.0, f"{st} monopolistic (sourced)", subject=e["employee"])
        else:
            in_scope.append(e)

    reg_total = sum(float(e["gross_wages"]) for e in in_scope)

    # ---- guard: zero/empty payroll ----
    if not in_scope or reg_total <= 0.0:
        add("ZERO-PAYROLL", "review", "ALL",
            "No auditable payroll in scope — empty register or all wages excluded/zero. This is either a ghost policy, a records failure, or total monopolistic-state exposure.",
            f"in-scope employees={len(in_scope)}, register total={money(reg_total)}",
            "Route to reviewer: verify operations ceased vs. records withheld; consider estimated audit / minimum premium handling.",
            0.0, "audit completeness guard (structural)")

    # ---- guard: interchange of labor (one employee, multiple class codes) ----
    by_name = {}
    for e in in_scope:
        by_name.setdefault(e["employee"], set()).add(e["class_code"])
    for name, classes in by_name.items():
        if len(classes) > 1:
            st = next(e["state"] for e in in_scope if e["employee"] == name)
            add(f"INTERCHANGE-{name.replace(' ', '')}", "review", st,
                f"{name} has payroll divided across classes {sorted(classes)} — interchange-of-labor division requires verifiable original payroll records per class; unverifiable splits go to the highest-rated class.",
                "payroll register: duplicate employee across class codes",
                "Reviewer verifies the division against original records before accepting the split.",
                0.0, "NCCI interchange-of-labor rule (sourced)", subject=name)

    # ---- check 1: reconciliation triangle (941 / SUTA / register) ----
    f941 = case["form_941"]["line2_wages_tips_comp"]
    suta = case["suta_total_wages"]
    mono_excluded = sum(float(e["gross_wages"]) for e in register) - reg_total
    d941 = f941 - (reg_total + mono_excluded)
    if d941 > 1.0:
        add("TRIANGLE-941", "high", "ALL",
            f"Form 941 wages exceed the payroll register by {money(d941)} — unrecorded compensation missing from the register.",
            f"941 line 2 = {money(f941)}; register total (all states) = {money(reg_total + mono_excluded)}; SUTA = {money(suta)}",
            f"Add {money(d941)} to auditable payroll in governing class {gov_class} pending insured explanation.",
            d941 * rates[gov_class] / 100, "NCCI Basic Manual: remuneration verification (sourced)")
    elif d941 < -1.0:
        add("TRIANGLE-941-NEG", "review", "ALL",
            f"Payroll register EXCEEDS Form 941 wages by {money(-d941)} — possible non-taxable compensation in the register (Sec. 125, per-diems), a 941 filing error, or double-counted wages. Direction matters: this can mean the insured is due a REFUND.",
            f"941 line 2 = {money(f941)}; register total (all states) = {money(reg_total + mono_excluded)}; SUTA = {money(suta)}",
            "Route to reviewer: reconcile line-by-line before adjusting in either direction.",
            0.0, "reconciliation direction guard (structural)")

    # ---- check 2: overtime exclusion, state-resolved ----
    for e in in_scope:
        ot = float(e["ot_premium_pay"])
        if ot <= 0:
            continue
        st = e["state"]
        excludable, _ = rules.get(st, "ot_premium_excludable", True)
        breakout_required, _ = rules.get(st, "ot_requires_employee_breakout", True)
        cls = e["class_code"]
        who = e["employee"].replace(" ", "")
        if excludable is False:
            add(f"OT-STATE-{st}-{who}", "medium", st,
                f"{e['employee']}: {money(ot)} OT premium pay claimed for exclusion, but {st} does not permit the overtime exclusion — DENIED by state rule regardless of records.",
                f"register ot_premium_pay={money(ot)}; state={st}",
                "Deny exclusion; retain full amount in auditable payroll.",
                ot * rates[cls] / 100, f"{st} bureau rule: no OT exclusion (sourced)", subject=e["employee"])
        elif excludable is None:
            add(f"OT-VERIFY-{st}-{who}", "review", st,
                f"{e['employee']}: {money(ot)} OT exclusion requested in {st}, where OT treatment is UNCONFIRMED in the rules library — route to credentialed reviewer.",
                f"register ot_premium_pay={money(ot)}",
                f"Human review against the {st} bureau manual before allowing.",
                0.0, f"{st} OT treatment (verify)", subject=e["employee"])
        elif breakout_required and e["ot_detail_by_employee"] != "Y":
            add(f"OT-RECORDS-{st}-{who}", "medium", st,
                f"{e['employee']}: {money(ot)} OT premium pay not broken out by employee — exclusion DENIED for records deficiency.",
                "register ot_detail_by_employee=N",
                "Deny exclusion; notify insured of record-keeping requirement.",
                ot * rates[cls] / 100, "NCCI record-keeping requirement (sourced)", subject=e["employee"])

    # ---- check 3: officer min/max + sole proprietor basis, state- and date-resolved ----
    weeks = case.get("weeks_in_period", 13)

    def officer_band(st):
        """Resolve the officer payroll band for a state at the policy effective
        date. States publish weekly OR annual values; both normalize to the
        audit period. Returns (floor, cap, provenance) — None where unresolved."""
        cap = floor = None
        prov = "?"
        v, entry = rules.get(st, "officer_annual_max", None, on_date=eff_date)
        if v is not None:
            cap = v * weeks / 52.0
            prov = (entry or {}).get("provenance", "?")
        else:
            v, entry = rules.get(st, "officer_weekly_max", None, on_date=eff_date)
            if v is not None:
                cap = v * weeks
                prov = (entry or {}).get("provenance", "?")
        v, entry = rules.get(st, "officer_annual_min", None, on_date=eff_date)
        if v is not None:
            floor = v * weeks / 52.0
        else:
            v, entry = rules.get(st, "officer_weekly_min", None, on_date=eff_date)
            if v is not None:
                floor = v * weeks
        return floor, cap, prov

    def apply_band(e, prefix, label):
        st, gross = e["state"], float(e["gross_wages"])
        floor, cap, prov = officer_band(st)
        if cap is None:
            add(f"{prefix}-VERIFY-{st}", "review", st,
                f"{label.capitalize()} {e['employee']} in {st}: payroll band not resolved for policy effective {eff_date} — table missing or no vintage covers that date; route to reviewer.",
                f"register gross={money(gross)}",
                f"Load the {st} table vintage covering {eff_date}, then re-run.",
                0.0, f"{st} {label} band (unresolved for {eff_date})", subject=e["employee"])
            return
        if gross > cap:
            over = gross - cap
            add(f"{prefix}-{st}-CAP", "medium", st,
                f"{label.capitalize()} {e['employee']} payroll {money(gross)} exceeds the {st} maximum {money(cap)} for the period — {money(over)} excluded.",
                f"register vs {st} table (policy eff {eff_date})",
                f"Cap auditable payroll at {money(cap)}.",
                -over * rates[e["class_code"]] / 100,
                f"{st} {label} max ({prov}, vintage-resolved)", subject=e["employee"])
        elif floor is not None and gross < floor:
            under = floor - gross
            add(f"{prefix}-{st}-MIN", "medium", st,
                f"{label.capitalize()} {e['employee']} payroll {money(gross)} is below the {st} minimum {money(floor)} for the period — raise auditable payroll by {money(under)}.",
                f"register vs {st} table (policy eff {eff_date})",
                f"Charge payroll at the {st} minimum {money(floor)}.",
                under * rates[e["class_code"]] / 100,
                f"{st} {label} min ({prov}, vintage-resolved)", subject=e["employee"])

    for e in in_scope:
        role = e.get("entity_role", "employee")
        st, gross = e["state"], float(e["gross_wages"])
        if role in ("sole_prop", "partner"):
            band, _ = rules.get(st, "sole_prop_uses_officer_band", False)
            if band:
                apply_band(e, "SOLEPROP", f"covered {role.replace('_', ' ')}")
                continue
            basis, entry = rules.get(st, "sole_prop_annual_basis", None, on_date=eff_date)
            if basis is None:
                add(f"SOLEPROP-VERIFY-{st}", "review", st,
                    f"{e['employee']} is a covered {role.replace('_', ' ')} in {st}, where the payroll basis is not confirmed (or no vintage covers policy eff {eff_date}) — route to reviewer.",
                    f"register gross={money(gross)}",
                    f"Load the current {st} sole proprietor/partner basis, then re-run.",
                    0.0, f"{st} sole-prop basis (unresolved)", subject=e["employee"])
            else:
                period_basis = basis * weeks / 52.0
                delta = period_basis - gross
                if abs(delta) > 1.0:
                    add(f"SOLEPROP-{st}-BASIS", "medium", st,
                        f"{e['employee']} ({role.replace('_', ' ')}, covered by election): reported {money(gross)} but {st} rates covered {role.replace('_', ' ')}s at a flat basis of {money(period_basis)} — {'add' if delta > 0 else 'reduce by'} {money(abs(delta))}.",
                        f"register vs {st} flat basis ({(entry or {}).get('provenance', '?')}, vintage-resolved)",
                        f"Set auditable payroll to the flat basis {money(period_basis)}.",
                        delta * rates[e["class_code"]] / 100,
                        f"{st} sole-prop/partner flat basis ({(entry or {}).get('provenance', '?')})", subject=e["employee"])
            continue
        if e["is_officer"] != "Y":
            continue
        apply_band(e, "OFFICER", "officer")

    # ---- check 4: uninsured subcontractors, materials fraction state-resolved ----
    for row in gl:
        if row["coi_on_file"] == "N":
            amt, st = float(row["amount"]), row["work_state"]
            frac = 1.0
            cite = "full payments chargeable absent COI (sourced)"
            if row["materials_documented"] == "Y":
                frac, _ = rules.get(st, "uninsured_sub_materials_fraction", 1.0)
                cite = f"labor-portion fraction {frac} for documented materials (verify per {st})"
            charge = amt * frac
            add(f"SUB-NOCOI-{st}", "high", st,
                f"GL payment {money(amt)} to {row['payee']} ({row['memo']}) with NO certificate of insurance — {money(charge)} chargeable as payroll in class {gov_class}.",
                f"gl_cash_disbursements.csv {row['date']}",
                "Charge as payroll unless a valid COI covering the work period is produced.",
                charge * rates[gov_class] / 100, cite, subject=row["payee"])

    # ---- check 5: audit type determination + compliance clock ----
    est_annual = case["policy"]["estimated_annual_premium"]
    for st in sorted({e["state"] for e in in_scope}):
        annual_at, entry = rules.get(st, "physical_audit_annual_at")
        if annual_at and est_annual >= annual_at:
            add(f"AUDITTYPE-{st}", "info", st,
                f"Estimated annual premium {money(est_annual)} meets the {st} physical-audit threshold ({money(annual_at)}) — records examination by an accountable auditor REQUIRED (remote completion permitted where bureau allows).",
                f"policy est. annual premium vs threshold ({(entry or {}).get('provenance', '?')})",
                "Route to credentialed auditor for records examination and signature.",
                0.0, f"{st} physical-audit threshold ({(entry or {}).get('provenance', '?')})")

    exp = date.fromisoformat(case["policy"]["expiration_date"])
    today = date.fromisoformat(case["as_of_date"])
    for st in sorted({e["state"] for e in in_scope}):
        deadline, _ = rules.get(st, "audit_deadline_days")
        if deadline:
            elapsed = (today - exp).days
            if elapsed > deadline:
                add(f"DEADLINE-{st}", "high", st,
                    f"{elapsed} days since policy expiration exceeds the {st} {deadline}-day audit completion requirement — escalate immediately.",
                    f"expired {exp.isoformat()}, as-of {today.isoformat()}",
                    "Complete and deliver the audit now; document cause of delay for the carrier.",
                    0.0, f"{st} {deadline}-day rule (sourced)")

    # ---- check 6: ANC eligibility ----
    attempts = case["contact_attempts_documented"]
    if case.get("insured_noncompliant"):
        for st in sorted({e["state"] for e in in_scope}):
            applies, _ = rules.get(st, "anc_applies", True)
            need, _ = rules.get(st, "anc_required_contact_attempts", 2)
            mult, _ = rules.get(st, "anc_max_multiplier", 2.0)
            if not applies:
                add(f"ANC-NA-{st}", "info", st,
                    f"Insured noncompliant, but the audit noncompliance charge is NOT available in {st}.",
                    "state_rules: anc_applies=false", "Use estimated-audit and cancellation levers instead.",
                    0.0, f"{st}: ANC not adopted (sourced)")
            elif attempts < need:
                add(f"ANC-NOTELIGIBLE-{st}", "info", st,
                    f"Insured noncompliant but only {attempts} documented contact attempt(s) — ANC (up to {mult}x premium) requires {need} before charging.",
                    f"case contact_attempts_documented={attempts}",
                    "Make and document the required attempts before applying ANC.",
                    0.0, "NCCI Item B-1429 (sourced)")

    return findings

# ---------------- CLI: load, worksheet, self-test ----------------
def run(case_dir):
    rules = Rules()
    case = json.load(open(os.path.join(case_dir, "case.json")))
    register = list(csv.DictReader(open(os.path.join(case_dir, "payroll_register.csv"))))
    gl = list(csv.DictReader(open(os.path.join(case_dir, "gl_cash_disbursements.csv"))))
    findings = audit(case, register, gl, rules)

    print("=" * 78)
    print(f"AUDIT WORKSHEET v1 — {case['policy']['insured']}   period {case['period']}")
    print("=" * 78)
    net = 0.0
    for st in ["ALL"] + sorted({f["state"] for f in findings if f["state"] != "ALL"}):
        block = [f for f in findings if f["state"] == st]
        if not block:
            continue
        print(f"--- {st} " + "-" * (72 - len(st)))
        for fd in block:
            net += fd["premium_impact"]
            print(f"[{fd['severity'].upper():6}] {fd['id']}: {fd['finding']}")
            print(f"         evidence: {fd['evidence']}")
            print(f"         action:   {fd['action']}   rule: {fd['rule']}")
            if fd["premium_impact"]:
                print(f"         premium impact: {money(fd['premium_impact'])}")
    print("-" * 78)
    print(f"FINDINGS: {len(findings)}   NET PREMIUM IMPACT: {money(net)}")

    if rules.verify_hits:
        print("\nVERIFY QUEUE (placeholder rules applied this run — confirm before production):")
        for st, key, val, note in sorted(set(rules.verify_hits)):
            print(f"  - [{st}] {key} = {val}  ({note})")

    expected = set(case["expected_findings"])
    caught = {f["id"] for f in findings}
    missed, extra = expected - caught, caught - expected
    print(f"\nSELF-TEST: expected {len(expected)} findings")
    print(f"caught: {len(caught)}  missed: {sorted(missed) or 'NONE'}  unexpected: {sorted(extra) or 'NONE'}")
    return 0 if not missed and not extra else 1

if __name__ == "__main__":
    case_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "case_v1")
    sys.exit(run(case_dir))
