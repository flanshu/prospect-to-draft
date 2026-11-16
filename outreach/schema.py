"""Data model for an outreach run.

Everything is a plain dataclass with ``to_dict``/``from_dict`` so a run can be
serialised to JSON and stored in one row, and rebuilt after a Streamlit rerun.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Run statuses. These are deliberately distinct outcomes, not a single
# "failed" bucket -- the difference between them is the point of the workflow.
# ---------------------------------------------------------------------------
STATUS_RUNNING = "Running"
STATUS_NEEDS_CLARIFICATION = "Needs clarification"
STATUS_INSUFFICIENT_EVIDENCE = "Insufficient evidence"
STATUS_RESEARCH_INCOMPLETE = "Research incomplete"
STATUS_AWAITING_REVIEW = "Awaiting review"
STATUS_APPROVED = "Approved"
STATUS_REJECTED = "Rejected"

TERMINAL_STATUSES = {
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_APPROVED,
    STATUS_REJECTED,
}

# Stages, used for the live run view.
STAGES = ["Identity", "Research", "Signal selection", "Draft", "Human review"]

# Where a piece of text came from. Only ``source_text`` may be shown as a
# quotation; everything else is paraphrase.
PROV_SOURCE_TEXT = "source_text"        # verified against grounded source text
PROV_SEARCH_SUMMARY = "search_summary"  # search-result snippet / grounding segment
PROV_MODEL = "model_generated"          # model's own words


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Source:
    """A web source returned by Gemini's google_search grounding."""

    short_id: str
    title: str
    url: str
    domain: str = ""
    # Text segments from the grounded answer that this source supports.
    # Reused concept from shared/deep_search_agent.py (claim -> source mapping).
    supported_claims: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Source":
        return cls(
            short_id=d.get("short_id", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            domain=d.get("domain", ""),
            supported_claims=d.get("supported_claims", []) or [],
        )


@dataclass
class Finding:
    """One candidate signal: a fact plus the source that supports it."""

    claim: str                      # the specific fact, in our own words
    publisher: str                  # e.g. "Acme Corp careers site"
    url: str
    date: str = ""                  # "" when the source gives no date
    source_id: str = ""             # links back to a Source.short_id
    kind: str = ""                  # job posting / announcement / interview / ...
    quote: str = ""                 # only populated when verified
    provenance: str = PROV_MODEL
    quote_verified: bool = False
    verification_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Check:
    """One reviewable check on the selected signal."""

    name: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Check":
        return cls(name=d["name"], passed=bool(d["passed"]), reason=d.get("reason", ""))


@dataclass
class Identity:
    status: str = "unknown"          # confirmed | ambiguous | not_found
    confidence_reason: str = ""
    ambiguity: str = ""              # populated when status == "ambiguous"
    candidates: list[dict[str, Any]] = field(default_factory=list)
    resolved_note: str = ""          # user-supplied correction / profile link

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Identity":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Draft:
    subject: str = ""
    body: str = ""
    edited_subject: str = ""
    edited_body: str = ""
    decision: str = ""               # "" | approved | rejected
    decided_at: str = ""
    reviewer_note: str = ""

    def final_subject(self) -> str:
        return self.edited_subject or self.subject

    def final_body(self) -> str:
        return self.edited_body or self.body

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Draft":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Run:
    """The full state of one prospect run."""

    prospect_name: str
    company: str
    role: str = ""
    company_website: str = ""
    profile_url: str = ""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    status: str = STATUS_RUNNING
    mode: str = "live"               # "live" (real web research) or "fixture"
    fixture_id: str = ""

    stage: str = STAGES[0]
    stage_log: list[dict[str, str]] = field(default_factory=list)

    identity: Identity = field(default_factory=Identity)
    sources: list[Source] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    selected_index: int = -1
    selection_reason: str = ""
    checks: list[Check] = field(default_factory=list)

    draft: Draft = field(default_factory=Draft)

    stop_reason: str = ""            # why the run stopped short of a draft
    error: str = ""

    # ---------------------------------------------------------------- helpers
    def log(self, stage: str, message: str) -> None:
        self.stage = stage
        self.stage_log.append({"at": _now(), "stage": stage, "message": message})
        self.updated_at = _now()

    def selected_finding(self) -> Finding | None:
        if 0 <= self.selected_index < len(self.findings):
            return self.findings[self.selected_index]
        return None

    def checks_met(self) -> tuple[int, int]:
        return sum(1 for c in self.checks if c.passed), len(self.checks)

    def source_for(self, finding: Finding) -> Source | None:
        for s in self.sources:
            if s.short_id and s.short_id == finding.source_id:
                return s
        for s in self.sources:
            if s.url and s.url == finding.url:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "prospect_name": self.prospect_name,
            "company": self.company,
            "role": self.role,
            "company_website": self.company_website,
            "profile_url": self.profile_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "mode": self.mode,
            "fixture_id": self.fixture_id,
            "stage": self.stage,
            "stage_log": self.stage_log,
            "identity": self.identity.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "findings": [f.to_dict() for f in self.findings],
            "selected_index": self.selected_index,
            "selection_reason": self.selection_reason,
            "checks": [c.to_dict() for c in self.checks],
            "draft": self.draft.to_dict(),
            "stop_reason": self.stop_reason,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Run":
        run = cls(
            prospect_name=d.get("prospect_name", ""),
            company=d.get("company", ""),
            role=d.get("role", ""),
            company_website=d.get("company_website", ""),
            profile_url=d.get("profile_url", ""),
        )
        run.run_id = d.get("run_id", run.run_id)
        run.created_at = d.get("created_at", run.created_at)
        run.updated_at = d.get("updated_at", run.updated_at)
        run.status = d.get("status", STATUS_RUNNING)
        run.mode = d.get("mode", "live")
        run.fixture_id = d.get("fixture_id", "")
        run.stage = d.get("stage", STAGES[0])
        run.stage_log = d.get("stage_log", []) or []
        run.identity = Identity.from_dict(d.get("identity", {}) or {})
        run.sources = [Source.from_dict(s) for s in d.get("sources", []) or []]
        run.findings = [Finding.from_dict(f) for f in d.get("findings", []) or []]
        run.selected_index = d.get("selected_index", -1)
        run.selection_reason = d.get("selection_reason", "")
        run.checks = [Check.from_dict(c) for c in d.get("checks", []) or []]
        run.draft = Draft.from_dict(d.get("draft", {}) or {})
        run.stop_reason = d.get("stop_reason", "")
        run.error = d.get("error", "")
        return run
