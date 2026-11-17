"""Offline checks. No network, no model calls, no API key needed.

Run with:  python -m pytest tests -q      (or)  python tests/test_offline.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from outreach import config, fixtures, pipeline, verify  # noqa: E402
from outreach.gemini_client import ResearchProviderError  # noqa: E402
from outreach.pipeline import _strip_unverified_quotes, stage_score  # noqa: E402
from outreach.store import _product_text, _signal_text  # noqa: E402
from outreach.schema import (  # noqa: E402
    CONTEXT_ONLY,
    ELIGIBLE,
    EXCLUDED,
    MIN_PRODUCT_RELEVANCE,
    PROV_MODEL,
    PROV_SEARCH_SUMMARY,
    PROV_SOURCE_TEXT,
    STATUS_APPROVED,
    STATUS_AWAITING_REVIEW,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_RESEARCH_INCOMPLETE,
    Finding,
    Run,
    Score,
)

INVOICE = "invoice_matching"
RECEIPTS = "receipt_tracking"
# Capabilities the scoring layer will accept for each product, copied from the
# catalogue so a renamed capability fails loudly here rather than silently.
INVOICE_CAP = "Comparing supplier invoices with purchase orders"
RECEIPTS_CAP = "Collecting missing employee expense receipts"


def _run_for(product_id: str, **kwargs) -> Run:
    kwargs.setdefault("prospect_name", "Maya Iyer")
    kwargs.setdefault("company", "Aurora Freight")
    return Run(product=config.product(product_id), **kwargs)

PAGE = (
    "<html><body><h1>Accounts Payable Analyst</h1>"
    "<p>You will own three-way matching of supplier invoices against purchase orders "
    "and goods receipt notes, and escalate mismatches to the finance manager for "
    "review.</p><script>var x=1;</script></body></html>"
)


def test_quote_verification_exact_match():
    text = verify._WS_RE.sub(" ", verify._TAG_RE.sub(" ", PAGE))
    quote = "own three-way matching of supplier invoices against purchase orders"
    assert verify.quote_matches(quote, text)
    assert not verify.quote_matches("has a huge invoice backlog costing millions", text)


def test_quote_verification_rejects_short_and_altered_quotes():
    text = "The team matches invoices to purchase orders every week."
    assert not verify.quote_matches("invoices", text)           # too short
    assert not verify.quote_matches("matches invoices to purchase requests", text)


def test_claim_overlap():
    text = "Northwind Logistics opened a second distribution hub in Coimbatore."
    assert verify.claim_overlap("Northwind opened a distribution hub in Coimbatore", text) >= 0.6
    assert verify.claim_overlap("Northwind is losing money on invoice errors", text) < 0.6


def test_unverifiable_finding_is_excluded(monkeypatch):
    monkeypatch.setattr(verify, "fetch_page_text", lambda url: (None, url, "HTTP 404"))
    f = Finding(
        claim="The company plans to replace its AP system next quarter.",
        publisher="unknown", url="https://example.com/gone",
        quote="We are replacing our AP system.",
    )
    verify.verify_finding(f, grounding_segments=["Unrelated text about hiring."])
    assert f.provenance == PROV_MODEL
    assert f.quote == "" and not f.quote_verified
    assert not verify.is_usable(f)
    assert "Excluded from the draft" in f.verification_note


def test_grounding_segment_rescues_claim_when_page_unreadable(monkeypatch):
    monkeypatch.setattr(verify, "fetch_page_text", lambda url: (None, url, "HTTP 403"))
    f = Finding(
        claim="Northwind Logistics opened a distribution hub in Coimbatore.",
        publisher="Freight Weekly", url="https://example.com/news",
    )
    verify.verify_finding(
        f, grounding_segments=["Northwind Logistics opened a second distribution hub in Coimbatore."]
    )
    assert f.provenance == PROV_SEARCH_SUMMARY
    assert verify.is_usable(f)
    assert not f.quote_verified


def test_page_text_verifies_quote(monkeypatch):
    page = verify._WS_RE.sub(" ", verify._TAG_RE.sub(" ", PAGE))
    monkeypatch.setattr(
        verify, "fetch_page_text",
        lambda url: (page, "https://northwind.example/careers/ap", "fetched"),
    )
    f = Finding(
        claim="The posting covers three-way matching of supplier invoices against purchase orders.",
        publisher="", url="https://redirect.example/x",
        quote="escalate mismatches to the finance manager for review",
    )
    verify.verify_finding(f, grounding_segments=[])
    assert f.provenance == PROV_SOURCE_TEXT and f.quote_verified
    assert f.url == "https://northwind.example/careers/ap"       # redirect resolved
    assert f.publisher == "northwind.example"                    # publisher inferred


def test_draft_guardrail_strips_unverified_quotes():
    body = 'He said "we have a massive invoice backlog" last week.'
    cleaned, removed = _strip_unverified_quotes(body, allowed_quote="")
    assert removed == 1 and '"' not in cleaned
    allowed = "we have a massive invoice backlog"
    kept, removed2 = _strip_unverified_quotes(body, allowed_quote=allowed)
    assert removed2 == 0 and '"we have a massive invoice backlog"' in kept


def test_a_high_total_never_overrides_a_failed_evidence_gate(monkeypatch):
    """8 of 10 must never produce a draft when the evidence is unsupported."""
    run = _run_for(INVOICE, prospect_name="A B", company="C")
    run.findings = [
        Finding(claim="They are replacing their AP system", publisher="p", url="u",
                finding_id="f-1", provenance=PROV_SEARCH_SUMMARY),
    ]
    monkeypatch.setattr(pipeline, "json_call", lambda *a, **k: {"scores": [
        _score_row("f-1", 3, 3, 0, 2, evidence_quality_reason="no source states this"),
    ]})
    stage_score(run)
    assert run.status == STATUS_INSUFFICIENT_EVIDENCE
    assert run.score_for("f-1").total == 8
    assert run.score_for("f-1").eligibility == EXCLUDED
    assert not run.draft.subject and run.active_id == ""


def test_fixtures_have_expected_outcomes():
    expected = {
        "E": STATUS_AWAITING_REVIEW,
        "A": STATUS_AWAITING_REVIEW,
        "B": STATUS_NEEDS_CLARIFICATION,
        "C": STATUS_INSUFFICIENT_EVIDENCE,
        "D": STATUS_RESEARCH_INCOMPLETE,
    }
    for fid, status in expected.items():
        run = fixtures.build(fid)
        assert run.status == status, (fid, run.status)
        assert run.mode == "fixture"
    a = fixtures.build("A")
    assert a.draft.subject and a.selected_finding() is not None
    assert a.checks_met() == (4, 4)     # every rubric component scored above zero
    c = fixtures.build("C")
    assert c.stop_reason and not c.checks
    assert not c.draft.subject          # weak signal must not produce a draft


def test_fixture_a_draft_only_quotes_verified_text():
    """Everything in quotation marks in the happy-path draft is verified text."""
    a = fixtures.build("A")
    f = a.selected_finding()
    assert f and f.quote_verified
    _, removed = _strip_unverified_quotes(a.draft.body, allowed_quote=f.quote)
    assert removed == 0


def test_round_trip_serialisation():
    run = fixtures.build("A")
    clone = Run.from_dict(run.to_dict())
    assert clone.to_dict() == run.to_dict()
    assert clone.selected_finding().claim == run.selected_finding().claim


def test_store_sqlite_upsert_and_reload(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "t.db"
        monkeypatch.setattr(config, "sqlite_path", lambda: db)
        monkeypatch.setattr(config, "database_url", lambda: None)
        from outreach.store import Store

        store = Store()
        run = fixtures.build("A")
        store.save(run)
        store.save(run)                                  # no duplicate
        assert len(store.list_runs()) == 1

        run.draft.edited_subject = "Edited subject"
        run.status = STATUS_APPROVED
        store.save(run)
        rows = store.list_runs()
        assert len(rows) == 1 and rows[0]["status"] == STATUS_APPROVED

        loaded = store.get(run.run_id)
        assert loaded is not None
        assert loaded.draft.final_subject() == "Edited subject"
        assert loaded.selected_finding().quote_verified

        store.save(fixtures.build("C"))
        assert len(store.list_runs()) == 2


def test_fixture_replay_reaches_final_state():
    run = fixtures.replay("A", step_delay=0.0)
    assert run.status == STATUS_AWAITING_REVIEW and run.stage_log


def test_product_catalogue_shape_and_default():
    """Three products, each with capabilities, and receipts is the default."""
    assert list(config.PRODUCTS) == [RECEIPTS, "vendor_onboarding", INVOICE]
    assert config.DEFAULT_PRODUCT_ID == RECEIPTS
    assert config.default_product().name == "Expense receipt tracking"
    # The dropdown shows the default first.
    assert config.product_choices()[0] == (RECEIPTS, "Expense receipt tracking")
    for pid, product in config.PRODUCTS.items():
        assert product.product_id == pid
        assert product.name and product.description and product.target_users
        assert product.capabilities, pid
        assert not product.legacy
    # An unknown id falls back to the default rather than raising.
    assert config.product("nope").product_id == RECEIPTS
    # Capability matching is exact, tolerating case and a trailing stop.
    inv = config.product(INVOICE)
    assert inv.matches_capability(INVOICE_CAP.lower() + ".") == INVOICE_CAP
    assert inv.matches_capability(RECEIPTS_CAP) == ""


def test_a_new_run_carries_the_default_product():
    run = Run(prospect_name="A", company="B")
    assert run.product.product_id == RECEIPTS and not run.product.legacy
    assert Run.from_dict(run.to_dict()).product.product_id == RECEIPTS


def test_a_payload_without_a_product_is_shown_as_a_legacy_invoice_run():
    """Runs saved before the dropdown keep their original context."""
    payload = fixtures.build("A").to_dict()
    payload.pop("product")
    run = Run.from_dict(payload)
    assert run.product.product_id == INVOICE
    assert run.product.legacy is True
    # The flag survives a re-save, so approving an old run does not relabel it.
    assert Run.from_dict(run.to_dict()).product.legacy is True
    assert "before product choice" in _product_text(payload)


# ---------------------------------------------------------------------------
# Full workflow with the model and search layers mocked. This exercises the
# real pipeline code (stage order, URL allow-listing, verification gate, status
# transitions) without any network call or API key.
# ---------------------------------------------------------------------------
class _FakeGrounded:
    def __init__(self, text, sources):
        self.text, self.sources, self.queries = text, sources, ["q"]


def _fake_sources():
    return {
        "src-1": {
            "short_id": "src-1",
            "title": "Careers — Aurora Freight",
            "url": "https://aurora-freight.example/careers/ap-analyst",
            "domain": "aurora-freight.example",
            "supported_claims": [{
                "text_segment": "Aurora Freight is hiring an AP Analyst to match supplier "
                                "invoices against purchase orders and escalate mismatches.",
                "confidence": 0.9,
            }],
        }
    }


def _wire(monkeypatch, *, json_answers):
    import outreach.pipeline as pipeline

    monkeypatch.setattr(
        pipeline, "grounded_search",
        lambda *a, **k: _FakeGrounded("summary text", _fake_sources()),
    )
    answers = list(json_answers)
    monkeypatch.setattr(pipeline, "json_call", lambda *a, **k: answers.pop(0))
    # No page fetching in tests: fall back to grounding-segment corroboration.
    monkeypatch.setattr(
        pipeline.verify, "fetch_page_text",
        lambda url: (None, url, "network disabled in tests"),
    )
    return pipeline


def test_full_workflow_happy_path(monkeypatch):
    from outreach.pipeline import execute

    pipeline = _wire(monkeypatch, json_answers=[
        {"status": "confirmed", "confidence_reason": "Company page lists her.",
         "ambiguity": "", "candidates": []},
        {"findings": [{
            "claim": "Aurora Freight is hiring an AP Analyst to match supplier invoices "
                     "against purchase orders and escalate mismatches.",
            "publisher": "Aurora Freight careers",
            "url": "https://aurora-freight.example/careers/ap-analyst",
            "date": "2026-10-01", "kind": "job posting", "quote": "",
        }]},
        {"scores": [_score_row("f-1", 3, 2, 2, 2,
                               product_relevance_reason="names invoice-to-PO matching")]},
        {"subject": "Your AP analyst posting", "body": "Hi — how does your team handle "
                                                       "mismatches today?"},
    ])
    stages = []
    run = _run_for(INVOICE)
    execute(run, on_stage=lambda r: stages.append(r.stage))

    assert run.status == STATUS_AWAITING_REVIEW
    assert run.draft.subject and run.draft.body
    assert run.selected_finding().url.endswith("/ap-analyst")
    assert run.checks_met() == (4, 4)
    assert run.recommended_id == "f-1" and run.active_id == "f-1"
    assert run.score_for("f-1").total == 9 and run.draft.finding_id == "f-1"
    assert "Identity" in stages and "Human review" in stages


def test_full_workflow_drops_findings_with_uncited_urls(monkeypatch):
    from outreach.pipeline import execute

    _wire(monkeypatch, json_answers=[
        {"status": "confirmed", "confidence_reason": "ok", "ambiguity": "", "candidates": []},
        {"findings": [{
            "claim": "They are replacing their ERP next quarter.",
            "publisher": "Invented Blog", "url": "https://not-a-cited-source.example/post",
            "date": "2026-01-01", "kind": "news", "quote": "We are replacing our ERP.",
        }]},
    ])
    run = _run_for(INVOICE)
    execute(run)
    assert run.status == STATUS_INSUFFICIENT_EVIDENCE
    assert run.findings == []
    assert any("not in the cited sources" in e["message"] for e in run.stage_log)


def test_full_workflow_pauses_on_ambiguous_identity(monkeypatch):
    from outreach.pipeline import execute

    _wire(monkeypatch, json_answers=[
        {"status": "ambiguous", "confidence_reason": "Two matches.",
         "ambiguity": "Two people share this name.",
         "candidates": [{"description": "A", "why": "b", "url": ""}]},
    ])
    run = _run_for(INVOICE, prospect_name="Michael Chen", company="Veridian Health")
    execute(run)
    assert run.status == STATUS_NEEDS_CLARIFICATION
    assert not run.findings            # research never ran, so nothing was spent
    assert not run.draft.subject


def test_provider_failure_is_not_insufficient_evidence(monkeypatch):
    import outreach.pipeline as pipeline
    from outreach.gemini_client import ResearchProviderError
    from outreach.pipeline import execute

    def boom(*a, **k):
        raise ResearchProviderError("503 backend unavailable")

    monkeypatch.setattr(pipeline, "grounded_search", boom)
    run = _run_for(INVOICE, prospect_name="Alina Moreau", company="Castellan Foods")
    execute(run)
    assert run.status == STATUS_RESEARCH_INCOMPLETE
    assert "503" in run.error
    assert run.status != STATUS_INSUFFICIENT_EVIDENCE


def test_missing_credentials_reports_research_incomplete(monkeypatch):
    from outreach.pipeline import execute

    monkeypatch.setattr(config, "google_api_key", lambda: None)
    run = _run_for(INVOICE)
    execute(run)
    assert run.status == STATUS_RESEARCH_INCOMPLETE
    assert "GOOGLE_API_KEY" in run.error


# ---------------------------------------------------------------------------
# Ranked signals: scoring validation, ordering, eligibility gates, and the
# human switching signal without repeating any research.
# ---------------------------------------------------------------------------
def _run_with_findings(claims: list[str], product_id: str = INVOICE) -> Run:
    run = Run(
        prospect_name="Priya Raghavan",
        company="Northwind Logistics",
        product=config.product(product_id),
    )
    run.findings = [
        Finding(
            claim=claim,
            publisher="p",
            url=f"https://src.example/{i}",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="corroborated",
        )
        for i, claim in enumerate(claims)
    ]
    pipeline._assign_finding_ids(run)
    return run


DISTINCT_CLAIMS = [
    "An open accounts payable analyst posting lists three-way matching of supplier "
    "invoices against purchase orders",
    "The prospect said her finance team wants to cut manual spreadsheet reconciliation "
    "this year",
    "The company raised a Series B funding round led by Calder Partners",
]


def _score_row(fid, product, prospect, evidence, timeliness, *, capability=None, **reasons):
    """One scoring row, valid by default.

    A product relevance of 2 or 3 has to name a capability and give a reason,
    so the helper supplies both unless a test is deliberately leaving them out.
    """
    row = {
        "finding_id": fid,
        "product_relevance": product,
        "prospect_relevance": prospect,
        "evidence_quality": evidence,
        "timeliness": timeliness,
    }
    claims_connection = (
        isinstance(product, (int, float))
        and not isinstance(product, bool)
        and product >= MIN_PRODUCT_RELEVANCE
    )
    if claims_connection:
        row["capability"] = INVOICE_CAP if capability is None else capability
        row.setdefault("product_relevance_reason", "names the task the source describes")
    elif capability is not None:
        row["capability"] = capability
    row.update(reasons)
    return row


def _with_scores(monkeypatch, rows):
    monkeypatch.setattr(pipeline, "json_call", lambda *a, **k: {"scores": rows})


def test_ranking_orders_by_total_and_sets_recommendation(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS)
    _with_scores(monkeypatch, [
        _score_row("f-1", 3, 2, 2, 2, product_relevance_reason="names invoice-to-PO matching"),
        _score_row("f-2", 2, 3, 2, 1),
        _score_row("f-3", 0, 1, 2, 2),
    ])
    pipeline.stage_score(run)

    assert run.ranking == ["f-1", "f-2", "f-3"]            # 9, 8, then background only
    assert run.recommended_id == "f-1" and run.active_id == "f-1"
    assert run.score_for("f-1").total == 9
    assert [s.eligibility for s in run.scores] == [ELIGIBLE, ELIGIBLE, CONTEXT_ONLY]
    assert "9 of 10" in run.selection_reason and "8" in run.selection_reason
    assert not run.recommendation_was_overridden()
    # The capability the model named is kept on the score and reaches the UI.
    assert run.score_for("f-1").capability == INVOICE_CAP
    assert run.score_for("f-3").capability == ""


def test_context_only_sits_below_eligible_even_with_a_higher_total(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS[:2])
    _with_scores(monkeypatch, [
        _score_row("f-1", 0, 3, 2, 2),        # 7, but no product connection
        _score_row("f-2", 2, 1, 1, 1),        # 5, eligible
    ])
    pipeline.stage_score(run)

    assert run.ranking == ["f-2", "f-1"]
    assert run.score_for("f-1").total > run.score_for("f-2").total
    assert run.score_for("f-1").eligibility == CONTEXT_ONLY
    assert run.recommended_id == "f-2"


def test_tie_breaks_follow_the_documented_order(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS)
    # All three total 7. f-2 wins on product relevance; f-3 beats f-1 on
    # prospect relevance; f-1 is last despite coming first in research order.
    _with_scores(monkeypatch, [
        _score_row("f-1", 2, 2, 2, 1),
        _score_row("f-2", 3, 1, 2, 1),
        _score_row("f-3", 2, 3, 1, 1),
    ])
    pipeline.stage_score(run)
    assert [s.total for s in run.scores] == [7, 7, 7]
    assert run.ranking == ["f-2", "f-3", "f-1"]


def test_full_tie_preserves_original_research_order(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS)
    rows = [_score_row(f"f-{i}", 2, 2, 1, 1) for i in (1, 2, 3)]
    _with_scores(monkeypatch, list(reversed(rows)))   # model order must not matter
    pipeline.stage_score(run)
    assert run.ranking == ["f-1", "f-2", "f-3"]


def test_unverified_finding_is_excluded_from_ranking_whatever_the_model_says(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS[:2])
    run.findings[1].provenance = PROV_MODEL          # failed verification
    run.findings[1].verification_note = "Not verified: the page does not state this."
    _with_scores(monkeypatch, [
        _score_row("f-1", 2, 2, 1, 1),
    ])
    pipeline.stage_score(run)

    excluded = run.score_for("f-2")
    assert excluded.eligibility == EXCLUDED and excluded.total == 0
    assert "No source supports this claim" in excluded.eligibility_reason
    assert run.ranking[-1] == "f-2"
    assert run.recommended_id == "f-1"


def test_zero_evidence_quality_is_excluded_not_merely_ranked_low(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS[:2])
    _with_scores(monkeypatch, [
        _score_row("f-1", 3, 3, 0, 2),      # 8 points, but unsupported
        _score_row("f-2", 2, 1, 1, 1),      # 5 points, supported
    ])
    pipeline.stage_score(run)
    assert run.score_for("f-1").eligibility == EXCLUDED
    assert run.recommended_id == "f-2"
    assert run.status != STATUS_INSUFFICIENT_EVIDENCE      # a weaker signal still qualifies


def test_no_eligible_signal_is_insufficient_evidence_not_a_draft(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS)
    _with_scores(monkeypatch, [
        _score_row("f-1", 0, 3, 2, 2),
        _score_row("f-2", 0, 1, 1, 1),
        _score_row("f-3", 0, 1, 2, 2),
    ])
    pipeline.stage_score(run)
    assert run.status == STATUS_INSUFFICIENT_EVIDENCE
    assert run.active_id == "" and run.selected_index == -1
    assert "context only" in run.stop_reason
    assert not run.draft.subject


def test_duplicate_reports_of_one_event_do_not_take_two_ranks(monkeypatch):
    claim = "The company raised a 24 million dollar Series B led by Calder Partners"
    run = _run_with_findings([
        "An accounts payable posting lists matching of supplier invoices to purchase orders",
        claim,
        claim + " ",            # the same event from a second outlet
    ])
    _with_scores(monkeypatch, [
        _score_row("f-1", 3, 2, 2, 2),
        _score_row("f-2", 2, 2, 2, 2),
        _score_row("f-3", 2, 2, 2, 1),
    ])
    pipeline.stage_score(run)
    eligible = [s.finding_id for s in run.scores if s.eligibility == ELIGIBLE]
    assert eligible == ["f-1", "f-2"]
    assert run.score_for("f-3").eligibility == EXCLUDED
    assert "same event" in run.score_for("f-3").eligibility_reason


# ---- malformed scoring output ------------------------------------------------
def test_scoring_retries_once_then_succeeds(monkeypatch):
    run = _run_with_findings(DISTINCT_CLAIMS[:1])
    answers = [
        {"scores": [{"finding_id": "f-1", "product_relevance": 2}]},        # incomplete
        {"scores": [_score_row("f-1", 2, 2, 2, 2)]},                        # valid
    ]
    monkeypatch.setattr(pipeline, "json_call", lambda *a, **k: answers.pop(0))
    pipeline.stage_score(run)
    assert run.recommended_id == "f-1"
    assert any("Retrying once" in e["message"] for e in run.stage_log)


def test_scoring_invalid_twice_is_research_incomplete_with_a_retry(monkeypatch):
    from outreach.pipeline import execute

    _wire(monkeypatch, json_answers=[
        {"status": "confirmed", "confidence_reason": "ok", "ambiguity": "", "candidates": []},
        {"findings": [{
            "claim": "Aurora Freight is hiring an AP Analyst to match supplier invoices "
                     "against purchase orders and escalate mismatches.",
            "publisher": "Aurora Freight careers",
            "url": "https://aurora-freight.example/careers/ap-analyst",
            "date": "2026-10-01", "kind": "job posting", "quote": "",
        }]},
        {"scores": [_score_row("f-1", 9, 9, 9, 9)]},     # out of range
        {"scores": [_score_row("f-2", 1, 1, 1, 1)]},     # unknown id
    ])
    run = _run_for(INVOICE)
    execute(run)
    assert run.status == STATUS_RESEARCH_INCOMPLETE
    assert run.status != STATUS_INSUFFICIENT_EVIDENCE
    assert "scoring" in run.error.lower()
    assert not run.draft.subject


def test_score_validation_rejects_bad_shapes():
    bad = [
        ({"scores": []}, "no scores list"),
        ({"scores": [{"product_relevance": 1}]}, "no finding_id"),
        ({"scores": [_score_row("f-1", 1, 1, 1, 1), _score_row("f-1", 2, 2, 2, 2)]}, "duplicate"),
        ({"scores": [_score_row("f-1", 1, 1, 1, 3)]}, "timeliness out of range"),
        ({"scores": [_score_row("f-1", "two", 1, 1, 1)]}, "non-integer"),
        ({"scores": [{"finding_id": "f-1", "product_relevance": 1, "prospect_relevance": 1}]}, "missing"),
        ("not json", "not an object"),
    ]
    product = config.product(INVOICE)
    for payload, why in bad:
        with pytest.raises(pipeline.ScoringFormatError):
            pipeline._parse_scores(payload, ["f-1"], product)
    # A float that is exactly an integer is accepted; 1.5 is not.
    ok = pipeline._parse_scores(
        {"scores": [_score_row("f-1", 2.0, 1, 1, 1)]}, ["f-1"], product
    )
    assert ok[0].product_relevance == 2
    with pytest.raises(pipeline.ScoringFormatError):
        pipeline._parse_scores(
            {"scores": [_score_row("f-1", 1.5, 1, 1, 1)]}, ["f-1"], product
        )


def test_missing_score_for_a_candidate_is_rejected():
    with pytest.raises(pipeline.ScoringFormatError):
        pipeline._parse_scores(
            {"scores": [_score_row("f-1", 1, 1, 1, 1)]},
            ["f-1", "f-2"],
            config.product(INVOICE),
        )


def test_a_claimed_product_connection_must_name_a_real_capability():
    """Product relevance of 2 or 3 has to say which capability, and why."""
    product = config.product(INVOICE)

    def parse(row):
        return pipeline._parse_scores({"scores": [row]}, ["f-1"], product)

    # No capability named at all.
    row = _score_row("f-1", 3, 2, 2, 2)
    row.pop("capability")
    with pytest.raises(pipeline.ScoringFormatError, match="no capability named"):
        parse(row)
    # A capability this product does not have.
    with pytest.raises(pipeline.ScoringFormatError, match="not a capability"):
        parse(_score_row("f-1", 3, 2, 2, 2, capability=RECEIPTS_CAP))
    # Named, but with no reason given.
    with pytest.raises(pipeline.ScoringFormatError, match="no reason given"):
        parse(_score_row("f-1", 2, 2, 2, 2, product_relevance_reason=""))
    # Valid: the capability is kept in the catalogue's own wording.
    ok = parse(_score_row("f-1", 3, 2, 2, 2, capability=INVOICE_CAP.lower()))
    assert ok[0].capability == INVOICE_CAP
    # Below the threshold nothing is claimed, so nothing has to be named.
    low = parse(_score_row("f-1", 1, 2, 2, 2))
    assert low[0].capability == "" 


# ---- switching signal --------------------------------------------------------
def test_switching_signal_redrafts_without_repeating_research(monkeypatch):
    run = fixtures.build("A")
    searches: list[str] = []
    monkeypatch.setattr(pipeline, "grounded_search",
                        lambda *a, **k: searches.append("search"))
    drafted: list[str] = []

    def fake_draft(*a, **k):
        drafted.append("draft")
        return {"subject": "The manual steps you mentioned",
                "body": "Hi Priya - which part still runs on spreadsheets?"}

    monkeypatch.setattr(pipeline, "json_call", fake_draft)
    before_sources = [s.url for s in run.sources]
    before_scores = [(s.finding_id, s.total) for s in run.scores]

    pipeline.redraft(run, "f-2")

    assert searches == []                       # no web research
    assert len(drafted) == 1                    # exactly one drafting call
    assert run.active_id == "f-2" and run.draft.finding_id == "f-2"
    assert run.recommended_id == "f-1"          # the app's pick is still visible
    assert run.recommendation_was_overridden()
    assert run.status == STATUS_AWAITING_REVIEW and run.draft.decision == ""
    assert [s.url for s in run.sources] == before_sources
    assert [(s.finding_id, s.total) for s in run.scores] == before_scores
    assert run.checks[0].name == "Product relevance" and "2 of 3" in run.checks[0].reason


def test_switching_to_a_context_only_signal_is_refused():
    run = fixtures.build("A")
    with pytest.raises(pipeline.SignalNotEligible):
        pipeline.redraft(run, "f-3")            # the funding announcement
    assert run.active_id == "f-1"               # unchanged
    with pytest.raises(pipeline.SignalNotEligible):
        pipeline.redraft(run, "f-99")           # unknown id


def test_failed_regeneration_keeps_the_previous_draft_and_signal(monkeypatch):
    run = fixtures.build("A")
    before = (run.draft.subject, run.draft.body, run.active_id, run.status)

    def boom(*a, **k):
        raise ResearchProviderError("503 the model backend is unavailable")

    monkeypatch.setattr(pipeline, "json_call", boom)
    with pytest.raises(ResearchProviderError):
        pipeline.redraft(run, "f-2")

    assert (run.draft.subject, run.draft.body, run.active_id, run.status) == before
    assert run.draft.finding_id == "f-1"        # evidence and email still agree
    assert "503" in run.error
    assert any("previous draft" in e["message"] for e in run.stage_log)


def test_fixture_switch_needs_no_model_call():
    run = fixtures.build("A")
    canned = fixtures.alternate_draft("A", "f-2")
    assert canned is not None
    pipeline.redraft(run, "f-2", draft_fn=lambda r, f: canned)
    assert run.active_id == "f-2" and run.draft.finding_id == "f-2"
    assert "spreadsheets" in run.draft.body
    assert fixtures.alternate_draft("A", "f-3") is None     # context only


# ---- the demo flow, end to end, offline -------------------------------------
def test_demo_flow_switch_approve_reopen(monkeypatch):
    """Fixture A -> switch to #2 -> approve -> reload from the store."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "demo.db"
        monkeypatch.setattr(config, "sqlite_path", lambda: db)
        monkeypatch.setattr(config, "database_url", lambda: None)
        from outreach.store import Store

        store = Store()
        run = fixtures.build("A")
        store.save(run)

        canned = fixtures.alternate_draft("A", "f-2")
        pipeline.redraft(run, "f-2", draft_fn=lambda r, f: canned)
        store.save(run)

        run.draft.edited_body = run.draft.body + "\n\nPS - congratulations on the Series B."
        run.draft.decision = "approved"
        run.draft.decided_at = "2026-11-17T10:00:00+00:00"
        run.status = STATUS_APPROVED
        store.save(run)

        assert len(store.list_runs()) == 1                 # still one run
        row = store.list_runs()[0]
        assert "manual" in row["signal"] and "8 of 10" in row["signal"]
        assert "reviewer's choice" in row["signal"]

        loaded = store.get(run.run_id)
        assert loaded.status == STATUS_APPROVED
        assert loaded.active_id == "f-2" and loaded.draft.finding_id == "f-2"
        assert loaded.recommended_id == "f-1"
        assert loaded.selected_finding().claim.startswith("In a trade-press interview")
        assert "Series B" in loaded.draft.final_body()
        assert loaded.score_for("f-2").total == 8
        assert loaded.has_ranking()


