"""Offline checks. No network, no model calls, no API key needed.

Run with:  python -m pytest tests -q      (or)  python tests/test_offline.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from outreach import config, fixtures, verify  # noqa: E402
from outreach.pipeline import _strip_unverified_quotes, stage_signal  # noqa: E402
from outreach.schema import (  # noqa: E402
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
)

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


def test_failed_evidence_check_overrides_tally(monkeypatch):
    """3-of-4 must never produce a draft when the evidence check fails."""
    import outreach.pipeline as pipeline

    run = Run(prospect_name="A B", company="C")
    run.findings = [
        Finding(claim="x", publisher="p", url="u", provenance=PROV_SEARCH_SUMMARY)
    ]
    monkeypatch.setattr(pipeline, "json_call", lambda *a, **k: {
        "selected_index": 0,
        "sufficient": True,
        "selection_reason": "only option",
        "checks": [
            {"name": "Evidence", "passed": False, "reason": "no source states this"},
            {"name": "Role relevance", "passed": True, "reason": "ok"},
            {"name": "Product relevance", "passed": True, "reason": "ok"},
            {"name": "Timeliness", "passed": True, "reason": "ok"},
        ],
    })
    stage_signal(run)
    assert run.status == STATUS_INSUFFICIENT_EVIDENCE
    assert run.checks_met() == (3, 4)
    assert not run.draft.subject


def test_fixtures_have_expected_outcomes():
    expected = {
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
    assert a.checks_met() == (4, 4)
    c = fixtures.build("C")
    assert c.checks_met() == (3, 4) and c.stop_reason
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


def test_seller_profile_is_the_fixed_sentence():
    assert config.SELLER_PROFILE.startswith("We sell software that helps accounts payable")
    assert len(config.SELLER_CAPABILITIES) == 2


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
        {"selected_index": 0, "sufficient": True, "selection_reason": "only one on point",
         "checks": [{"name": n, "passed": True, "reason": "ok"} for n in
                    ("Evidence", "Role relevance", "Product relevance", "Timeliness")]},
        {"subject": "Your AP analyst posting", "body": "Hi — how does your team handle "
                                                       "mismatches today?"},
    ])
    stages = []
    run = Run(prospect_name="Maya Iyer", company="Aurora Freight")
    execute(run, on_stage=lambda r: stages.append(r.stage))

    assert run.status == STATUS_AWAITING_REVIEW
    assert run.draft.subject and run.draft.body
    assert run.selected_finding().url.endswith("/ap-analyst")
    assert run.checks_met() == (4, 4)
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
    run = Run(prospect_name="Maya Iyer", company="Aurora Freight")
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
    run = Run(prospect_name="Michael Chen", company="Veridian Health")
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
    run = Run(prospect_name="Alina Moreau", company="Castellan Foods")
    execute(run)
    assert run.status == STATUS_RESEARCH_INCOMPLETE
    assert "503" in run.error
    assert run.status != STATUS_INSUFFICIENT_EVIDENCE


def test_missing_credentials_reports_research_incomplete(monkeypatch):
    from outreach.pipeline import execute

    monkeypatch.setattr(config, "google_api_key", lambda: None)
    run = Run(prospect_name="Maya Iyer", company="Aurora Freight")
    execute(run)
    assert run.status == STATUS_RESEARCH_INCOMPLETE
    assert "GOOGLE_API_KEY" in run.error


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
