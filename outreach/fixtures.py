"""Sample scenarios for rehearsing the app.

These are canned runs. They perform NO web search and NO model calls, and every
one is stored with ``mode = "fixture"`` so the run view and the history view
label it as sample data. The companies, people and source URLs are fictional,
and a sample run is never evidence that live research works.

Each scenario declares its product, its findings and the raw rubric scores a
model might return. Eligibility, ranking, the checks and the "why it ranked
first" sentence are then computed by the real pipeline code, so a sample run
cannot show a verdict the live code would not reach.

Replaying a scenario walks its stage log with a short pause per step, so the
live run view behaves the same way it does on a real run.
"""

from __future__ import annotations

import time
from typing import Callable

from . import config, pipeline
from .schema import (
    ELIGIBLE,
    PROV_SEARCH_SUMMARY,
    PROV_SOURCE_TEXT,
    STATUS_AWAITING_REVIEW,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_RESEARCH_INCOMPLETE,
    Draft,
    Finding,
    Identity,
    Run,
    Score,
    Source,
)


def _finalise(run: Run) -> None:
    """Apply the real eligibility gates, ranking and rationale to a sample run.

    The scenario supplies only the raw scores. Everything a reviewer is shown
    about what those scores *mean* comes from the pipeline, so the samples stay
    in step with the code even when the thresholds change.
    """
    pipeline._apply_eligibility(run, run.scores)
    pipeline.rank_scores(run, run.scores)
    eligible = run.ranked_findings(ELIGIBLE)
    if eligible:
        _, top, score = eligible[0]
        run.recommended_id = top.finding_id
        run.set_active_finding(top.finding_id)
        run.checks = pipeline._checks_from_score(run, score)
        run.selection_reason = pipeline.winner_rationale(run)
    else:
        run.recommended_id = ""
        run.active_id = ""
        run.selected_index = -1
        run.checks = []
        run.selection_reason = ""


# ---------------------------------------------------------------------------
# E -- strong match for the default product (expense receipt tracking)
# ---------------------------------------------------------------------------
_E_QUOTE = (
    "You will collect missing receipts from employees and follow up until each "
    "expense report is complete."
)

_E_CAPABILITY = "Collecting missing employee expense receipts"