def test_legacy_run_without_ranking_still_opens(monkeypatch):
    """A run saved before ranking existed keeps its evidence and draft."""
    legacy = fixtures.build("A").to_dict()
    for key in ("scores", "ranking", "recommended_id", "active_id"):
        legacy.pop(key)
    for f in legacy["findings"]:
        f.pop("finding_id")
    legacy["draft"].pop("finding_id")
    legacy["selected_index"] = 0

    run = Run.from_dict(legacy)
    assert not run.has_ranking()
    assert run.scores == [] and run.ranking == []
    assert run.selected_finding() is not None            # falls back to the index
    assert run.selected_finding().claim.startswith("Northwind Logistics has an open")
    assert run.draft.subject and run.checks                # original draft intact
    assert "no score recorded" in _signal_text(legacy)     # labelled, not invented

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "legacy.db"
        monkeypatch.setattr(config, "sqlite_path", lambda: db)
        monkeypatch.setattr(config, "database_url", lambda: None)
        from outreach.store import Store

        store = Store()
        store.save(run)
        again = store.get(run.run_id)
        assert not again.has_ranking()
        assert again.selected_finding().claim == run.selected_finding().claim


def test_fixture_a_is_demo_ready():
    """The invoice-matching sample must show the ranking the demo talks about."""
    a = fixtures.build("A")
    totals = {s.finding_id: s.total for s in a.scores}
    assert totals == {"f-1": 9, "f-2": 8, "f-3": 5}
    assert sum(1 for s in a.scores if s.eligibility == ELIGIBLE) == 2
    assert sum(1 for s in a.scores if s.eligibility == CONTEXT_ONLY) == 1
    assert a.recommended_id == "f-1" and a.draft.finding_id == "f-1"
    # Every score carries a reason a reviewer can disagree with.
    for s in a.scores:
        for key, _, _, _, reason in s.components():
            assert reason, (s.finding_id, key)


