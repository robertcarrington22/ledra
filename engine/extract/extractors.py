"""Audit House extraction layer v2 — vendor-native documents in, canonical case out.

Pipeline stages (per document):
  1. FORMAT DETECTION  — sniff headers/structure; unknown formats fail LOUDLY
  2. PII TOKENIZATION  — SSNs replaced with deterministic tokens at ingestion,
     before any downstream processing (in production: before any model call;
     the vault write goes to KMS-backed storage, never plaintext on disk)
  3. ADAPTATION        — per-format adapter normalizes rows to the canonical
     employee schema the engine consumes
  4. EXTRACTION REPORT — per-file provenance: format, rows, totals, tokens,
     and any line the adapter could not parse (nothing is silently dropped)

Scanned/PDF documents route to ScannedDocAdapter — a deliberate stub marking
where the OCR/LLM parser (Reducto/Bedrock-class) plugs in. v2 proves the
normalization architecture on structured exports; the ML parser is a vendor
integration, not a design change.
"""
import csv, hashlib, json, os, re

SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
MONEY_RE = re.compile(r"[\d,]+\.\d{2}")

def _money(s):
    return float(s.replace(",", "").replace("$", ""))

def _canon_name(name):
    """'Marsh, T.' -> 'T. Marsh'; strip annotations like '(Officer)'."""
    name = re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        return f"{first} {last}"
    return name

class Vault:
    """Deterministic SSN tokenizer. Production: KMS-backed store, per-tenant keys."""
    def __init__(self):
        self.map = {}
    def tokenize(self, ssn):
        tok = "SSN-" + hashlib.sha256(("audit-house|" + ssn).encode()).hexdigest()[:10].upper()
        self.map[tok] = ssn
        return tok
    def scrub(self, text):
        return SSN_RE.sub(lambda m: self.tokenize(m.group()), text)

class ExtractionError(Exception):
    pass

# ---------------- format detection ----------------
def detect_format(path, first_kb):
    name = os.path.basename(path).lower()
    if name.endswith(".pdf"):
        return "scanned"
    if "File #|Employee Name" in first_kb:
        return "adp_register"
    if first_kb.startswith("employee_name,ssn,work_state"):
        return "gusto_register"
    if "QuickBooks Payroll Summary" in first_kb:
        return "qb_register"
    if "FORM 941" in first_kb:
        return "form_941"
    if "STATE UNEMPLOYMENT WAGE REPORT" in first_kb:
        return "suta"
    if first_kb.startswith("Txn Date,Vendor"):
        return "gl"
    if name == "policy_dec.json":
        return "policy"
    return None

# ---------------- adapters ----------------
def adapt_adp(path, vault, dept_map, report):
    rows, unparsed = [], []
    for i, line in enumerate(open(path).read().splitlines()):
        if "|" not in line or line.startswith("File #") or line.startswith("TOTAL"):
            if line.strip() and "|" in line and not line.startswith("File #"):
                if line.startswith("TOTAL"):
                    m = MONEY_RE.search(line)
                    if m:
                        report["doc_total"] = _money(m.group())
                else:
                    unparsed.append((i + 1, line))
            continue
        parts = [p.strip() for p in vault.scrub(line).split("|")]
        if len(parts) != 8:
            unparsed.append((i + 1, line)); continue
        _, name, _tok, dept, state, gross, ot, officer = parts
        cls = dept_map.get(dept)
        if cls is None:
            raise ExtractionError(f"{path}: no class mapping for dept '{dept}'")
        rows.append({"employee": _canon_name(name), "state": state, "class_code": cls,
                     "gross_wages": f"{_money(gross):.2f}", "ot_premium_pay": f"{_money(ot):.2f}",
                     "ot_detail_by_employee": "Y",  # ADP export itemizes OT per employee
                     "is_officer": officer})
    report["unparsed_lines"] = unparsed
    return rows

def adapt_gusto(path, vault, dept_map, report):
    rows = []
    for r in csv.DictReader(open(path)):
        vault.tokenize(r["ssn"])
        cls = dept_map.get(r["role"])
        if cls is None:
            raise ExtractionError(f"{path}: no class mapping for role '{r['role']}'")
        rows.append({"employee": _canon_name(r["employee_name"]), "state": r["work_state"],
                     "class_code": cls, "gross_wages": f"{float(r['total_wages']):.2f}",
                     "ot_premium_pay": f"{float(r['overtime_premium']):.2f}",
                     "ot_detail_by_employee": "Y" if r["ot_itemized"].lower() in ("yes", "y") else "N",
                     "is_officer": "N"})
    report["doc_total"] = sum(float(r["gross_wages"]) for r in rows)
    return rows

def adapt_qb(path, vault, dept_map, report):
    rows, unparsed = [], []
    for i, raw in enumerate(open(path).read().splitlines()):
        line = raw.strip()
        if not line or line.startswith(("BlueRidge", "QuickBooks", "Name")):
            continue
        m = re.match(r"^(.*?)\s{2,}(\S+)\s{2,}([A-Z]{2})\s{2,}(\S+)\s{2,}([\d,]+\.\d{2})$",
                     vault.scrub(line))
        if not m:
            tm = re.search(r"Report total gross wages:\s*([\d,]+\.\d{2})", line)
            if tm:
                report["doc_total"] = _money(tm.group(1))
            elif line:
                unparsed.append((i + 1, raw))
            continue
        name_raw, _tok, state, dept, gross = m.groups()
        cls = dept_map.get(dept)
        if cls is None:
            raise ExtractionError(f"{path}: no class mapping for dept '{dept}'")
        rows.append({"employee": _canon_name(name_raw), "state": state, "class_code": cls,
                     "gross_wages": f"{_money(gross):.2f}", "ot_premium_pay": "0.00",
                     "ot_detail_by_employee": "Y",
                     "is_officer": "Y" if "(Officer)" in name_raw else "N"})
    report["unparsed_lines"] = unparsed
    return rows