def _fixture_e() -> Run:
    """Strong match for Expense receipt tracking, the default product.

    Three findings: an open expense-operations role that names receipt chasing
    (9), the prospect describing that same chase in an interview (8), and a new
    distribution centre that scores 5 and is background only because no listed
    capability connects to it. The two usable signals make switching signals
    demonstrable with no API key.
    """
    run = Run(
        prospect_name="Hannah Weiss",
        company="Meridian Outfitters",
        role="Finance Operations Manager",
        company_website="https://meridian-outfitters.example",
        product=config.product("receipt_tracking"),
        mode="fixture",
        fixture_id="E",
    )
    run.run_id = "fixtureE" + str(int(time.time()))[-4:]
    run.identity = Identity(
        status="confirmed",
        confidence_reason=(
            "Meridian Outfitters' own team page lists Hannah Weiss as Finance "
            "Operations Manager, and a 2026 trade-press interview names her in the "
            "same role at the same company."
        ),
    )
    run.sources = [
        Source(
            short_id="src-1",
            title="Our team — Meridian Outfitters",
            url="https://meridian-outfitters.example/about/team",
            domain="meridian-outfitters.example",
            supported_claims=[{
                "text_segment": (
                    "Hannah Weiss is Finance Operations Manager at Meridian Outfitters."
                ),
                "confidence": 0.92,
            }],
        ),
        Source(
            short_id="src-2",
            title="Expense Operations Analyst — Careers at Meridian Outfitters",
            url="https://meridian-outfitters.example/careers/expense-operations-analyst",
            domain="meridian-outfitters.example",
            supported_claims=[{
                "text_segment": (
                    "The Expense Operations Analyst role covers collecting missing "
                    "receipts from employees and following up until each expense "
                    "report is complete."
                ),
                "confidence": 0.93,
            }],
        ),
        Source(
            short_id="src-3",
            title="Closing the books at a growing retailer — Meridian's finance lead",
            url="https://retailfinancereview.example/interviews/meridian-month-end",
            domain="retailfinancereview.example",
            supported_claims=[{
                "text_segment": (
                    "Hannah Weiss said her finance team follows up with employees "
                    "about missing expense receipts through the first week of each month."
                ),
                "confidence": 0.87,
            }],
        ),
        Source(
            short_id="src-4",
            title="Meridian Outfitters opens a third distribution centre in Porto",
            url="https://retailfinancereview.example/news/meridian-porto",
            domain="retailfinancereview.example",
            supported_claims=[{
                "text_segment": (
                    "Meridian Outfitters opened a third distribution centre in Porto "
                    "in October 2026."
                ),
                "confidence": 0.9,
            }],
        ),
    ]
    run.findings = [
        Finding(
            claim=(
                "Meridian Outfitters has an open Expense Operations Analyst posting "
                "whose duties include collecting missing receipts from employees and "
                "following up until each expense report is complete."
            ),
            publisher="Meridian Outfitters careers site",
            url="https://meridian-outfitters.example/careers/expense-operations-analyst",
            date="2026-11-04",
            finding_id="f-1",
            source_id="src-2",
            kind="job posting",
            quote=_E_QUOTE,
            provenance=PROV_SOURCE_TEXT,
            quote_verified=True,
            verification_note="Quote matched verbatim on the source page.",
        ),
        Finding(
            claim=(
                "In a trade-press interview, Hannah Weiss said her finance team "
                "follows up with employees about missing expense receipts through the "
                "first week of each month."
            ),
            publisher="Retail Finance Review",
            url="https://retailfinancereview.example/interviews/meridian-month-end",
            date="2026-09-16",
            finding_id="f-2",
            source_id="src-3",
            kind="interview",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim=(
                "Meridian Outfitters opened a third distribution centre in Porto in "
                "October 2026."
            ),
            publisher="Retail Finance Review",
            url="https://retailfinancereview.example/news/meridian-porto",
            date="2026-10-21",
            finding_id="f-3",
            source_id="src-4",
            kind="news",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
    ]
    run.scores = [
        Score(
            finding_id="f-1",
            product_relevance=3, prospect_relevance=2, evidence_quality=2, timeliness=2,
            capability=_E_CAPABILITY,
            reasons={
                "product_relevance":
                    "Collecting missing employee expense receipts: the posting names "
                    "exactly that duty.",
                "prospect_relevance":
                    "An expense role inside the finance operations function she manages.",
                "evidence_quality": "The company's own job posting states the duties.",
                "timeliness": "Posted 4 November 2026 and still open.",
            },
        ),
        Score(
            finding_id="f-2",
            product_relevance=3, prospect_relevance=3, evidence_quality=1, timeliness=1,
            capability=_E_CAPABILITY,
            reasons={
                "product_relevance":
                    "Collecting missing employee expense receipts: she describes her "
                    "team doing that chase monthly.",
                "prospect_relevance": "Her own statement about her own team's month end.",
                "evidence_quality":
                    "Trade reporting of her words; the wording was not matched verbatim.",
                "timeliness": "Dated September 2026; plausibly still monthly, not shown.",
            },
        ),
        Score(
            finding_id="f-3",
            product_relevance=0, prospect_relevance=1, evidence_quality=2, timeliness=2,
            reasons={
                "product_relevance":
                    "A new distribution centre touches no listed capability.",
                "prospect_relevance": "Company-wide expansion, not her function specifically.",
                "evidence_quality": "Reported with the location and month named.",
                "timeliness": "Opened October 2026, clearly current.",
            },
        ),
    ]
    _finalise(run)
    run.draft = Draft(
        subject="Your expense operations analyst posting",
        finding_id="f-1",
        body=(
            "Hi Hannah,\n\n"
            "I came across Meridian's Expense Operations Analyst posting — it says the "
            "role will \"collect missing receipts from employees and follow up until "
            "each expense report is complete.\"\n\n"
            "Collecting missing employee expense receipts is what we build, so that "
            "line stood out. I'd rather ask than guess — who picks that up today when "
            "a report arrives without its receipts?\n\n"
            "Best,\n[Your name]"
        ),
    )
    run.status = STATUS_AWAITING_REVIEW
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Searching for public evidence on Hannah Weiss at Meridian Outfitters."},
        {"at": "", "stage": "Identity", "message": "2 search(es) run, 4 source(s) cited."},
        {"at": "", "stage": "Identity", "message": "Identity confirmed. " + run.identity.confidence_reason},
        {"at": "", "stage": "Research", "message": "Searching company pages, job postings, announcements and interviews."},
        {"at": "", "stage": "Research", "message": "Verifying 3 finding(s) against their sources."},
        {"at": "", "stage": "Research", "message": "Meridian Outfitters careers site: Quote matched verbatim on the source page."},
        {"at": "", "stage": "Research", "message": "3 of 3 finding(s) verified and usable."},
        {"at": "", "stage": "Signal selection", "message": "Scoring 3 verified finding(s) against the 10-point rubric for Expense receipt tracking."},
        {"at": "", "stage": "Signal selection", "message": "Ranked 2 eligible signal(s); recommending f-1 at 9 of 10. 1 context-only finding(s) below."},
        {"at": "", "stage": "Draft", "message": "Writing a first-contact email from the selected evidence, for Expense receipt tracking."},
        {"at": "", "stage": "Human review", "message": "Draft ready for the salesperson to edit, approve or reject."},
    ]
    return run