def test_fixture_c_refuses_to_draft_despite_a_seven_out_of_ten():
    c = fixtures.build("C")
    assert c.status == STATUS_INSUFFICIENT_EVIDENCE
    assert max(s.total for s in c.scores) == 7
    assert all(s.eligibility == CONTEXT_ONLY for s in c.scores)
    assert not c.draft.subject and c.active_id == ""
    assert "cannot buy a product connection" in c.stop_reason



# ---------------------------------------------------------------------------
# Multi-product support. Two layers, tested separately: Python's thresholds and
# ordering are exercised with mocked scores, and the prompts are checked for
# actually carrying the chosen product.
# ---------------------------------------------------------------------------
ACCEPTANCE_CLAIM = (
    "The finance team follows up with employees about missing expense receipts."
)


def _one_finding_run(product_id: str, claim: str = ACCEPTANCE_CLAIM) -> Run:
    run = Run(
        prospect_name="Hannah Weiss",
        company="Meridian Outfitters",
        role="Finance Operations Manager",
        product=config.product(product_id),
    )
    run.findings = [
        Finding(
            claim=claim, publisher="Meridian Outfitters", url="https://m.example/policy",
            provenance=PROV_SEARCH_SUMMARY, verification_note="corroborated",
        )
    ]
    pipeline._assign_finding_ids(run)
    return run


