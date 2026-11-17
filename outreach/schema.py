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

# ---------------------------------------------------------------------------
# Signal scoring rubric. 10 points total, fixed weights -- the model supplies
# the four integers and a reason for each; Python validates, totals and sorts.
# The total scores the strength of the outreach angle. It is NOT a prediction
# that the prospect will buy.
# ---------------------------------------------------------------------------
SCORE_COMPONENTS: list[tuple[str, str, int]] = [
    ("product_relevance", "Product relevance", 3),
    ("prospect_relevance", "Prospect relevance", 3),
    ("evidence_quality", "Evidence quality", 2),
    ("timeliness", "Timeliness", 2),
]
SCORE_MAX = sum(maximum for _, _, maximum in SCORE_COMPONENTS)

# How a scored finding may be used.
ELIGIBLE = "eligible"            # can be selected and can generate a draft
CONTEXT_ONLY = "context_only"    # real, but no product or prospect connection
EXCLUDED = "excluded"            # unsupported/contradicted, or a duplicate

# A finding needs at least this much product relevance to be drafted from.
# 2 means "a related workflow is described, but the exact task is unclear" --
# below that the source shows no more than the same broad business area, which
# is not a reason to write to someone about this product.
MIN_PRODUCT_RELEVANCE = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Product:
    """One thing the salesperson can sell, and the only claims allowed for it.

    A run stores a snapshot of the product it was researched for, so reopening
    it later shows the same offering even if the catalogue has moved on and
    even if a different product is selected on the new-run form.
    """

    product_id: str
    name: str
    target_users: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    # True only for runs saved before product selection existed.
    legacy: bool = False

    def capability_lines(self) -> str:
        return "\n".join(f"- {c}" for c in self.capabilities)

    def matches_capability(self, text: str) -> str:
        """The listed capability ``text`` names, or "" if it names none."""
        wanted = " ".join((text or "").split()).strip().lower().rstrip(".")
        if not wanted:
            return ""
        for cap in self.capabilities:
            if " ".join(cap.split()).strip().lower().rstrip(".") == wanted:
                return cap
        return ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Product":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in (d or {}).items() if k in known}
        payload["capabilities"] = list(payload.get("capabilities") or [])
        return cls(**payload)


def _default_product() -> Product:
    # Imported lazily: config owns the catalogue and imports this module.
    from .config import default_product

    return default_product()


