"""Rehearsal fixtures.

These are canned runs for rehearsing the demo. They perform NO web search and
NO model calls, and every fixture run is stored with ``mode = "fixture"`` so the
history view and the run view label it as such. The companies and people are
fictional and the source URLs are synthetic -- a fixture run is never evidence
that live research works.

Replaying a fixture walks its real stage log with a short pause per step, so the
live run view behaves the same way it does on a real run.
"""

from __future__ import annotations

import time
from typing import Callable

from .schema import (
    PROV_SEARCH_SUMMARY,
    PROV_SOURCE_TEXT,
    STATUS_AWAITING_REVIEW,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_RESEARCH_INCOMPLETE,
    Check,
    Draft,
    Finding,
    Identity,
    Run,
    Source,
)

# ---------------------------------------------------------------------------
# A -- happy path
# ---------------------------------------------------------------------------
_A_QUOTE = (
    "You will own three-way matching of supplier invoices against purchase "
    "orders and goods receipt notes, and escalate mismatches to the finance "
    "manager for review."
)


def _fixture_a() -> Run:
    run = Run(
        prospect_name="Priya Raghavan",
        company="Northwind Logistics",
        role="Head of Finance Operations",
        company_website="https://northwind-logistics.example",
        mode="fixture",
        fixture_id="A",
    )
    run.run_id = "fixtureA" + str(int(time.time()))[-4:]
    run.identity = Identity(
        status="confirmed",
        confidence_reason=(
            "The company's own leadership page lists Priya Raghavan as Head of "
            "Finance Operations, and a 2026 trade-press interview names her in "
            "the same role at the same company."
        ),
    )
    run.sources = [
        Source(
            short_id="src-1",
            title="Leadership — Northwind Logistics",
            url="https://northwind-logistics.example/about/leadership",
            domain="northwind-logistics.example",
            supported_claims=[{
                "text_segment": "Priya Raghavan leads Finance Operations at Northwind Logistics.",
                "confidence": 0.93,
            }],
        ),
        Source(
            short_id="src-2",
            title="Accounts Payable Analyst — Careers at Northwind Logistics",
            url="https://northwind-logistics.example/careers/accounts-payable-analyst",
            domain="northwind-logistics.example",
            supported_claims=[{
                "text_segment": (
                    "The Accounts Payable Analyst role covers three-way matching of "
                    "supplier invoices against purchase orders and escalation of mismatches."
                ),
                "confidence": 0.91,
            }],
        ),
        Source(
            short_id="src-3",
            title="Northwind opens second distribution hub in Coimbatore",
            url="https://freightweekly.example/news/northwind-coimbatore-hub",
            domain="freightweekly.example",
            supported_claims=[{
                "text_segment": "Northwind Logistics opened a second distribution hub in Coimbatore.",
                "confidence": 0.84,
            }],
        ),
    ]
    run.findings = [
        Finding(
            claim=(
                "Northwind Logistics has an open Accounts Payable Analyst posting whose "
                "duties include three-way matching of supplier invoices against purchase "
                "orders and escalating mismatches to the finance manager."
            ),
            publisher="Northwind Logistics careers site",
            url="https://northwind-logistics.example/careers/accounts-payable-analyst",
            date="2026-10-28",
            source_id="src-2",
            kind="job posting",
            quote=_A_QUOTE,
            provenance=PROV_SOURCE_TEXT,
            quote_verified=True,
            verification_note="Quote matched verbatim on the source page.",
        ),
        Finding(
            claim=(
                "Northwind Logistics opened a second distribution hub in Coimbatore in "
                "September 2026."
            ),
            publisher="Freight Weekly",
            url="https://freightweekly.example/news/northwind-coimbatore-hub",
            date="2026-09-16",
            source_id="src-3",
            kind="news",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim=(
                "Priya Raghavan is listed as Head of Finance Operations on the company's "
                "leadership page."
            ),
            publisher="Northwind Logistics",
            url="https://northwind-logistics.example/about/leadership",
            date="",
            source_id="src-1",
            kind="official page",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
    ]
    run.selected_index = 0
    run.selection_reason = (
        "The job posting is the only finding that names invoice-to-PO matching and "
        "mismatch escalation — the exact work our product does — and it sits inside "
        "the team this person runs."
    )
    run.checks = [
        Check("Evidence", True,
              "The company's own careers page states the matching and escalation duties; "
              "the quoted sentence was matched verbatim."),
        Check("Role relevance", True,
              "The posting is an Accounts Payable role, and this prospect heads Finance "
              "Operations, so the role reports into her function."),
        Check("Product relevance", True,
              "The posting names invoice-to-PO matching and escalation of mismatches, "
              "which maps directly to our two stated capabilities."),
        Check("Timeliness", True,
              "The posting is dated 28 October 2026 and is still listed as open."),
    ]
    run.draft = Draft(
        subject="Your AP analyst posting at Northwind",
        body=(
            "Hi Priya,\n\n"
            "I came across Northwind's Accounts Payable Analyst posting — it says the role "
            "will \"own three-way matching of supplier invoices against purchase orders and "
            "goods receipt notes, and escalate mismatches to the finance manager for "
            "review.\"\n\n"
            "That's the work we build for: matching supplier invoices to purchase orders and "
            "routing the discrepancies to a reviewer. I'm curious how your team handles those "
            "mismatches today — is the escalation step something a person does manually?\n\n"
            "Best,\n[Your name]"
        ),
    )
    run.status = STATUS_AWAITING_REVIEW
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Searching for public evidence on Priya Raghavan at Northwind Logistics."},
        {"at": "", "stage": "Identity", "message": "3 search(es) run, 3 source(s) cited."},
        {"at": "", "stage": "Identity", "message": "Identity confirmed. " + run.identity.confidence_reason},
        {"at": "", "stage": "Research", "message": "Searching company pages, job postings, announcements and interviews."},
        {"at": "", "stage": "Research", "message": "Verifying 3 finding(s) against their sources."},
        {"at": "", "stage": "Research", "message": "Northwind Logistics careers site: Quote matched verbatim on the source page."},
        {"at": "", "stage": "Research", "message": "3 of 3 finding(s) verified and usable."},
        {"at": "", "stage": "Signal selection", "message": "Comparing 3 verified finding(s) against our offer."},
        {"at": "", "stage": "Signal selection", "message": "Selected the AP Analyst posting (4 of 4 checks met)."},
        {"at": "", "stage": "Draft", "message": "Writing a first-contact email from the selected evidence."},
        {"at": "", "stage": "Human review", "message": "Draft ready for the salesperson to edit, approve or reject."},
    ]
    return run