def test_the_same_finding_is_usable_for_one_product_and_background_for_another(monkeypatch):
    """The acceptance example: receipt chasing is a reason to write about
    receipt tracking, and only background for invoice matching."""
    # Expense receipt tracking: collecting missing receipts is a listed capability.
    good = _one_finding_run(RECEIPTS)
    _with_scores(monkeypatch, [
        _score_row("f-1", 3, 3, 2, 1, capability=RECEIPTS_CAP,
                   product_relevance_reason="collecting missing expense receipts, exactly this"),
    ])
    pipeline.stage_score(good)
    assert good.score_for("f-1").eligibility == ELIGIBLE
    assert good.score_for("f-1").capability == RECEIPTS_CAP
    assert good.recommended_id == "f-1" and good.status != STATUS_INSUFFICIENT_EVIDENCE

    # Invoice matching: the same sentence gives no invoice-to-PO connection.
    weak = _one_finding_run(INVOICE)
    _with_scores(monkeypatch, [
        _score_row("f-1", 1, 3, 2, 1),
    ])
    pipeline.stage_score(weak)
    score = weak.score_for("f-1")
    assert score.total == 7                         # a high total, and still unusable
    assert score.eligibility == CONTEXT_ONLY
    assert "Invoice matching" in score.eligibility_reason
    assert weak.status == STATUS_INSUFFICIENT_EVIDENCE
    assert not weak.draft.subject and weak.active_id == ""
    assert "Invoice matching" in weak.stop_reason
    assert "another product" in weak.stop_reason.lower()