def _legacy_product() -> Product:
    from .config import legacy_product

    return legacy_product()


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
    finding_id: str = ""            # stable id ("f-1"), assigned before scoring
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
class Score:
    """One finding's rubric scores, keyed by the finding's stable id.

    The four integers come from the model; the total, the ordering and the
    eligibility verdict are computed in Python so they can be checked.
    """

    finding_id: str
    product_relevance: int = 0
    prospect_relevance: int = 0
    evidence_quality: int = 0
    timeliness: int = 0
    # component key -> the model's short reason for that score
    reasons: dict[str, str] = field(default_factory=dict)
    # Which of the selected product's listed capabilities this finding connects
    # to. Required when product relevance is 2 or 3, and validated against the
    # run's own product so the model cannot name a capability we do not sell.
    capability: str = ""
    eligibility: str = ELIGIBLE
    eligibility_reason: str = ""

    @property
    def total(self) -> int:
        return (
            self.product_relevance
            + self.prospect_relevance
            + self.evidence_quality
            + self.timeliness
        )

    def components(self) -> list[tuple[str, str, int, int, str]]:
        """``(key, label, value, maximum, reason)`` in rubric order."""
        return [
            (key, label, int(getattr(self, key)), maximum, self.reasons.get(key, ""))
            for key, label, maximum in SCORE_COMPONENTS
        ]

    def sort_key(self) -> tuple[int, int, int, int, int]:
        """Total first, then the documented tie-breaks, highest wins."""
        return (
            self.total,
            self.product_relevance,
            self.prospect_relevance,
            self.evidence_quality,
            self.timeliness,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total"] = self.total          # stored so history needs no recompute
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Score":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in d.items() if k in known}
        payload["reasons"] = dict(payload.get("reasons") or {})
        return cls(**payload)


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
    finding_id: str = ""             # the signal this draft was written from
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

    # What this run is selling. Chosen once, at run creation, and never changed
    # afterwards: research, scoring, drafting and history all read it from here.
    product: Product = field(default_factory=_default_product)

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

    # Ranking. ``scores`` is one entry per finding; ``ranking`` is finding_ids
    # in display order (eligible by total desc, then context-only, then
    # excluded). ``recommended_id`` is the app's pick and never changes;
    # ``active_id`` is what the human is actually reviewing.
    scores: list[Score] = field(default_factory=list)
    ranking: list[str] = field(default_factory=list)
    recommended_id: str = ""
    active_id: str = ""

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
        """The finding the reviewer is currently looking at.

        ``active_id`` is authoritative once a run has been ranked;
        ``selected_index`` is kept in step with it so runs saved before ranking
        existed still open, and so history can read the signal cheaply.
        """
        if self.active_id:
            found = self.finding_by_id(self.active_id)
            if found is not None:
                return found
        if 0 <= self.selected_index < len(self.findings):
            return self.findings[self.selected_index]
        return None

    def finding_by_id(self, finding_id: str) -> Finding | None:
        if not finding_id:
            return None
        for f in self.findings:
            if f.finding_id == finding_id:
                return f
        return None

    def index_of(self, finding_id: str) -> int:
        for i, f in enumerate(self.findings):
            if f.finding_id == finding_id:
                return i
        return -1

    def score_for(self, finding_id: str) -> Score | None:
        for sc in self.scores:
            if sc.finding_id == finding_id:
                return sc
        return None

    def has_ranking(self) -> bool:
        """False for runs saved before ranked signals existed."""
        return bool(self.scores and self.ranking)

    def ranked_findings(self, eligibility: str | None = None) -> list[tuple[int, Finding, Score]]:
        """``(rank, finding, score)`` in ranking order, rank 1-based per group."""
        out: list[tuple[int, Finding, Score]] = []
        rank = 0
        for fid in self.ranking:
            finding = self.finding_by_id(fid)
            score = self.score_for(fid)
            if finding is None or score is None:
                continue
            if score.eligibility == ELIGIBLE:
                rank += 1
            if eligibility is not None and score.eligibility != eligibility:
                continue
            out.append((rank if score.eligibility == ELIGIBLE else 0, finding, score))
        return out

    def set_active_finding(self, finding_id: str) -> bool:
        """Point the run at one finding. Returns False for an unknown id."""
        idx = self.index_of(finding_id)
        if idx < 0:
            return False
        self.active_id = finding_id
        self.selected_index = idx
        return True

    def recommendation_was_overridden(self) -> bool:
        return bool(
            self.recommended_id and self.active_id and self.recommended_id != self.active_id
        )

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
            "product": self.product.to_dict(),
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
            "scores": [sc.to_dict() for sc in self.scores],
            "ranking": list(self.ranking),
            "recommended_id": self.recommended_id,
            "active_id": self.active_id,
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
        # A payload with no product predates product selection: it was an
        # invoice-matching run, and it is shown that way rather than rescored.
        stored_product = d.get("product")
        run.product = (
            Product.from_dict(stored_product) if stored_product else _legacy_product()
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
        run.scores = [Score.from_dict(sc) for sc in d.get("scores", []) or []]
        run.ranking = list(d.get("ranking", []) or [])
        run.recommended_id = d.get("recommended_id", "") or ""
        run.active_id = d.get("active_id", "") or ""
        run.selected_index = d.get("selected_index", -1)
        run.selection_reason = d.get("selection_reason", "")
        run.checks = [Check.from_dict(c) for c in d.get("checks", []) or []]
        run.draft = Draft.from_dict(d.get("draft", {}) or {})
        run.stop_reason = d.get("stop_reason", "")
        run.error = d.get("error", "")
        return run