# ---------------------------------------------------------------------------
# B -- ambiguous identity
# ---------------------------------------------------------------------------
def _fixture_b() -> Run:
    run = Run(
        prospect_name="Michael Chen",
        company="Veridian Health",
        role="",
        mode="fixture",
        fixture_id="B",
    )
    run.run_id = "fixtureB" + str(int(time.time()))[-4:]
    run.sources = [
        Source(
            short_id="src-1",
            title="Veridian Health appoints Michael Chen as VP Finance",
            url="https://veridianhealth.example/newsroom/vp-finance-appointment",
            domain="veridianhealth.example",
            supported_claims=[{
                "text_segment": "Veridian Health announced Michael Chen as VP Finance in 2023.",
                "confidence": 0.78,
            }],
        ),
        Source(
            short_id="src-2",
            title="Meet the team — Harborline Capital",
            url="https://harborlinecapital.example/team",
            domain="harborlinecapital.example",
            supported_claims=[{
                "text_segment": "Michael Chen is a partner at Harborline Capital.",
                "confidence": 0.71,
            }],
        ),
        Source(
            short_id="src-3",
            title="Veridian Health leadership",
            url="https://veridianhealth.example/about/leadership",
            domain="veridianhealth.example",
            supported_claims=[{
                "text_segment": "Veridian Health's current leadership page lists Anita Deshpande as CFO and does not mention Michael Chen.",
                "confidence": 0.82,
            }],
        ),
    ]
    run.identity = Identity(
        status="ambiguous",
        confidence_reason=(
            "A 2023 Veridian Health press release names a Michael Chen as VP Finance, but "
            "the company's current leadership page does not list him."
        ),
        ambiguity=(
            "Two different people named Michael Chen appear in finance roles, and the "
            "Veridian Health evidence is out of date: the 2023 appointment press release "
            "names him, but the current leadership page does not. He may have left. Add "
            "his profile link, or confirm which Michael Chen you mean."
        ),
        candidates=[
            {"description": "Michael Chen — VP Finance, Veridian Health (2023 announcement)",
             "why": "Named in the company's own 2023 appointment press release.",
             "url": "https://veridianhealth.example/newsroom/vp-finance-appointment"},
            {"description": "Michael Chen — Partner, Harborline Capital",
             "why": "Listed on Harborline Capital's team page; a different company.",
             "url": "https://harborlinecapital.example/team"},
            {"description": "Possible departure from Veridian Health",
             "why": "Veridian's current leadership page lists a different finance lead and does not mention him.",
             "url": "https://veridianhealth.example/about/leadership"},
        ],
    )
    run.status = STATUS_NEEDS_CLARIFICATION
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Searching for public evidence on Michael Chen at Veridian Health."},
        {"at": "", "stage": "Identity", "message": "2 search(es) run, 3 source(s) cited."},
        {"at": "", "stage": "Identity", "message": "Sources disagree about the current employer; more than one person matches the name."},
        {"at": "", "stage": "Identity", "message": "Paused — needs clarification. " + run.identity.ambiguity},
    ]
    return run