def test_product_relevance_of_one_is_background_only_not_eligible(monkeypatch):
    """The threshold moved from 1 to 2, deliberately."""
    assert MIN_PRODUCT_RELEVANCE == 2
    run = _run_with_findings(DISTINCT_CLAIMS[:2])
    _with_scores(monkeypatch, [
        _score_row("f-1", 1, 3, 2, 2),      # 8 points, broad area only
        _score_row("f-2", 2, 1, 1, 1),      # 5 points, a related workflow
    ])
    pipeline.stage_score(run)
    assert run.score_for("f-1").eligibility == CONTEXT_ONLY
    assert run.score_for("f-2").eligibility == ELIGIBLE
    assert run.recommended_id == "f-2"      # the weaker total is the usable one
    assert run.ranking == ["f-2", "f-1"]


def test_research_scoring_and_drafting_all_receive_the_chosen_product(monkeypatch):
    """The product has to reach the model, not just the screen."""
    from outreach.pipeline import execute

    search_prompts: list[str] = []
    json_prompts: list[str] = []

    class _G:
        def __init__(self):
            self.text, self.sources, self.queries = "summary", _fake_sources(), ["q"]

    def fake_search(prompt, *a, **k):
        search_prompts.append(prompt)
        return _G()

    answers = [
        {"status": "confirmed", "confidence_reason": "ok", "ambiguity": "", "candidates": []},
        {"findings": [{
            "claim": "Aurora Freight is hiring an AP Analyst to match supplier invoices "
                     "against purchase orders and escalate mismatches.",
            "publisher": "Aurora Freight careers",
            "url": "https://aurora-freight.example/careers/ap-analyst",
            "date": "2026-10-01", "kind": "job posting", "quote": "",
        }]},
        {"scores": [_score_row("f-1", 3, 2, 2, 2)]},
        {"subject": "Your AP analyst posting", "body": "Hi - how do you handle that today?"},
    ]

    def fake_json(prompt, *a, **k):
        json_prompts.append(prompt)
        return answers.pop(0)

    monkeypatch.setattr(pipeline, "grounded_search", fake_search)
    monkeypatch.setattr(pipeline, "json_call", fake_json)
    monkeypatch.setattr(
        pipeline.verify, "fetch_page_text",
        lambda url: (None, url, "network disabled in tests"),
    )

    run = _run_for(INVOICE)
    execute(run)
    assert run.status == STATUS_AWAITING_REVIEW

    # Identity is deliberately product-blind; everything after it is not.
    identity_prompt, research_prompt = search_prompts
    assert "Invoice matching" not in identity_prompt
    assert "Invoice matching" in research_prompt
    assert INVOICE_CAP in research_prompt

    scoring_prompt, draft_prompt = json_prompts[2], json_prompts[3]
    assert "Invoice matching" in scoring_prompt and INVOICE_CAP in scoring_prompt
    assert "Invoice matching" in draft_prompt and INVOICE_CAP in draft_prompt
    # The capability the model named is handed to the drafting call.
    assert "capability this connects to: " + INVOICE_CAP in draft_prompt
    # And no other product leaks into any prompt.
    for prompt in search_prompts[1:] + json_prompts[2:]:
        assert "Expense receipt tracking" not in prompt
        assert "Vendor onboarding" not in prompt


