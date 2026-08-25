"""Generate mock payroll-provider fixtures (Finch-style sandbox shapes).

Simulates the employer-permissioned connection covering BlueRidge's main
payroll system: 6 of 8 employees (NY/PA/TX/NJ). The FL officer and WA employee
live on a separate local payroll and still arrive as documents — the hybrid
case the intake layer must handle.

Deliberate domain nuance: D. Ruiz's payroll system reports overtime as a single
unallocated bucket WITHOUT identifying the premium portion — so the NCCI
records-deficiency denial must still fire even though the data came via API.
An OT bucket is not an OT breakout.

Data-minimization by design: the consent scope excludes SSN/identity — these
fixtures contain no SSNs, matching how the intake layer requests access.
"""
import json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_fixtures")
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(OUT, "consent.json"), "w") as f:
    json.dump({
        "employer": "BlueRidge Mechanical Contractors Inc (fictional)",
        "authorized_by": "T. Marsh, President",
        "method": "e-sign via carrier audit notice payroll-connect link",
        "provider": "finch-sandbox",
        "connection_id": "conn_demo_blueridge_01",
        "scopes": ["company", "directory", "pay_statements"],
        "granted_at": "2026-08-10",
        "expires_at": "2026-11-10"
    }, f, indent=2)

with open(os.path.join(OUT, "company.json"), "w") as f:
    json.dump({"legal_name": "BlueRidge Mechanical Contractors Inc",
               "entity_type": "c_corporation", "primary_state": "NY"}, f, indent=2)

DIRECTORY = [
    {"individual_id": "ind_001", "first_name": "T.", "last_name": "Marsh",
     "title": "President", "department": "ADMIN", "location": {"state": "NY"}},
    {"individual_id": "ind_002", "first_name": "L.", "last_name": "Chen",
     "title": "Crew Lead", "department": "HVAC-INSTALL", "location": {"state": "NY"}},
    {"individual_id": "ind_003", "first_name": "R.", "last_name": "Novak",
     "title": "Installer", "department": "HVAC-INSTALL", "location": {"state": "PA"}},
    {"individual_id": "ind_004", "first_name": "D.", "last_name": "Ruiz",
     "title": "Installer", "department": "HVAC-INSTALL", "location": {"state": "TX"}},
    {"individual_id": "ind_005", "first_name": "A.", "last_name": "Boone",
     "title": "Outside Sales", "department": "SALES", "location": {"state": "TX"}},
    {"individual_id": "ind_006", "first_name": "S.", "last_name": "Adeyemi",
     "title": "Installer", "department": "HVAC-INSTALL", "location": {"state": "NJ"}},
]
with open(os.path.join(OUT, "directory.json"), "w") as f:
    json.dump({"individuals": DIRECTORY}, f, indent=2)

STATEMENTS = [
    {"individual_id": "ind_001", "period": "policy year ending 2026-02-01", "gross_pay": 182000.00,
     "earnings": [{"type": "base", "amount": 182000.00}]},
    {"individual_id": "ind_002", "period": "policy year ending 2026-02-01", "gross_pay": 68800.00,
     "earnings": [{"type": "base", "amount": 63400.00},
                  {"type": "overtime_premium", "amount": 5400.00, "premium_portion_identified": True}]},
    {"individual_id": "ind_003", "period": "policy year ending 2026-02-01", "gross_pay": 63200.00,
     "earnings": [{"type": "base", "amount": 58720.00},
                  {"type": "overtime_premium", "amount": 4480.00, "premium_portion_identified": True}]},
    {"individual_id": "ind_004", "period": "policy year ending 2026-02-01", "gross_pay": 56400.00,
     "earnings": [{"type": "base", "amount": 52840.00},
                  {"type": "overtime_unallocated", "amount": 3560.00, "premium_portion_identified": False}]},
    {"individual_id": "ind_005", "period": "policy year ending 2026-02-01", "gross_pay": 49200.00,
     "earnings": [{"type": "base", "amount": 49200.00}]},
    {"individual_id": "ind_006", "period": "policy year ending 2026-02-01", "gross_pay": 64000.00,
     "earnings": [{"type": "base", "amount": 60240.00},
                  {"type": "overtime_premium", "amount": 3760.00, "premium_portion_identified": True}]},
]
with open(os.path.join(OUT, "pay_statements.json"), "w") as f:
    json.dump({"statements": STATEMENTS}, f, indent=2)

total = sum(s["gross_pay"] for s in STATEMENTS)
print("api_fixtures written:", sorted(os.listdir(OUT)))
print(f"API-covered individuals: {len(DIRECTORY)}  API gross total: {total:,.2f}")