# ---------------------------------------------------------------------------
# C -- weak signal (identity fine, evidence irrelevant)
# ---------------------------------------------------------------------------
def _fixture_c() -> Run:
    run = Run(
        prospect_name="Daniel Okafor",
        company="Lumenbridge Studios",
        role="VP of Engineering",
        mode="fixture",
        fixture_id="C",
    )
    run.run_id = "fixtureC" + str(int(time.time()))[-4:]
    run.identity = Identity(
        status="confirmed",
        confidence_reason=(
            "Lumenbridge Studios' own team page lists Daniel Okafor as VP of Engineering, "
            "and a 2026 conference programme lists him as a speaker with the same title."
        ),
    )
    run.sources = [
        Source(
            short_id="src-1", title="Team — Lumenbridge Studios",
            url="https://lumenbridge.example/team", domain="lumenbridge.example",
            supported_claims=[{"text_segment": "Daniel Okafor is VP of Engineering at Lumenbridge Studios.", "confidence": 0.9}],
        ),
        Source(
            short_id="src-2", title="DevCraft 2026 — speaker programme",
            url="https://devcraft.example/2026/programme", domain="devcraft.example",
            supported_claims=[{"text_segment": "Daniel Okafor spoke on real-time rendering pipelines at DevCraft 2026.", "confidence": 0.86}],
        ),
        Source(
            short_id="src-3", title="Lumenbridge wins art direction award",
            url="https://indiegamespress.example/lumenbridge-art-award", domain="indiegamespress.example",
            supported_claims=[{"text_segment": "Lumenbridge Studios won an art direction award for its 2026 title.", "confidence": 0.8}],
        ),
    ]
    run.findings = [
        Finding(
            claim="Daniel Okafor gave a talk on real-time rendering pipelines at DevCraft 2026.",
            publisher="DevCraft 2026 programme",
            url="https://devcraft.example/2026/programme", date="2026-06-11",
            source_id="src-2", kind="interview",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim="Lumenbridge Studios won an art direction award for its 2026 title.",
            publisher="Indie Games Press",
            url="https://indiegamespress.example/lumenbridge-art-award", date="2026-08-02",
            source_id="src-3", kind="news",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim="Lumenbridge Studios lists 42 employees on its team page.",
            publisher="Lumenbridge Studios",
            url="https://lumenbridge.example/team", date="",
            source_id="src-1", kind="official page",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
    ]
    run.selected_index = 0
    run.selection_reason = (
        "The conference talk is the strongest of the three because it is the prospect's "
        "own public statement — but it is about rendering engineering, not finance "
        "operations."
    )
    run.checks = [
        Check("Evidence", True, "The DevCraft programme page names him and the talk topic."),
        Check("Role relevance", True, "The talk is squarely within his engineering remit."),
        Check("Product relevance", False,
              "Nothing found touches accounts payable, invoices, purchase orders or "
              "finance operations. He runs engineering at a games studio; a rendering "
              "talk gives no opening to our invoice-matching offer."),
        Check("Timeliness", True, "The talk is dated June 2026, within the last twelve months."),
    ]
    run.status = STATUS_INSUFFICIENT_EVIDENCE
    run.stop_reason = (
        "Identity is confirmed, but none of the three verified findings connects this "
        "person or their team to invoice-to-PO matching or discrepancy review. Writing "
        "outreach from this evidence would mean inventing a reason to make contact, so "
        "the run stops here. 3 of 4 checks met does not override the failed product "
        "relevance check."
    )
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Searching for public evidence on Daniel Okafor at Lumenbridge Studios."},
        {"at": "", "stage": "Identity", "message": "Identity confirmed. " + run.identity.confidence_reason},
        {"at": "", "stage": "Research", "message": "Searching company pages, job postings, announcements and interviews."},
        {"at": "", "stage": "Research", "message": "3 of 3 finding(s) verified and usable."},
        {"at": "", "stage": "Signal selection", "message": "Comparing 3 verified finding(s) against our offer."},
        {"at": "", "stage": "Signal selection", "message": "No credible connection to our offer (3 of 4 checks met). Stopping."},
    ]
    return run