def test_a_run_keeps_its_product_through_switching_and_reopening(monkeypatch):
    """Switching signals changes the draft, never the product."""
    run = fixtures.build("E")
    assert run.product.product_id == RECEIPTS
    canned = fixtures.alternate_draft("E", "f-2")
    pipeline.redraft(run, "f-2", draft_fn=lambda r, f: canned)
    assert run.product.product_id == RECEIPTS and not run.product.legacy
    assert run.active_id == "f-2"
    assert any("Still selling Expense receipt tracking" in e["message"] for e in run.stage_log)

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "p.db"
        monkeypatch.setattr(config, "sqlite_path", lambda: db)
        monkeypatch.setattr(config, "database_url", lambda: None)
        from outreach.store import Store

        store = Store()
        store.save(run)
        row = store.list_runs()[0]
        assert row["product"] == "Expense receipt tracking"
        loaded = store.get(run.run_id)
        assert loaded.product.product_id == RECEIPTS
        assert loaded.product.capabilities == run.product.capabilities


def test_a_retry_keeps_the_original_product_not_the_form_default(monkeypatch):
    """Re-running an interrupted run must not silently change what we sell."""
    from outreach.pipeline import execute

    run = fixtures.build("D")                      # vendor onboarding, interrupted
    assert run.product.product_id == "vendor_onboarding"
    run.identity.status = "confirmed"

    captured: list[str] = []

    class _G:
        def __init__(self):
            self.text, self.sources, self.queries = "summary", {}, ["q"]

    def fake_search(prompt, *a, **k):
        captured.append(prompt)
        return _G()

    monkeypatch.setattr(pipeline, "grounded_search", fake_search)
    monkeypatch.setattr(pipeline, "json_call", lambda *a, **k: {"findings": []})
    execute(run, skip_identity=True)

    assert run.product.product_id == "vendor_onboarding"
    assert "Vendor onboarding" in captured[0]
    assert "Collecting supplier documents during onboarding" in captured[0]


