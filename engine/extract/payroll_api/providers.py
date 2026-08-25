"""Payroll provider abstraction — the layer a Finch/Argyle/Pinwheel client sits behind.

Contract:
  - Every call requires a VALIDATED consent record (no consent, no data —
    enforced here, not left to caller discipline).
  - Providers return provider-native payloads; normalization to the canonical
    schema happens in intake.py, never inside a provider client.
  - Swapping the mock for the live Finch client is a credentials change plus
    HTTP: the shapes and the consent gate stay identical.
"""
import json, os
from datetime import date

class ConsentError(Exception):
    pass

class ConsentRecord:
    REQUIRED_SCOPES = {"company", "directory", "pay_statements"}
    FORBIDDEN_SCOPES = {"ssn", "identity"}   # data minimization: never request these for audit

    def __init__(self, raw):
        self.raw = raw
        self.validated = False

    def validate(self, as_of):
        scopes = set(self.raw.get("scopes", []))
        if not self.REQUIRED_SCOPES.issubset(scopes):
            raise ConsentError(f"consent missing required scopes: {sorted(self.REQUIRED_SCOPES - scopes)}")
        banned = scopes & self.FORBIDDEN_SCOPES
        if banned:
            raise ConsentError(f"consent requests forbidden scopes {sorted(banned)} — audit intake never needs SSN/identity")
        granted = date.fromisoformat(self.raw["granted_at"])
        expires = date.fromisoformat(self.raw["expires_at"])
        if not (granted <= as_of <= expires):
            raise ConsentError(f"consent window {granted}..{expires} does not cover pull date {as_of}")
        for field in ("employer", "authorized_by", "method", "provider", "connection_id"):
            if not self.raw.get(field):
                raise ConsentError(f"consent record incomplete: missing {field}")
        self.validated = True
        return self

class FinchStyleProvider:
    """Mock of a Finch-style employer-permissioned payroll API, reading sandbox
    fixtures. Live client: same three calls against api.tryfinch.com with the
    connection's access token."""
    def __init__(self, fixtures_dir):
        self.dir = fixtures_dir

    def _load(self, name, consent):
        if not isinstance(consent, ConsentRecord) or not consent.validated:
            raise ConsentError(f"provider call '{name}' without validated consent — refused")
        return json.load(open(os.path.join(self.dir, name)))

    def company(self, consent):
        return self._load("company.json", consent)

    def directory(self, consent):
        return self._load("directory.json", consent)["individuals"]

    def pay_statements(self, consent):
        return self._load("pay_statements.json", consent)["statements"]

class ArgyleStyleProvider:
    """Worker-permissioned provider path (Argyle/Pinwheel/Atomic-class).
    Different consent model (each worker authorizes individually) — ships in
    v2.2 with its own consent flow; refuses rather than pretends."""
    def __init__(self, *_args, **_kw):
        raise NotImplementedError(
            "Worker-permissioned providers need per-worker consent handling (v2.2). "
            "Use the employer-permissioned path or document intake.")