# ---------------------------------------------------------------------------
# D -- provider failure (distinct from 'Insufficient evidence')
# ---------------------------------------------------------------------------
def _fixture_d() -> Run:
    run = Run(
        prospect_name="Alina Moreau",
        company="Castellan Foods",
        role="Finance Director",
        mode="fixture",
        fixture_id="D",
    )
    run.run_id = "fixtureD" + str(int(time.time()))[-4:]
    run.identity = Identity(
        status="confirmed",
        confidence_reason="The company's investor page lists Alina Moreau as Finance Director.",
    )
    run.status = STATUS_RESEARCH_INCOMPLETE
    run.error = "ServerError: 503 The search backend is temporarily unavailable."
    run.stop_reason = (
        "The search provider failed part-way through, so we do not know whether a usable "
        "signal exists. Retry before concluding anything."
    )
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Identity confirmed. " + run.identity.confidence_reason},
        {"at": "", "stage": "Research", "message": "Searching company pages, job postings, announcements and interviews."},
        {"at": "", "stage": "Research", "message": "Research incomplete: ServerError: 503 The search backend is temporarily unavailable."},
    ]
    return run


FIXTURES: dict[str, dict[str, object]] = {
    "A": {
        "label": "A · Happy path — Priya Raghavan, Northwind Logistics",
        "summary": "Clearly identified prospect, a verified job posting that names invoice-to-PO "
                   "matching, four of four checks met, draft ready for review.",
        "expected": "Awaiting review",
        "build": _fixture_a,
    },
    "B": {
        "label": "B · Ambiguous identity — Michael Chen, Veridian Health",
        "summary": "Two people share the name and the company's own pages disagree about whether "
                   "he still works there. The run pauses before any research spend.",
        "expected": "Needs clarification",
        "build": _fixture_b,
    },
    "C": {
        "label": "C · Weak signal — Daniel Okafor, Lumenbridge Studios",
        "summary": "Identity confirmed and findings verified, but nothing connects him to invoice "
                   "matching. The run records why it refused to draft.",
        "expected": "Insufficient evidence",
        "build": _fixture_c,
    },
    "D": {
        "label": "D · Provider failure — Alina Moreau, Castellan Foods",
        "summary": "The search backend errors mid-run. Recorded as a retryable failure, not as a "
                   "conclusion about the prospect.",
        "expected": "Research incomplete",
        "build": _fixture_d,
    },
}


def build(fixture_id: str) -> Run:
    spec = FIXTURES[fixture_id]
    return spec["build"]()  # type: ignore[operator, no-any-return]


def replay(
    fixture_id: str,
    on_stage: Callable[[Run], None] | None = None,
    *,
    step_delay: float = 0.55,
) -> Run:
    """Rebuild a fixture run, replaying its stage log so the UI animates."""
    final = build(fixture_id)
    log = list(final.stage_log)

    live = Run.from_dict(final.to_dict())
    live.stage_log = []
    live.status = "Running"
    live.findings = []
    live.sources = []
    live.checks = []
    live.draft = Draft()
    live.selected_index = -1

    if on_stage:
        on_stage(live)
    for entry in log:
        live.stage = entry["stage"]
        live.stage_log.append(entry)
        # Reveal the data as the stage that produced it completes.
        if entry["stage"] == "Research":
            live.sources = final.sources
            if "verified and usable" in entry["message"]:
                live.findings = final.findings
        elif entry["stage"] == "Signal selection":
            live.sources, live.findings = final.sources, final.findings
            if "Selected" in entry["message"] or "Stopping" in entry["message"]:
                live.checks = final.checks
                live.selected_index = final.selected_index
                live.selection_reason = final.selection_reason
        elif entry["stage"] in ("Draft", "Human review"):
            live.sources, live.findings = final.sources, final.findings
            live.checks, live.selected_index = final.checks, final.selected_index
        if on_stage:
            on_stage(live)
        time.sleep(step_delay)

    return final