def test_fixture_e_is_demo_ready():
    """The default product's sample must show the ranking the demo talks about."""
    e = fixtures.build("E")
    assert e.product.product_id == RECEIPTS and not e.product.legacy
    assert {s.finding_id: s.total for s in e.scores} == {"f-1": 9, "f-2": 8, "f-3": 5}
    assert sum(1 for s in e.scores if s.eligibility == ELIGIBLE) == 2
    assert sum(1 for s in e.scores if s.eligibility == CONTEXT_ONLY) == 1
    assert e.recommended_id == "f-1" and e.draft.finding_id == "f-1"
    # Both usable signals name a capability this product actually has.
    for s in e.scores:
        if s.eligibility == ELIGIBLE:
            assert e.product.matches_capability(s.capability) == RECEIPTS_CAP
        for key, _, _, _, reason in s.components():
            assert reason, (s.finding_id, key)
    # The acceptance example is in there as the runner-up.
    assert "missing expense receipts" in e.finding_by_id("f-2").claim


def test_fixture_e_draft_only_quotes_verified_text():
    e = fixtures.build("E")
    f = e.selected_finding()
    assert f and f.quote_verified
    _, removed = _strip_unverified_quotes(e.draft.body, allowed_quote=f.quote)
    assert removed == 0
    # The runner-up is a summary, so its stored email quotes nothing.
    alt = fixtures.alternate_draft("E", "f-2")
    assert chr(34) not in alt.body and chr(8220) not in alt.body