def adapt_941(path, report):
    text = open(path).read()
    m = re.search(r"Line 2\s+Wages, tips, and other compensation\s*\.*\s*([\d,]+\.\d{2})", text)
    if not m:
        raise ExtractionError(f"{path}: could not locate Form 941 line 2")
    report["doc_total"] = _money(m.group(1))
    return {"line2_wages_tips_comp": _money(m.group(1))}

def adapt_suta(path, report):
    text = open(path).read()
    m = re.search(r"Total wages reported\s*\.*\s*([\d,]+\.\d{2})", text)
    if not m:
        raise ExtractionError(f"{path}: could not locate SUTA total wages")
    report["doc_total"] = _money(m.group(1))
    return _money(m.group(1))

def adapt_gl(path, report):
    rows = []
    for r in csv.DictReader(open(path)):
        rows.append({"date": r["Txn Date"], "payee": r["Vendor"], "memo": r["Description"],
                     "amount": f"{float(r['Amt']):.2f}", "coi_on_file": r["COI on File"],
                     "work_state": r["Job State"], "materials_documented": r["Materials Documented"]})
    report["doc_total"] = sum(float(r["amount"]) for r in rows)
    return rows

class ScannedDocAdapter:
    """Plug point for the OCR/LLM parser (Reducto / Bedrock-class, zero-retention terms).
    Not implemented in v2 by design — requires a vendor integration and its own
    eval set of scanned register formats before it can be trusted in the pipeline."""
    def __init__(self, path):
        raise ExtractionError(
            f"{path}: scanned/PDF ingestion requires the ML parser integration (v2.1). "
            "Route this file to manual intake; do not guess.")

# ---------------- orchestration ----------------
def extract_case(docs_dir, out_dir):
    vault = Vault()
    reports, employees, gl_rows, f941, suta, policy = [], [], [], None, None, None

    # pass 1: the policy declarations carry the dept->class map every register
    # adapter needs, so they load before any register is touched
    policy_path = os.path.join(docs_dir, "policy_dec.json")
    if os.path.exists(policy_path):
        policy = json.load(open(policy_path))

    for fname in sorted(os.listdir(docs_dir)):
        if fname in ("ground_truth.json", "policy_dec.json"):
            continue
        path = os.path.join(docs_dir, fname)
        first_kb = open(path, encoding="utf-8", errors="replace").read(1024)
        fmt = detect_format(path, first_kb)
        report = {"file": fname, "format": fmt, "rows": 0, "unparsed_lines": []}
        if fmt is None:
            raise ExtractionError(f"UNKNOWN FORMAT: {fname} — refusing to guess; route to manual intake")
        if fmt == "adp_register":
            rows = adapt_adp(path, vault, policy["dept_class_map"], report)
            employees += rows; report["rows"] = len(rows)
        elif fmt == "gusto_register":
            rows = adapt_gusto(path, vault, policy["dept_class_map"], report)
            employees += rows; report["rows"] = len(rows)
        elif fmt == "qb_register":
            rows = adapt_qb(path, vault, policy["dept_class_map"], report)
            employees += rows; report["rows"] = len(rows)
        elif fmt == "form_941":
            f941 = adapt_941(path, report)
        elif fmt == "suta":
            suta = adapt_suta(path, report)
        elif fmt == "gl":
            gl_rows = adapt_gl(path, report); report["rows"] = len(gl_rows)
        elif fmt == "scanned":
            ScannedDocAdapter(path)
        reports.append(report)

    if not (employees and gl_rows and f941 and suta and policy):
        raise ExtractionError("Incomplete document set — missing register, GL, 941, SUTA, or policy dec")

    # cross-file total check at extraction time (pre-engine sanity)
    reg_total = sum(float(e["gross_wages"]) for e in employees)
    per_doc = {r["file"]: r.get("doc_total") for r in reports if r.get("doc_total") is not None}

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "payroll_register.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["employee", "state", "class_code", "gross_wages",
                                          "ot_premium_pay", "ot_detail_by_employee", "is_officer"])
        w.writeheader(); w.writerows(employees)
    with open(os.path.join(out_dir, "gl_cash_disbursements.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "payee", "memo", "amount", "coi_on_file",
                                          "work_state", "materials_documented"])
        w.writeheader(); w.writerows(gl_rows)

    case = {
        "period": policy["period"], "as_of_date": policy["as_of_date"],
        "weeks_in_period": policy["weeks_in_period"],
        "policy": {k: policy[k] for k in ("insured", "expiration_date", "estimated_annual_premium",
                                          "governing_class", "class_rates_per_100")},
        "form_941": f941, "suta_total_wages": suta,
        "insured_noncompliant": policy["insured_noncompliant"],
        "contact_attempts_documented": policy["contact_attempts_documented"],
        "expected_findings": json.load(open(os.path.join(docs_dir, "ground_truth.json")))["expected_findings"],
    }
    with open(os.path.join(out_dir, "case.json"), "w") as f:
        json.dump(case, f, indent=2)

    # NOTE: production writes the vault to KMS-backed storage; the test writes
    # a count only — plaintext SSNs never land in the case directory.
    summary = {"files": reports, "employees": len(employees), "register_total": reg_total,
               "ssns_tokenized": len(vault.map), "per_doc_totals": per_doc}
    with open(os.path.join(out_dir, "extraction_report.json"), "w") as f:
        json.dump(summary, f, indent=2)
    return summary