# Sample content, written by hand: the runner-up signal is a paraphrase, so this
# draft contains no quotation marks.
_E_ALTERNATE_DRAFTS: dict[str, Draft] = {
    "f-2": Draft(
        subject="The first week of every month at Meridian",
        finding_id="f-2",
        body=(
            "Hi Hannah,\n\n"
            "I read your Retail Finance Review interview, where you described your "
            "team following up with employees about missing expense receipts through "
            "the first week of each month.\n\n"
            "That chase is the thing we build for — collecting missing employee "
            "expense receipts. I won't pretend to know how much of it is manual at "
            "your end, so what does that follow-up look like for your team today?\n\n"
            "Best,\n[Your name]"
        ),
    ),
}


# ---------------------------------------------------------------------------
# A -- strong match for invoice matching
# ---------------------------------------------------------------------------
_A_QUOTE = (
    "You will own three-way matching of supplier invoices against purchase "
    "orders and goods receipt notes, and escalate mismatches to the finance "
    "manager for review."
)

_A_CAPABILITY = "Comparing supplier invoices with purchase orders"


def _fixture_a() -> Run:
    """Strong match for Invoice matching, built so the ranking is readable.

    Three findings: an open AP role that names invoice-to-PO matching (9), the
    prospect's own remark about manual finance work (8), and a funding round
    that scores 5 but is background only because no listed capability connects.
    """
    run = Run(
        prospect_name="Priya Raghavan",
        company="Northwind Logistics",
        role="Head of Finance Operations",
        company_website="https://northwind-logistics.example",
        product=config.product("invoice_matching"),
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
            title="“We spend too long chasing paperwork” — Northwind's finance lead on scaling",
            url="https://freightweekly.example/interviews/northwind-finance-operations",
            domain="freightweekly.example",
            supported_claims=[{
                "text_segment": (
                    "Priya Raghavan said her team is working to reduce manual, "
                    "spreadsheet-driven steps across finance as Northwind grows."
                ),
                "confidence": 0.88,
            }],
        ),
        Source(
            short_id="src-4",
            title="Northwind Logistics raises a 24 million dollar Series B",
            url="https://freightweekly.example/news/northwind-series-b",
            domain="freightweekly.example",
            supported_claims=[{
                "text_segment": "Northwind Logistics raised a 24 million dollar Series B led by Calder Partners.",
                "confidence": 0.9,
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
            finding_id="f-1",
            source_id="src-2",
            kind="job posting",
            quote=_A_QUOTE,
            provenance=PROV_SOURCE_TEXT,
            quote_verified=True,
            verification_note="Quote matched verbatim on the source page.",
        ),
        Finding(
            claim=(
                "In a trade-press interview, Priya Raghavan said her team is working to "
                "reduce manual, spreadsheet-driven steps across finance as the company grows."
            ),
            publisher="Freight Weekly",
            url="https://freightweekly.example/interviews/northwind-finance-operations",
            date="2026-07-09",
            finding_id="f-2",
            source_id="src-3",
            kind="interview",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim=(
                "Northwind Logistics raised a 24 million dollar Series B led by Calder "
                "Partners in October 2026."
            ),
            publisher="Freight Weekly",
            url="https://freightweekly.example/news/northwind-series-b",
            date="2026-10-02",
            finding_id="f-3",
            source_id="src-4",
            kind="news",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
    ]
    run.scores = [
        Score(
            finding_id="f-1",
            product_relevance=3, prospect_relevance=2, evidence_quality=2, timeliness=2,
            capability=_A_CAPABILITY,
            reasons={
                "product_relevance":
                    "Comparing supplier invoices with purchase orders: the posting names "
                    "three-way matching outright.",
                "prospect_relevance": "An AP role inside the finance function she runs.",
                "evidence_quality": "The company's own job posting states the duties.",
                "timeliness": "Posted 28 October 2026 and still open.",
            },
        ),
        Score(
            finding_id="f-2",
            product_relevance=2, prospect_relevance=3, evidence_quality=2, timeliness=1,
            capability=_A_CAPABILITY,
            reasons={
                "product_relevance":
                    "Manual finance steps relate to invoice-to-PO comparison, but the "
                    "exact task is not named.",
                "prospect_relevance": "Her own statement about her own team's priority.",
                "evidence_quality": "A direct quote from the prospect in a trade interview.",
                "timeliness": "Dated July 2026; plausibly still her priority, but not shown.",
            },
        ),
        Score(
            finding_id="f-3",
            product_relevance=0, prospect_relevance=1, evidence_quality=2, timeliness=2,
            reasons={
                "product_relevance":
                    "Funding touches no listed capability of this product.",
                "prospect_relevance": "Company-wide event, not her function specifically.",
                "evidence_quality": "Reported with the lead investor named and confirmed by the company.",
                "timeliness": "Announced October 2026, clearly current.",
            },
        ),
    ]
    _finalise(run)
    run.draft = Draft(
        subject="Your AP analyst posting at Northwind",
        finding_id="f-1",
        body=(
            "Hi Priya,\n\n"
            "I came across Northwind's Accounts Payable Analyst posting — it says the role "
            "will \"own three-way matching of supplier invoices against purchase orders and "
            "goods receipt notes, and escalate mismatches to the finance manager for "
            "review.\"\n\n"
            "Comparing supplier invoices with purchase orders is the piece we build, so "
            "that line caught my eye. How does your team handle the comparison today — is "
            "it one person going line by line?\n\n"
            "Best,\n[Your name]"
        ),
    )
    run.status = STATUS_AWAITING_REVIEW
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Searching for public evidence on Priya Raghavan at Northwind Logistics."},
        {"at": "", "stage": "Identity", "message": "3 search(es) run, 4 source(s) cited."},
        {"at": "", "stage": "Identity", "message": "Identity confirmed. " + run.identity.confidence_reason},
        {"at": "", "stage": "Research", "message": "Searching company pages, job postings, announcements and interviews."},
        {"at": "", "stage": "Research", "message": "Verifying 3 finding(s) against their sources."},
        {"at": "", "stage": "Research", "message": "Northwind Logistics careers site: Quote matched verbatim on the source page."},
        {"at": "", "stage": "Research", "message": "3 of 3 finding(s) verified and usable."},
        {"at": "", "stage": "Signal selection", "message": "Scoring 3 verified finding(s) against the 10-point rubric for Invoice matching."},
        {"at": "", "stage": "Signal selection", "message": "Ranked 2 eligible signal(s); recommending f-1 at 9 of 10. 1 context-only finding(s) below."},
        {"at": "", "stage": "Draft", "message": "Writing a first-contact email from the selected evidence, for Invoice matching."},
        {"at": "", "stage": "Human review", "message": "Draft ready for the salesperson to edit, approve or reject."},
    ]
    return run


# Sample content, written by hand: the runner-up signal is a paraphrase, so this
# draft contains no quotation marks.
_A_ALTERNATE_DRAFTS: dict[str, Draft] = {
    "f-2": Draft(
        subject="The manual steps you mentioned at Northwind",
        finding_id="f-2",
        body=(
            "Hi Priya,\n\n"
            "I read your Freight Weekly interview, where you talked about cutting the "
            "manual, spreadsheet-driven steps in finance as Northwind grows.\n\n"
            "We work on one slice of that: comparing supplier invoices with purchase "
            "orders. I'd rather not guess which steps you meant — which part of the "
            "finance month still runs on spreadsheets today?\n\n"
            "Best,\n[Your name]"
        ),
    ),
}


# ---------------------------------------------------------------------------
# B -- two people with the same name
# ---------------------------------------------------------------------------
def _fixture_b() -> Run:
    run = Run(
        prospect_name="Michael Chen",
        company="Veridian Health",
        role="",
        product=config.product("receipt_tracking"),
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
# C -- no relevant finding (identity fine, evidence off-target)
# ---------------------------------------------------------------------------
def _fixture_c() -> Run:
    """Identity fine, findings verified, nothing usable for this product.

    Every finding scores 0 for product relevance, so all three are background
    only and the run refuses to draft — even though one of them totals 7 of 10.
    """
    run = Run(
        prospect_name="Daniel Okafor",
        company="Lumenbridge Studios",
        role="VP of Engineering",
        product=config.product("invoice_matching"),
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
            finding_id="f-1", source_id="src-2", kind="interview",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim="Lumenbridge Studios won an art direction award for its 2026 title.",
            publisher="Indie Games Press",
            url="https://indiegamespress.example/lumenbridge-art-award", date="2026-08-02",
            finding_id="f-2", source_id="src-3", kind="news",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
        Finding(
            claim="Lumenbridge Studios lists 42 employees on its team page.",
            publisher="Lumenbridge Studios",
            url="https://lumenbridge.example/team", date="",
            finding_id="f-3", source_id="src-1", kind="official page",
            provenance=PROV_SEARCH_SUMMARY,
            verification_note="Claim corroborated by the source page; shown as paraphrase.",
        ),
    ]
    run.scores = [
        Score(
            finding_id="f-1",
            product_relevance=0, prospect_relevance=3, evidence_quality=2, timeliness=2,
            reasons={
                "product_relevance": "Rendering pipelines touch no listed capability.",
                "prospect_relevance": "He gave the talk himself, squarely in his own remit.",
                "evidence_quality": "The conference programme names him and the talk.",
                "timeliness": "June 2026, and the programme is still published.",
            },
        ),
        Score(
            finding_id="f-2",
            product_relevance=0, prospect_relevance=1, evidence_quality=1, timeliness=2,
            reasons={
                "product_relevance": "An art direction award says nothing about finance work.",
                "prospect_relevance": "Company-wide recognition, not his function.",
                "evidence_quality": "Credible trade reporting rather than a direct source.",
                "timeliness": "Awarded August 2026.",
            },
        ),
        Score(
            finding_id="f-3",
            product_relevance=0, prospect_relevance=1, evidence_quality=2, timeliness=0,
            reasons={
                "product_relevance": "Headcount is not a connection to any capability.",
                "prospect_relevance": "Company-wide, and only incidentally about him.",
                "evidence_quality": "The company's own team page.",
                "timeliness": "The page carries no date.",
            },
        ),
    ]
    _finalise(run)
    run.status = STATUS_INSUFFICIENT_EVIDENCE
    run.stop_reason = (
        "Research completed and all three findings were scored for Invoice matching, but "
        "none of them describes a task this product handles, so there is no honest "
        "reason to write about it. The strongest of them — his rendering talk — totals "
        "7 of 10 on the strength of his own involvement and good sourcing, and is still "
        "background only: a high total cannot buy a product connection that the evidence "
        "does not show. A different product may fit this prospect better."
    )
    run.stage_log = [
        {"at": "", "stage": "Identity", "message": "Searching for public evidence on Daniel Okafor at Lumenbridge Studios."},
        {"at": "", "stage": "Identity", "message": "Identity confirmed. " + run.identity.confidence_reason},
        {"at": "", "stage": "Research", "message": "Searching company pages, job postings, announcements and interviews."},
        {"at": "", "stage": "Research", "message": "3 of 3 finding(s) verified and usable."},
        {"at": "", "stage": "Signal selection", "message": "Scoring 3 verified finding(s) against the 10-point rubric for Invoice matching."},
        {"at": "", "stage": "Signal selection", "message": "No eligible signal after scoring. Stopping with 'Insufficient evidence'."},
    ]
    return run


# ---------------------------------------------------------------------------
# D -- research interrupted (distinct from 'no strong signal found')
# ---------------------------------------------------------------------------
def _fixture_d() -> Run:
    run = Run(
        prospect_name="Alina Moreau",
        company="Castellan Foods",
        role="Finance Director",
        product=config.product("vendor_onboarding"),
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


_ALTERNATE_DRAFTS: dict[str, dict[str, Draft]] = {
    "A": _A_ALTERNATE_DRAFTS,
    "E": _E_ALTERNATE_DRAFTS,
}


def alternate_draft(fixture_id: str, finding_id: str) -> Draft | None:
    """A stored draft for one of a scenario's other signals, or None.

    This is what makes "Use this signal" work with no API key: a sample run
    takes the stored draft instead of calling the model. It is sample content,
    written by hand, and labelled as such in the interface.
    """
    base = (fixture_id or "").split()[0].upper() if fixture_id else ""
    store = _ALTERNATE_DRAFTS.get(base)
    if store is None:
        return None
    if finding_id == "f-1":
        # The draft the run opens with, rebuilt rather than cached, so
        # switching back during a demo returns the identical email.
        return Draft.from_dict(build(base).draft.to_dict())
    stored = store.get(finding_id)
    return Draft.from_dict(stored.to_dict()) if stored else None


FIXTURES: dict[str, dict[str, object]] = {
    "E": {
        "label": "Strong match · Expense receipt tracking",
        "product": "Expense receipt tracking",
        "summary": "Hannah Weiss at Meridian Outfitters. An open expense role that names "
                   "receipt chasing scores 9 of 10, her own interview 8, and a new "
                   "distribution centre 5 — background only. Switching to the runner-up "
                   "works with no API key.",
        "expected": "Awaiting review",
        "build": _fixture_e,
    },
    "A": {
        "label": "Strong match · Invoice matching",
        "product": "Invoice matching",
        "summary": "Priya Raghavan at Northwind Logistics. A verified AP posting scores 9 of "
                   "10, her own interview 8, and a funding round 5 — background only. "
                   "Switching to the runner-up works with no API key.",
        "expected": "Awaiting review",
        "build": _fixture_a,
    },
    "B": {
        "label": "Two people with the same name",
        "product": "Expense receipt tracking",
        "summary": "Michael Chen at Veridian Health. Two people share the name and the "
                   "company's own pages disagree about whether he still works there, so the "
                   "run pauses before any research spend.",
        "expected": "Needs clarification",
        "build": _fixture_b,
    },
    "C": {
        "label": "No relevant finding",
        "product": "Invoice matching",
        "summary": "Daniel Okafor at Lumenbridge Studios. All three findings are verified and "
                   "scored — the best reaching 7 of 10 — but none describes a task this "
                   "product handles, so the run refuses to draft.",
        "expected": "Insufficient evidence",
        "build": _fixture_c,
    },
    "D": {
        "label": "Research interrupted",
        "product": "Vendor onboarding",
        "summary": "Alina Moreau at Castellan Foods. The search backend errors mid-run, "
                   "recorded as a retryable failure rather than a conclusion about the "
                   "prospect.",
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
    """Rebuild a sample run, replaying its stage log so the UI animates."""
    final = build(fixture_id)
    log = list(final.stage_log)

    live = Run.from_dict(final.to_dict())
    live.stage_log = []
    live.status = "Running"
    live.findings = []
    live.sources = []
    live.checks = []
    live.draft = Draft()
    live.scores = []
    live.ranking = []
    live.recommended_id = ""
    live.active_id = ""
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
            # The ranking appears when the stage that produced it completes.
            if "Ranked" in entry["message"] or "Stopping" in entry["message"]:
                live.scores = final.scores
                live.ranking = final.ranking
                live.recommended_id = final.recommended_id
                live.active_id = final.active_id
                live.checks = final.checks
                live.selected_index = final.selected_index
                live.selection_reason = final.selection_reason
        elif entry["stage"] in ("Draft", "Human review"):
            live.sources, live.findings = final.sources, final.findings
            live.scores, live.ranking = final.scores, final.ranking
            live.recommended_id, live.active_id = final.recommended_id, final.active_id
            live.checks, live.selected_index = final.checks, final.selected_index
        if on_stage:
            on_stage(live)
        time.sleep(step_delay)

    return final