def test_every_sample_scenario_declares_its_product():
    for fid, spec in fixtures.FIXTURES.items():
        run = fixtures.build(fid)
        assert spec["product"] == run.product.name, fid
        assert not run.product.legacy
        # Scenario names say what the scenario is, not what the code calls it.
        label = str(spec["label"]).lower()
        assert "fixture" not in label and "eligib" not in label
    # The default product leads the list, so the first example matches the form.
    first = next(iter(fixtures.FIXTURES))
    assert fixtures.build(first).product.product_id == config.DEFAULT_PRODUCT_ID


def test_demo_flow_for_the_receipt_tracking_sample(monkeypatch):
    """Try the example -> inspect -> switch -> approve -> reopen from history."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "demo_e.db"
        monkeypatch.setattr(config, "sqlite_path", lambda: db)
        monkeypatch.setattr(config, "database_url", lambda: None)
        from outreach.store import Store

        store = Store()
        run = fixtures.replay("E", step_delay=0.0)
        store.save(run)
        assert run.status == STATUS_AWAITING_REVIEW

        # Inspect: the screen can explain why #1 came first, and what it connects to.
        top = run.score_for(run.recommended_id)
        assert "9 of 10" in run.selection_reason
        assert RECEIPTS_CAP.lower() in pipeline.why_it_matters(run, top).lower()

        # Switch to the runner-up, with no model call and no new search.
        canned = fixtures.alternate_draft("E", "f-2")
        pipeline.redraft(run, "f-2", draft_fn=lambda r, f: canned)
        store.save(run)

        # Review and approve.
        run.draft.edited_body = run.draft.body + "\n\nPS - thanks for the interview."
        run.draft.decision = "approved"
        run.draft.decided_at = "2026-11-17T12:00:00+00:00"
        run.status = STATUS_APPROVED
        store.save(run)

        assert len(store.list_runs()) == 1
        row = store.list_runs()[0]
        assert row["product"] == "Expense receipt tracking"
        assert "8 of 10" in row["signal"] and "reviewer" in row["signal"]

        # Reopen: same product, same signal, same approved email.
        loaded = store.get(run.run_id)
        assert loaded.product.product_id == RECEIPTS
        assert loaded.status == STATUS_APPROVED
        assert loaded.active_id == "f-2" and loaded.draft.finding_id == "f-2"
        assert loaded.recommended_id == "f-1"
        assert "thanks for the interview" in loaded.draft.final_body()
        assert loaded.score_for("f-2").capability == RECEIPTS_CAP


def test_why_it_matters_names_the_capability_without_inventing_anything():
    e = fixtures.build("E")
    score = e.score_for("f-1")
    sentence = pipeline.why_it_matters(e, score)
    # Built only from what was already scored and shown: the two reasons, and
    # the capability the model named.
    assert score.reasons["product_relevance"].rstrip(".") in sentence
    assert score.reasons["prospect_relevance"].rstrip(".") in sentence
    assert RECEIPTS_CAP.lower() in sentence.lower()

    # When the reason does not name the capability, the sentence spells it out.
    terse = Score(
        finding_id="f-1", product_relevance=3, prospect_relevance=2,
        evidence_quality=2, timeliness=2, capability=RECEIPTS_CAP,
        reasons={"product_relevance": "the posting says so",
                 "prospect_relevance": "her own function"},
    )
    assert "Expense receipt tracking" in pipeline.why_it_matters(e, terse)

    # A background-only finding claims no capability, so it claims no product fit.
    background = pipeline.why_it_matters(e, e.score_for("f-3"))
    assert "Expense receipt tracking" not in background
    assert RECEIPTS_CAP.lower() not in background.lower()


def test_no_single_product_wording_survives_in_shared_code():
    """Rejection messages and prompt templates must not assume one product."""
    import inspect

    from outreach import prompts

    for module in (pipeline, prompts):
        src = inspect.getsource(module).lower()
        for word in ("invoice-to-po", "accounts payable", "three-way"):
            assert word not in src, (module.__name__, word)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
