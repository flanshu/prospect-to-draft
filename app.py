"""Personalised outreach — from prospect to draft.

Streamlit front end. Two views: "Research a prospect" and "Past runs".

Written for a salesperson who knows their customers and has never heard the
words "fixture", "grounding" or "eligibility". The screen answers four
questions in order: who did we research, what did we find, why does it matter
for the product you picked, and what do you want to do about it. Internal
status values, stage names and score keys are unchanged — only what is shown
has been put into plain words, so storage, tests and the pipeline keep working.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from outreach import config, fixtures, verify
from outreach.pipeline import SignalNotEligible, execute, redraft, why_it_matters
from outreach.schema import (
    CONTEXT_ONLY,
    ELIGIBLE,
    EXCLUDED,
    PROV_MODEL,
    PROV_SEARCH_SUMMARY,
    PROV_SOURCE_TEXT,
    SCORE_MAX,
    STAGES,
    STATUS_APPROVED,
    STATUS_AWAITING_REVIEW,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_REJECTED,
    STATUS_RESEARCH_INCOMPLETE,
    STATUS_RUNNING,
    Run,
)
from outreach.store import Store

st.set_page_config(
    page_title="Personalised outreach — prospect to draft",
    page_icon="✉️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Display labels. The values on the left are what the code, the tests and the
# database use; the strings on the right are the only thing a salesperson sees.
# ---------------------------------------------------------------------------
STATUS_LABEL = {
    STATUS_RUNNING: "Working…",
    STATUS_NEEDS_CLARIFICATION: "Confirm who you mean",
    STATUS_INSUFFICIENT_EVIDENCE: "No strong signal found",
    STATUS_RESEARCH_INCOMPLETE: "Research interrupted",
    STATUS_AWAITING_REVIEW: "Needs your review",
    STATUS_APPROVED: "Approved",
    STATUS_REJECTED: "Rejected",
}

STATUS_TONE = {
    STATUS_RUNNING: "running",
    STATUS_NEEDS_CLARIFICATION: "attention",
    STATUS_INSUFFICIENT_EVIDENCE: "stopped",
    STATUS_RESEARCH_INCOMPLETE: "attention",
    STATUS_AWAITING_REVIEW: "review",
    STATUS_APPROVED: "good",
    STATUS_REJECTED: "stopped",
}

# The stage strip, in the words of the job rather than the code.
STAGE_LABEL = {
    "Identity": "Confirming identity",
    "Research": "Finding sources",
    "Signal selection": "Comparing signals",
    "Draft": "Preparing draft",
    "Human review": "Your review",
}

ELIGIBILITY_LABEL = {
    ELIGIBLE: ("Can use in draft", "good"),
    CONTEXT_ONLY: ("Background only", "attention"),
    EXCLUDED: ("Can't be used", "stopped"),
}

# Rubric components, in plain words. The keys stay as stored.
COMPONENT_LABEL = {
    "product_relevance": "Product fit",
    "prospect_relevance": "Relevant to their role",
    "evidence_quality": "Source quality",
    "timeliness": "Timing",
}

PROV_LABEL = {
    PROV_SOURCE_TEXT: (
        "Verified quote",
        "We opened the source page and matched this wording exactly, so it can be quoted.",
    ),
    PROV_SEARCH_SUMMARY: (
        "Summary of the source",
        "A source backs this, but we did not match its exact wording — so it is a "
        "summary and the email will not quote it.",
    ),
    PROV_MODEL: (
        "Not verified",
        "No source backs this, so it is left out of the email entirely.",
    ),
}

CSS = """
<style>
:root {
  --accent: #2563EB;
  --ink: #111827;
  --ink-soft: #566074;
  --ink-faint: #8A93A5;
  --line: #E3E7ED;
  --surface: #FFFFFF;
  --surface-soft: #F5F7FA;
}

.block-container { padding-top: 2.1rem; max-width: 1340px; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }

/* ---- result header ---- */
.prospect-head {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: .5rem .8rem;
  margin: 0 0 .2rem 0;
}
.prospect-name { font-size: 1.55rem; font-weight: 650; color: var(--ink); line-height: 1.2; }
.prospect-meta { font-size: 1rem; color: var(--ink-soft); }
.run-meta { font-size: .8rem; color: var(--ink-faint); margin-bottom: 1rem; }

/* ---- status pills: always carry a text label, never colour alone ---- */
.pill {
  display: inline-block; padding: .17rem .6rem; border-radius: 999px;
  font-size: .78rem; font-weight: 600; letter-spacing: .01em; white-space: nowrap;
  border: 1px solid transparent;
}
.pill.good      { background: #E8F3EC; color: #1C6B3C; border-color: #BFE0CB; }
.pill.review    { background: #EAF0FE; color: #1D4ED8; border-color: #C6D6FB; }
.pill.attention { background: #FDF3E2; color: #8A5A08; border-color: #F0DCB4; }
.pill.stopped   { background: #FBEBEB; color: #9B2C2C; border-color: #F0CFCF; }
.pill.running   { background: #EEF0F4; color: #44506A; border-color: #D9DEE7; }
.pill.mode      { background: var(--surface-soft); color: var(--ink-soft); border-color: var(--line); font-weight: 500; }
.pill.product   { background: #F2F6FF; color: #1D4ED8; border-color: #D6E2FD; }

/* ---- progress strip ---- */
.stages { display: flex; gap: .4rem; flex-wrap: wrap; margin: .2rem 0 .5rem; }
.stage {
  flex: 1 1 0; min-width: 132px; padding: .45rem .65rem;
  border: 1px solid var(--line); border-radius: 8px; background: var(--surface);
  font-size: .82rem; color: var(--ink-faint);
}
.stage .n { font-weight: 700; margin-right: .35rem; }
.stage.done { color: var(--ink-soft); background: var(--surface-soft); }
.stage.now  { color: var(--accent); border-color: var(--accent); background: #F3F7FF; font-weight: 600; }
.stage-note { font-size: .82rem; color: var(--ink-soft); margin: .1rem 0 .3rem; }

/* ---- cards ---- */
.card {
  border: 1px solid var(--line); border-radius: 12px; background: var(--surface);
  padding: 1.05rem 1.15rem; margin-bottom: .85rem;
}
.card-label {
  font-size: .73rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  color: var(--ink-faint); margin-bottom: .5rem;
}
/* The finding itself is the most prominent text on the page. */
.signal-claim {
  font-size: 1.18rem; line-height: 1.45; color: var(--ink); font-weight: 550;
  overflow-wrap: anywhere;
}
.source-line { font-size: .86rem; color: var(--ink-soft); margin-top: .65rem; overflow-wrap: anywhere; }
.source-line a { color: var(--accent); text-decoration: none; }
.source-line a:hover { text-decoration: underline; }
.excerpt {
  border-left: 3px solid var(--accent); background: var(--surface-soft);
  padding: .55rem .75rem; margin: .7rem 0 .2rem; border-radius: 0 6px 6px 0;
  font-size: .9rem; color: var(--ink); line-height: 1.5; overflow-wrap: anywhere;
}
.excerpt .tag { display: block; font-size: .72rem; color: var(--ink-faint); margin-top: .35rem; }
.why {
  font-size: .93rem; color: var(--ink-soft); line-height: 1.55; margin-top: .7rem;
  overflow-wrap: anywhere;
}
.why strong { color: var(--ink); }

/* ---- signal strength ---- */
.strength {
  display: inline-flex; align-items: baseline; gap: .35rem;
  font-size: .82rem; color: var(--ink-soft); font-weight: 600;
}
.strength .v { font-size: 1.1rem; font-weight: 700; color: var(--ink); }
.strength.sm .v { font-size: .98rem; }
.rank {
  font-size: .82rem; font-weight: 700; color: var(--accent);
  background: #EEF3FF; border: 1px solid #C6D6FB; border-radius: 6px; padding: .1rem .4rem;
}
.rank-claim { font-size: 1rem; line-height: 1.5; color: var(--ink); font-weight: 500; overflow-wrap: anywhere; }
.card-head { display: flex; align-items: center; flex-wrap: wrap; gap: .4rem .6rem; margin-bottom: .55rem; }

/* ---- score chips ---- */
.comps { display: flex; flex-wrap: wrap; gap: .35rem; margin: .65rem 0 .15rem; }
.comp {
  border: 1px solid var(--line); border-radius: 7px; background: var(--surface-soft);
  padding: .22rem .5rem; font-size: .78rem; color: var(--ink-soft);
  display: flex; align-items: baseline; gap: .35rem;
}
.comp .cv { font-weight: 700; color: var(--ink); }
.comp .cm { font-weight: 600; color: var(--ink-faint); font-size: .72rem; }
.comp-why { font-size: .86rem; color: var(--ink-soft); line-height: 1.5; margin: .3rem 0; }
.comp-why .n { font-weight: 650; color: var(--ink); }
.draft-from { font-size: .82rem; color: var(--ink-faint); margin: .1rem 0 .5rem; overflow-wrap: anywhere; }

/* ---- the old pass/fail checks, kept for runs saved before scoring ---- */
.checks { display: grid; grid-template-columns: 1fr 1fr; gap: .45rem; margin-top: .3rem; }
.check { border: 1px solid var(--line); border-radius: 9px; padding: .5rem .65rem; background: var(--surface); }
.check .top { display: flex; align-items: center; justify-content: space-between; gap: .4rem; }
.check .nm { font-size: .84rem; font-weight: 650; color: var(--ink); }
.check .vd { font-size: .71rem; font-weight: 700; padding: .08rem .42rem; border-radius: 999px; }
.check.met .vd    { background: #E8F3EC; color: #1C6B3C; }
.check.unmet .vd  { background: #FBEBEB; color: #9B2C2C; }
.check.unmet      { border-color: #F0CFCF; background: #FEFAFA; }
.check .rs { font-size: .79rem; color: var(--ink-soft); line-height: 1.45; margin-top: .25rem; }

/* ---- what happened / what to do next ---- */
.exception { border-radius: 12px; padding: 1rem 1.15rem; margin-bottom: .85rem; border: 1px solid; }
.exception.attention { background: #FFFBF3; border-color: #F0DCB4; }
.exception.stopped   { background: #FEF7F7; border-color: #F0CFCF; }
.exception h4 { margin: 0 0 .4rem; font-size: 1.05rem; color: var(--ink); }
.exception p  { margin: 0 0 .45rem; font-size: .93rem; color: var(--ink-soft); line-height: 1.55; }
.exception .next { font-size: .93rem; color: var(--ink); font-weight: 550; }
.candidate {
  border: 1px solid var(--line); border-radius: 9px; background: var(--surface);
  padding: .55rem .7rem; margin-bottom: .4rem; font-size: .87rem; color: var(--ink);
}
.candidate .why { font-size: .81rem; margin-top: .2rem; }
.candidate a { color: var(--accent); font-size: .81rem; text-decoration: none; }

/* ---- other findings, for runs saved before scoring ---- */
.alt { border-top: 1px solid var(--line); padding: .6rem 0 .1rem; font-size: .88rem; }
.alt:first-child { border-top: none; }
.alt .cl { color: var(--ink); line-height: 1.45; overflow-wrap: anywhere; }
.alt .mt { font-size: .78rem; color: var(--ink-faint); margin-top: .22rem; overflow-wrap: anywhere; }
.alt .mt a { color: var(--accent); text-decoration: none; }

/* One accent colour, used for the primary action only. */
.stButton > button { border-radius: 8px; font-weight: 600; }

/* ---- the product chosen on the form ---- */
.product-note {
  border: 1px solid #D6E2FD; background: #F6F9FF; border-radius: 10px;
  padding: .6rem .8rem; margin: -.4rem 0 .9rem;
  font-size: .89rem; color: var(--ink-soft); line-height: 1.5;
}
.product-note strong { color: var(--ink); }

/* ---- past runs ---- */
.hist-head {
  font-size: .73rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: var(--ink-faint); padding-bottom: .25rem;
}
.hist-cell { font-size: .87rem; color: var(--ink); line-height: 1.45; padding-top: .45rem; overflow-wrap: anywhere; }
.hist-sub  { font-size: .76rem; color: var(--ink-faint); margin-top: .15rem; overflow-wrap: anywhere; }
.hist-rule { border-top: 1px solid var(--line); margin: .3rem 0 .55rem; }

/* Narrow screens: evidence stacks above the draft, controls stay usable. */
@media (max-width: 900px) {
  [data-testid="stHorizontalBlock"] { flex-direction: column; }
  [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; }
  .checks { grid-template-columns: 1fr; }
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .prospect-name { font-size: 1.35rem; }
}
</style>
"""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def pill(label: str, tone: str) -> str:
    return f'<span class="pill {tone}">{escape(label)}</span>'


def status_pill(status: str) -> str:
    return pill(STATUS_LABEL.get(status, status), STATUS_TONE.get(status, "running"))


def mode_pill(run: Run) -> str:
    if run.mode == "fixture":
        return pill("Sample data · no live search", "mode")
    return pill("Live research", "mode")


def product_pill(run: Run) -> str:
    label = run.product.name
    if run.product.legacy:
        label += " (before product choice)"
    return pill(label, "product")


def strength(total: int, *, small: bool = False) -> str:
    cls = "strength sm" if small else "strength"
    return (
        f'<span class="{cls}">Signal strength'
        f'<span class="v">{total}/{SCORE_MAX}</span></span>'
    )


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def _shorten(text: str, limit: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# State — survives Streamlit reruns
# ---------------------------------------------------------------------------
@st.cache_resource
def get_store() -> Store:
    return Store()


def set_active(run: Run | None) -> None:
    st.session_state["active_run"] = run.to_dict() if run else None


def get_active() -> Run | None:
    payload = st.session_state.get("active_run")
    return Run.from_dict(payload) if payload else None


def persist(run: Run) -> None:
    """Upsert by run_id, so re-saving a run never creates a duplicate."""
    try:
        get_store().save(run)
    except Exception as exc:
        st.warning(
            "This run could not be saved to your past runs. Everything on screen is "
            "still correct — see Technical details for the reason."
        )
        st.session_state["save_error"] = f"{type(exc).__name__}: {exc}"
    set_active(run)


def selected_product_id() -> str:
    return st.session_state.get("product_id", config.DEFAULT_PRODUCT_ID)


# ---------------------------------------------------------------------------
# Header and progress
# ---------------------------------------------------------------------------
def render_prospect_head(run: Run) -> None:
    bits = [f'<span class="prospect-name">{escape(run.prospect_name)}</span>']
    meta = " · ".join(x for x in (run.role, run.company) if x)
    if meta:
        bits.append(f'<span class="prospect-meta">{escape(meta)}</span>')
    bits.append(product_pill(run))
    bits.append(mode_pill(run))
    bits.append(status_pill(run.status))
    html(f'<div class="prospect-head">{"".join(bits)}</div>')
    html(
        f'<div class="run-meta">Researched for <strong>{escape(run.product.name)}</strong>'
        f' · started {escape(run.created_at[:16].replace("T", " "))} UTC</div>'
    )


def render_progress(run: Run, slot=None) -> None:
    """What the app is doing, in the words of the job."""
    reached = {e["stage"] for e in run.stage_log}
    running = run.status == STATUS_RUNNING
    cells = []
    for i, stage in enumerate(STAGES, start=1):
        if running and stage == run.stage:
            cls = "now"
        elif stage in reached:
            cls = "done"
        else:
            cls = ""
        label = STAGE_LABEL.get(stage, stage)
        cells.append(f'<div class="stage {cls}"><span class="n">{i}</span>{escape(label)}</div>')
    note = run.stage_log[-1]["message"] if run.stage_log else "Starting…"
    markup = (
        f'<div class="stages">{"".join(cells)}</div>'
        f'<div class="stage-note">{escape(note)}</div>'
    )
    if slot is not None:
        with slot.container():
            render_prospect_head(run)
            html(markup)
    else:
        html(markup)


# ---------------------------------------------------------------------------
# Running a workflow
# ---------------------------------------------------------------------------
def run_live(run: Run, *, skip_identity: bool = False) -> Run:
    slot = st.empty()
    with st.spinner("Researching — searching the web now…"):
        result = execute(run, lambda r: render_progress(r, slot), skip_identity=skip_identity)
    render_progress(result, slot)
    persist(result)
    return result


def run_fixture(fixture_id: str) -> Run:
    st.info(
        "Sample scenario — nothing was searched and no email was written just now. "
        "The people, companies and links are invented, so this shows you how the "
        "screen works without spending a search.",
        icon="🧪",
    )
    slot = st.empty()
    with st.spinner("Replaying the sample scenario…"):
        result = fixtures.replay(fixture_id, lambda r: render_progress(r, slot))
    render_progress(result, slot)
    persist(result)
    return result


# ---------------------------------------------------------------------------
# LEFT COLUMN — what we found, and why it matters for this product
# ---------------------------------------------------------------------------
def source_line(finding) -> str:
    """Publisher · date · clickable source · whether it can be quoted."""
    label, _ = PROV_LABEL.get(finding.provenance, ("Unknown", ""))
    name = finding.publisher or verify.publisher_from_url(finding.url, "source")
    bits = [f'<a href="{escape(finding.url)}" target="_blank">{escape(name)}</a>']
    if finding.date:
        bits.append(escape(finding.date))
    bits.append(escape(label))
    return f'<div class="source-line">{" · ".join(bits)}</div>'


def excerpt_block(finding) -> str:
    if finding.quote_verified and finding.quote:
        return (
            f'<div class="excerpt">“{escape(finding.quote)}”'
            '<span class="tag">We matched this wording on the source page, so the email '
            "may quote it.</span></div>"
        )
    _, tooltip = PROV_LABEL.get(finding.provenance, ("Unknown", ""))
    return (
        '<div class="excerpt" style="border-left-color:#C8CEDA">'
        f'<span class="tag" style="margin-top:0">No quotable wording — {escape(tooltip)}'
        "</span></div>"
    )


def render_score_chips(score) -> None:
    chips = "".join(
        f'<div class="comp"><span class="cl">{escape(COMPONENT_LABEL.get(key, label))}</span>'
        f'<span class="cv">{value}<span class="cm">/{maximum}</span></span></div>'
        for key, label, value, maximum, _ in score.components()
    )
    html(f'<div class="comps">{chips}</div>')


def render_score_detail(score, *, expanded: bool = False) -> None:
    """The four parts of the score, with the reason the model gave for each."""
    with st.expander("How this was scored", expanded=expanded):
        rows = "".join(
            f'<div class="comp-why"><span class="n">'
            f"{escape(COMPONENT_LABEL.get(k, label))} {value} of {maximum}</span> — "
            f"{escape(reason or 'no reason given')}</div>"
            for k, label, value, maximum, reason in score.components()
        )
        html(f"<div>{rows}</div>")
        if score.capability:
            st.caption(f"Connects to: {score.capability}")
        st.caption(
            f"{score.total} out of {SCORE_MAX} describes how strong this is as a reason "
            "to make contact. It is not a prediction that they will buy, and it never "
            "overrides an unconfirmed identity or a claim no source supports."
        )


def render_selected_signal(run: Run) -> None:
    """The finding the email is written from, in full."""
    finding = run.selected_finding()
    if finding is None:
        return
    score = run.score_for(finding.finding_id)
    rank = next(
        (r for r, f, _ in run.ranked_findings(ELIGIBLE) if f.finding_id == finding.finding_id),
        0,
    )

    heads = ['<div class="card-label" style="margin:0">What we found</div>']
    if score is not None:
        heads.append(strength(score.total))
    if rank:
        heads.append(pill(f"Ranked #{rank}", "mode"))
    if run.recommended_id == finding.finding_id:
        heads.append(pill("Our pick", "review"))
    elif run.recommendation_was_overridden():
        heads.append(pill("Your pick", "attention"))

    reason = why_it_matters(run, score) if score is not None else ""
    html(
        '<div class="card">'
        f'<div class="card-head">{"".join(heads)}</div>'
        f'<div class="signal-claim">{escape(finding.claim)}</div>'
        f"{source_line(finding)}{excerpt_block(finding)}"
        + (
            '<div class="why"><strong>Why this matters for '
            f"{escape(run.product.name)}:</strong> {escape(reason)}</div>"
            if reason else ""
        )
        + (
            '<div class="why"><strong>Why it came first:</strong> '
            f"{escape(run.selection_reason)}</div>"
            if run.selection_reason and run.recommended_id == finding.finding_id
            else ""
        )
        + "</div>"
    )

    if score is not None:
        render_score_chips(score)
        render_score_detail(score)

    if run.recommendation_was_overridden():
        rec = run.finding_by_id(run.recommended_id)
        rec_score = run.score_for(run.recommended_id)
        rec_rank = next(
            (r for r, f, _ in run.ranked_findings(ELIGIBLE)
             if f.finding_id == run.recommended_id),
            0,
        )
        if rec is not None:
            st.caption(
                f"You chose this one. Our pick was #{rec_rank or 1} — "
                f"“{_shorten(rec.claim, 90)}”"
                + (f" ({rec_score.total}/{SCORE_MAX})" if rec_score else "")
                + ". Both are saved on this run."
            )


def render_other_signals(run: Run, *, allow_switch: bool = False) -> None:
    """Everything else we found, ranked, with the option to use one instead."""
    entries = run.ranked_findings()
    if not entries:
        return
    usable = sum(1 for _, _, s in entries if s.eligibility == ELIGIBLE)
    html(
        '<div class="card-label" style="margin:1rem 0 .4rem">'
        f"Other signals we found · {usable} of {len(entries)} can be used in a draft</div>"
    )

    for rank, finding, score in entries:
        label, tone = ELIGIBILITY_LABEL.get(score.eligibility, ("Scored", "mode"))
        is_active = finding.finding_id == run.active_id
        with st.container(border=True):
            head = [
                f'<span class="rank">{"#" + str(rank) if rank else "—"}</span>',
                strength(score.total, small=True),
                pill(label, tone),
            ]
            if finding.finding_id == run.recommended_id:
                head.append(pill("Our pick", "review"))
            if is_active:
                head.append(pill("In the draft now", "good"))
            html(
                f'<div class="card-head">{"".join(head)}</div>'
                f'<div class="rank-claim">{escape(finding.claim)}</div>'
                f"{source_line(finding)}"
            )
            if score.eligibility != ELIGIBLE and score.eligibility_reason:
                st.caption(score.eligibility_reason)
            if (
                finding.finding_id == run.recommended_id
                and run.selection_reason
                and not is_active
            ):
                html(
                    '<div class="why"><strong>Why we put this first:</strong> '
                    f"{escape(run.selection_reason)}</div>"
                )
            render_score_chips(score)
            render_score_detail(score, expanded=False)
            if finding.quote_verified and finding.quote and not is_active:
                html(excerpt_block(finding))
            if allow_switch and score.eligibility == ELIGIBLE and not is_active:
                if st.button(
                    "Use this signal",
                    key=f"use_{run.run_id}_{finding.finding_id}",
                    width="stretch",
                    help="Rewrites the email from this finding. Nothing is searched again.",
                ):
                    request_switch(run, finding.finding_id)


def render_legacy_signal(run: Run) -> None:
    """A run saved before signals were scored: shown exactly as it was stored."""
    finding = run.selected_finding()
    if finding is None:
        return
    html(
        '<div class="card">'
        '<div class="card-label">What we found</div>'
        f'<div class="signal-claim">{escape(finding.claim)}</div>'
        f"{source_line(finding)}{excerpt_block(finding)}"
        + (
            f'<div class="why"><strong>Why this matters:</strong> '
            f"{escape(run.selection_reason)}</div>"
            if run.selection_reason
            else ""
        )
        + "</div>"
    )
    st.caption(
        "This run is older than signal scoring, so it has no strength score and no "
        "alternatives to switch to. Nothing has been scored after the fact — the "
        "finding and the email are exactly as they were saved, for "
        f"{run.product.name}."
    )
    render_checks(run)
    render_other_findings(run)


def render_evidence_panel(run: Run, *, allow_switch: bool = False) -> None:
    """Left column: the finding in the draft, then everything else we found."""
    if not run.has_ranking():
        render_legacy_signal(run)
        return
    render_selected_signal(run)
    render_other_signals(run, allow_switch=allow_switch)


def render_checks(run: Run) -> None:
    """Pass/fail view, kept for runs saved before signals were scored."""
    if not run.checks:
        return
    met, total = run.checks_met()
    cells = []
    for c in run.checks:
        cls = "met" if c.passed else "unmet"
        verdict = "Yes" if c.passed else "No"
        cells.append(
            f'<div class="check {cls}"><div class="top"><span class="nm">{escape(c.name)}</span>'
            f'<span class="vd">{verdict}</span></div>'
            f'<div class="rs">{escape(c.reason)}</div></div>'
        )
    html(
        '<div class="card">'
        '<div class="card-label">What we checked</div>'
        f'<div class="checks">{"".join(cells)}</div>'
        "</div>"
    )


def render_other_findings(run: Run) -> None:
    """Other findings, for runs with no scores."""
    others = [(i, f) for i, f in enumerate(run.findings) if i != run.selected_index]
    if not others:
        return
    with st.expander(f"Other things we found ({len(others)})"):
        for _, f in others:
            label, _ = PROV_LABEL.get(f.provenance, ("Unknown", ""))
            excluded = "" if verify.is_usable(f) else " · left out of the email"
            source_name = f.publisher or verify.publisher_from_url(f.url, "source")
            date = f" · {escape(f.date)}" if f.date else ""
            html(
                f'<div class="alt"><div class="cl">{escape(f.claim)}</div>'
                f'<div class="mt"><a href="{escape(f.url)}" target="_blank">{escape(source_name)}</a>'
                f'{date} · {escape(label)}{excluded}</div></div>'
            )


# ---------------------------------------------------------------------------
# Switching the signal the draft uses
# ---------------------------------------------------------------------------
def draft_keys(run: Run) -> tuple[str, str]:
    """Editor keys, revised whenever the draft is replaced.

    Streamlit keeps a widget's value against its key, so re-rendering the same
    key after a switch would show the previous signal's email next to the new
    signal's evidence. Bumping the revision gives the new draft its own boxes.
    """
    rev = st.session_state.get(f"draft_rev_{run.run_id}", 0)
    return f"subj_{run.run_id}_{rev}", f"body_{run.run_id}_{rev}"


def _has_unsaved_edits(run: Run) -> bool:
    subj_key, body_key = draft_keys(run)
    subject = st.session_state.get(subj_key)
    body = st.session_state.get(body_key)
    if subject is None and body is None:
        return False
    return (
        (subject is not None and subject != run.draft.final_subject())
        or (body is not None and body != run.draft.final_body())
    )


def request_switch(run: Run, finding_id: str) -> None:
    """Ask to switch signals, checking first if edits would be lost."""
    if _has_unsaved_edits(run):
        subj_key, body_key = draft_keys(run)
        # Hold the unsaved text while we ask, so no path through the question
        # can lose it -- including the one where the switch itself fails.
        st.session_state["pending_switch"] = finding_id
        st.session_state["pending_edits"] = (
            st.session_state.get(subj_key, run.draft.final_subject()),
            st.session_state.get(body_key, run.draft.final_body()),
        )
        st.rerun()
    do_switch(run, finding_id)


def _restore_pending_edits(run: Run) -> None:
    held = st.session_state.pop("pending_edits", None)
    if not held:
        return
    subj_key, body_key = draft_keys(run)
    st.session_state[subj_key], st.session_state[body_key] = held


def do_switch(run: Run, finding_id: str) -> None:
    """Rewrite the email from another finding. Nothing searched, same run."""
    st.session_state.pop("pending_switch", None)
    draft_fn = None
    if run.mode == "fixture":
        canned = fixtures.alternate_draft(run.fixture_id, finding_id)
        if canned is None:
            st.error(
                "This sample scenario has no saved email for that signal, and writing "
                "one would need a live model call."
            )
            _restore_pending_edits(run)
            return
        draft_fn = lambda _run, _finding: canned  # noqa: E731 - sample data, not the model
    elif not config.credentials_available():
        st.error(
            "Rewriting the email needs live research to be set up. Your research and "
            "scores are untouched, and the current email has been kept."
        )
        _restore_pending_edits(run)
        return

    try:
        with st.spinner("Rewriting the email from that signal…"):
            redraft(run, finding_id, draft_fn=draft_fn)
    except SignalNotEligible as exc:
        st.error(str(exc))
        _restore_pending_edits(run)
        return
    except Exception as exc:
        st.session_state["switch_error"] = f"{type(exc).__name__}: {exc}"
        st.error(
            "We could not rewrite the email, so your previous one has been kept with "
            "the signal it was written from. Try again, or keep the email you have."
        )
        persist(run)
        _restore_pending_edits(run)
        return

    # The reviewer chose to replace their edits, so drop the held text.
    st.session_state.pop("pending_edits", None)
    st.session_state[f"draft_rev_{run.run_id}"] = (
        st.session_state.get(f"draft_rev_{run.run_id}", 0) + 1
    )
    persist(run)
    st.toast("Email rewritten from that signal. It needs your approval again.")
    st.rerun()


def render_pending_switch(run: Run) -> None:
    """Check before replacing edits the reviewer has not saved."""
    finding_id = st.session_state.get("pending_switch")
    if not finding_id:
        return
    finding = run.finding_by_id(finding_id)
    st.warning(
        "You have changes you haven't saved. Switching to "
        f"“{_shorten(finding.claim, 80) if finding else finding_id}” will replace them "
        "with a newly written email.",
        icon="✏️",
    )
    c1, c2, c3 = st.columns([1.2, 1, 1])
    if c1.button("Replace my changes", key=f"sw_yes_{run.run_id}", type="primary", width="stretch"):
        do_switch(run, finding_id)
    if c2.button("Keep my changes", key=f"sw_no_{run.run_id}", width="stretch"):
        st.session_state.pop("pending_switch", None)
        _restore_pending_edits(run)
        st.rerun()
    if c3.button("Save, then switch", key=f"sw_save_{run.run_id}", width="stretch"):
        subj_key, body_key = draft_keys(run)
        held = st.session_state.get("pending_edits") or (
            st.session_state.get(subj_key, run.draft.final_subject()),
            st.session_state.get(body_key, run.draft.final_body()),
        )
        run.draft.edited_subject, run.draft.edited_body = held
        run.log("Human review", "Salesperson saved edits before switching signal.")
        persist(run)
        st.session_state.pop("pending_switch", None)
        _restore_pending_edits(run)
        st.rerun()


# ---------------------------------------------------------------------------
# RIGHT COLUMN — the email
# ---------------------------------------------------------------------------
def render_draft_panel(run: Run, *, allow_review: bool) -> None:
    editable = allow_review and run.status == STATUS_AWAITING_REVIEW
    html('<div class="card-label" style="margin-bottom:.35rem">Your email</div>')

    written_from = run.draft.finding_id or run.active_id
    finding = run.finding_by_id(written_from)
    if finding is not None:
        score = run.score_for(written_from)
        rank = next(
            (r for r, f, _ in run.ranked_findings(ELIGIBLE) if f.finding_id == written_from),
            0,
        )
        bits = [f"signal {'#' + str(rank) if rank else written_from}"]
        if score is not None:
            bits.append(f"{score.total}/{SCORE_MAX}")
        html(
            f'<div class="draft-from">Written from {escape(" · ".join(bits))} — '
            f"{escape(_shorten(finding.claim, 95))}</div>"
        )

    render_pending_switch(run)

    subj_key, body_key = draft_keys(run)
    # When held text has been put back into these keys, Streamlit owns the
    # value and passing a default as well only earns a warning.
    subj_kwargs = {} if subj_key in st.session_state else {"value": run.draft.final_subject()}
    body_kwargs = {} if body_key in st.session_state else {"value": run.draft.final_body()}
    subject = st.text_input("Subject", key=subj_key, disabled=not editable, **subj_kwargs)
    body = st.text_area(
        "Email", height=330, key=body_key, disabled=not editable, **body_kwargs,
    )

    if editable:
        c1, c2, c3 = st.columns([1.1, 1, 1])
        if c1.button("Approve draft", key=f"appr_{run.run_id}", type="primary", width="stretch"):
            _decide(run, STATUS_APPROVED, subject, body)
        if c2.button("Save edits", key=f"save_{run.run_id}", width="stretch"):
            run.draft.edited_subject = subject
            run.draft.edited_body = body
            run.log("Human review", "Salesperson saved edits to the draft.")
            persist(run)
            st.toast("Your changes are saved. The draft still needs your approval.")
            st.rerun()
        if c3.button("Reject draft", key=f"rej_{run.run_id}", width="stretch"):
            _decide(run, STATUS_REJECTED, subject, body)
        st.caption(
            "Nothing is sent from here. Approving, saving or switching signal never "
            "searches again and never starts a second run."
        )
    elif run.draft.decision:
        tone = "good" if run.draft.decision == "approved" else "stopped"
        word = "Approved" if run.draft.decision == "approved" else "Rejected"
        html(
            f'<div style="margin-top:.4rem">{pill(word + " and saved", tone)}'
            f'<span style="font-size:.82rem;color:var(--ink-faint);margin-left:.5rem">'
            f'{escape(run.draft.decided_at.replace("T", " ")[:19])} UTC · this is the '
            f"version that was saved</span></div>"
        )
        st.caption("Finished runs are read-only, so the email and the signal stay as approved.")


def _decide(run: Run, status: str, subject: str, body: str) -> None:
    from datetime import datetime, timezone

    run.draft.edited_subject = subject
    run.draft.edited_body = body
    run.draft.decision = "approved" if status == STATUS_APPROVED else "rejected"
    run.draft.decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run.status = status
    run.log("Human review", f"Salesperson {run.draft.decision} the draft.")
    persist(run)
    st.toast(
        f"{'Approved' if status == STATUS_APPROVED else 'Rejected'} and saved, with the "
        "signal it was written from."
    )
    st.rerun()


# ---------------------------------------------------------------------------
# What happened, and what to do next
# ---------------------------------------------------------------------------
def render_identity_note(run: Run) -> None:
    if run.identity.status != "confirmed" or not run.identity.confidence_reason:
        return
    with st.expander("How we know it's the right person", expanded=False):
        st.write(run.identity.confidence_reason)
        if run.identity.resolved_note:
            st.caption(f"You told us: {run.identity.resolved_note}")


def _clarification_next_step(run: Run) -> str:
    n = len([c for c in run.identity.candidates if c.get("description")])
    if n >= 2:
        return (
            f"We found {n} possible matches for this name. Add a profile link to "
            "confirm the right person."
        )
    return "Add a profile link, or tell us in your own words which person you mean."


def render_clarification(run: Run) -> None:
    """More than one person fits: show the options and ask which one."""
    cands = "".join(
        '<div class="candidate">'
        f'<strong>{escape(str(c.get("description", "?")))}</strong>'
        f'<div class="why">{escape(str(c.get("why", "")))}</div>'
        + (f'<a href="{escape(str(c.get("url")))}" target="_blank">See the source</a>'
           if c.get("url") else "")
        + "</div>"
        for c in run.identity.candidates
    )
    html(
        '<div class="exception attention">'
        "<h4>Which person did you mean?</h4>"
        f"<p>{escape(run.identity.ambiguity or 'The evidence does not point to one person.')}</p>"
        f'<p class="next">{escape(_clarification_next_step(run))}</p>'
        "<p>We stopped before researching them, so nothing further has been spent on "
        "this prospect.</p>"
        f"{cands}</div>"
    )

    if run.mode == "fixture":
        st.warning(
            "This is a sample scenario. Continuing switches it to live web research "
            "for the remaining steps, and the run will be relabelled.",
            icon="🧪",
        )

    with st.form(f"clarify_{run.run_id}"):
        profile_url = st.text_input(
            "Profile link", value=run.profile_url,
            placeholder="LinkedIn, a company bio, or any page that identifies the right person",
        )
        note = st.text_area(
            "Or tell us in your own words",
            placeholder="e.g. “Right person — he moved to Veridian Health in 2023, still VP Finance.”",
            height=90,
        )
        c1, c2 = st.columns([1.2, 1])
        go = c1.form_submit_button("Confirm and keep researching", type="primary", width="stretch")
        abandon = c2.form_submit_button("Stop this run", width="stretch")

    if go:
        if not (profile_url.strip() or note.strip()):
            st.error("Add a profile link or a note before continuing.")
            return
        if not config.credentials_available():
            st.error(
                "Continuing needs live research, which isn't set up on this machine. "
                "See Technical details below for how to turn it on."
            )
            return
        if run.mode == "fixture":
            run.mode = "live"
            run.fixture_id = f"{run.fixture_id} (continued live)"
            run.log("Identity", "Sample run continued as a live research run.")
        run.profile_url = profile_url.strip() or run.profile_url
        run.identity.resolved_note = note.strip() or f"Confirmed via {run.profile_url}"
        run.identity.status = "confirmed"
        run.identity.confidence_reason = "Confirmed by the salesperson: " + run.identity.resolved_note
        persist(run)
        st.session_state["resume_run"] = True
        st.rerun()

    if abandon:
        run.status = STATUS_REJECTED
        run.stop_reason = "Stopped by the salesperson at the identity step."
        run.log("Identity", "Run stopped by the salesperson.")
        persist(run)
        st.rerun()


def render_no_signal(run: Run) -> None:
    """Research finished and found nothing worth writing about."""
    html(
        '<div class="exception stopped">'
        "<h4>No strong signal found</h4>"
        f"<p>{escape(run.stop_reason)}</p>"
        f'<p class="next">Try this prospect again with a different product, or move on. '
        "We would rather write nothing than invent a reason to make contact.</p>"
        "</div>"
    )
    if run.has_ranking():
        st.caption(
            f"Everything below was checked against its source and scored for "
            f"{run.product.name}. None of it describes a task this product handles, and "
            "the app will not invent a connection to make one usable."
        )
        render_other_signals(run)
        return

    left, right = st.columns([1, 1])
    with left:
        closest = run.selected_finding()
        if closest is not None:
            html('<div class="card-label">Closest thing we found</div>')
            source_name = closest.publisher or verify.publisher_from_url(closest.url, "source")
            html(
                '<div class="card">'
                f'<div class="signal-claim">{escape(closest.claim)}</div>'
                f'<div class="source-line"><a href="{escape(closest.url)}" target="_blank">'
                f'{escape(source_name)}</a>'
                + (f" · {escape(closest.date)}" if closest.date else "")
                + "</div></div>"
            )
        render_other_findings(run)
    with right:
        render_checks(run)


def render_interrupted(run: Run) -> None:
    """The search did not finish — which is not the same as finding nothing."""
    html(
        '<div class="exception attention">'
        "<h4>Research interrupted</h4>"
        f"<p>{escape(run.stop_reason)}</p>"
        '<p class="next">Nothing was decided about this prospect. Try again — the '
        "search stopped part-way, so we do not know what is out there.</p>"
        "</div>"
    )
    if st.button("Try again", key=f"retry_{run.run_id}", type="primary"):
        st.session_state["retry_run"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Technical details — everything a salesperson does not need
# ---------------------------------------------------------------------------
def render_technical_details(run: Run) -> None:
    with st.expander("Technical details"):
        store = get_store()
        st.markdown(
            f"**Run id** `{run.run_id}` · **product id** `{run.product.product_id}`"
            f" · **mode** `{run.mode}`"
            + (f" · **sample** `{run.fixture_id}`" if run.fixture_id else "")
        )
        st.markdown(
            f"**Internal status** `{run.status}` · **model** `{config.RESEARCH_MODEL}`"
            f" · **history** {store.describe()}"
        )
        if run.error:
            st.caption("Error reported by the provider:")
            st.code(run.error, language="text")
        for key, label in (
            ("save_error", "Last save error"),
            ("switch_error", "Last signal-switch error"),
        ):
            if st.session_state.get(key):
                st.caption(label + ":")
                st.code(st.session_state[key], language="text")
        st.caption("What actually ran, step by step:")
        for e in run.stage_log:
            st.markdown(f"**{STAGE_LABEL.get(e['stage'], e['stage'])}** · {e['message']}")


# ---------------------------------------------------------------------------
# Whole-run rendering
# ---------------------------------------------------------------------------
def render_run(run: Run, *, allow_review: bool = True, show_gate: bool = True) -> None:
    render_prospect_head(run)
    render_progress(run)
    render_identity_note(run)

    if run.status == STATUS_NEEDS_CLARIFICATION:
        if show_gate:
            render_clarification(run)
        else:
            html(
                '<div class="exception attention">'
                "<h4>Which person did you mean?</h4>"
                f"<p>{escape(run.identity.ambiguity)}</p>"
                '<p class="next">Open this run under “Research a prospect” to answer '
                "that.</p></div>"
            )
    elif run.status == STATUS_INSUFFICIENT_EVIDENCE:
        render_no_signal(run)
    elif run.status == STATUS_RESEARCH_INCOMPLETE:
        render_interrupted(run)
    elif run.draft.subject or run.draft.body:
        left, right = st.columns([1, 1], gap="large")
        allow_switch = allow_review and run.status == STATUS_AWAITING_REVIEW
        with left:
            render_evidence_panel(run, allow_switch=allow_switch)
        with right:
            render_draft_panel(run, allow_review=allow_review)

    render_technical_details(run)


# ---------------------------------------------------------------------------
# View: research a prospect
# ---------------------------------------------------------------------------
def render_new_run_form() -> None:
    live_ready = config.credentials_available()

    st.markdown("### Research a prospect")
    st.caption(
        "We confirm who they are, look for public evidence that matters for the product "
        "you pick, and write you an email to review. Nothing is ever sent."
    )

    if not live_ready:
        st.warning("Live research is unavailable. You can still try an example below.")
        with st.expander("Why, and how to turn it on"):
            st.markdown(
                "`GOOGLE_API_KEY` is not configured, so the app cannot run a web search "
                "or call the model.\n\n"
                "1. Get a Gemini API key from Google AI Studio.\n"
                "2. Put `GOOGLE_API_KEY=your-key` in a `.env` file in the project "
                "folder, or in `.streamlit/secrets.toml` as `GOOGLE_API_KEY = "
                '"your-key"`.\n'
                "3. Restart the app.\n\n"
                "The sample scenarios below need no key: they are saved runs, replayed."
            )

    left, right = st.columns([1.3, 1], gap="large")

    with left:
        # The product selector sits outside the form so the description and the
        # sidebar update the moment it changes.
        choices = config.product_choices()
        ids = [pid for pid, _ in choices]
        names = {pid: name for pid, name in choices}
        picker_kwargs = (
            {} if "product_id" in st.session_state
            else {"index": ids.index(config.DEFAULT_PRODUCT_ID)}
        )
        st.selectbox(
            "What are you selling?",
            ids,
            format_func=lambda pid: names[pid],
            key="product_id",
            **picker_kwargs,
        )
        chosen = config.product(selected_product_id())
        html(
            f'<div class="product-note"><strong>{escape(chosen.name)}</strong> — '
            f"{escape(chosen.description)}<br>Sold to {escape(chosen.target_users)}. "
            "We look for evidence about this, score every finding against it, and write "
            "the email about it.</div>"
        )

        with st.form("new_run"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Prospect name *", placeholder="e.g. Hannah Weiss")
            company = c2.text_input("Company *", placeholder="e.g. Meridian Outfitters")
            with st.expander("Additional details — optional, but they help"):
                role = st.text_input("Their role", placeholder="Finance Operations Manager")
                website = st.text_input("Company website", placeholder="https://…")
                profile = st.text_input(
                    "Profile link",
                    placeholder="LinkedIn or a company bio — helps us find the right person",
                )
                st.caption(
                    "A role and a profile link make it much more likely we identify the "
                    "right person first time."
                )
            submitted = st.form_submit_button(
                "Research prospect", type="primary", disabled=not live_ready
            )

        if submitted:
            if not name.strip() or not company.strip():
                st.error("We need at least a name and a company.")
            elif not live_ready:
                st.error("Live research is unavailable. Try an example instead.")
            else:
                run = Run(
                    prospect_name=name.strip(), company=company.strip(),
                    role=role.strip(), company_website=website.strip(),
                    profile_url=profile.strip(),
                    product=config.product(selected_product_id()),
                    mode="live",
                )
                persist(run)
                run_live(run)
                st.rerun()

    with right:
        st.markdown("##### Try an example")
        st.caption("Sample data · no live search. Saved runs, replayed step by step.")
        for fid, spec in fixtures.FIXTURES.items():
            with st.container(border=True):
                st.markdown(f"**{spec['label']}**")
                html(
                    '<div style="margin:.1rem 0 .4rem">'
                    + pill(str(spec["product"]), "product")
                    + pill("Sample data", "mode")
                    + "</div>"
                )
                st.caption(str(spec["summary"]))
                html(
                    '<div style="margin:.1rem 0 .55rem;font-size:.8rem;color:#8A93A5">'
                    f'Ends at: {escape(STATUS_LABEL.get(str(spec["expected"]), str(spec["expected"])))}'
                    "</div>"
                )
                if st.button("Try this example", key=f"fx_{fid}", width="stretch"):
                    run_fixture(fid)
                    st.rerun()


def view_research() -> None:
    # Resume after a clarification or a retry, without creating a new run.
    if st.session_state.pop("resume_run", False):
        st.session_state.pop("retry_run", None)
        run = get_active()
        if run:
            run_live(run, skip_identity=True)
            st.rerun()
    if st.session_state.pop("retry_run", False):
        run = get_active()
        if run:
            run_live(run, skip_identity=run.identity.status == "confirmed")
            st.rerun()

    active = get_active()
    if active is not None:
        render_run(active)
        st.divider()
        if st.button("Research someone else"):
            set_active(None)
            st.rerun()
        return

    render_new_run_form()


# ---------------------------------------------------------------------------
# View: past runs
# ---------------------------------------------------------------------------
def view_history() -> None:
    st.markdown("### Past runs")
    store = get_store()
    try:
        rows = store.list_runs()
    except Exception as exc:
        st.error("We could not read your past runs.")
        with st.expander("Technical details"):
            st.code(f"{type(exc).__name__}: {exc}", language="text")
        return

    if not rows:
        st.info("No runs yet. Start one under “Research a prospect”.")
        return

    st.caption(f"{len(rows)} run(s) · select a name to reopen it")

    cols = [1.9, 1.5, 1.6, 3.6, 1.4, 1.1]
    head = st.columns(cols, gap="small")
    for col, title in zip(
        head, ("Prospect", "Company", "Selling", "What we used", "Status", "Date (UTC)")
    ):
        col.markdown(f'<div class="hist-head">{title}</div>', unsafe_allow_html=True)

    opened = st.session_state.get("history_open")
    for r in rows:
        rid = r["run_id"]
        is_open = rid == opened
        c = st.columns(cols, gap="small")
        with c[0]:
            if st.button(
                r["prospect_name"] or "(no name)",
                key=f"open_{rid}",
                width="stretch",
                type="primary" if is_open else "secondary",
                help="Reopen this run",
            ):
                st.session_state["history_open"] = None if is_open else rid
                st.rerun()
            if r["role"]:
                html(f'<div class="hist-sub">{escape(r["role"])}</div>')
        c[1].markdown(f'<div class="hist-cell">{escape(r["company"])}</div>', unsafe_allow_html=True)
        c[2].markdown(f'<div class="hist-cell">{escape(r["product"])}</div>', unsafe_allow_html=True)
        c[3].markdown(f'<div class="hist-cell">{escape(r["signal"])}</div>', unsafe_allow_html=True)
        with c[4]:
            html(status_pill(r["status"]))
            html(
                '<div class="hist-sub">'
                + ("Sample data" if r["mode"] == "fixture" else "Live research")
                + "</div>"
            )
        c[5].markdown(
            f'<div class="hist-cell">{escape(str(r["created_at"])[:16].replace("T", " "))}</div>',
            unsafe_allow_html=True,
        )
        html('<div class="hist-rule"></div>')

    if not opened:
        return
    run = store.get(opened)
    if not run:
        st.error("That run could not be opened.")
        return

    st.divider()
    render_run(run, allow_review=True, show_gate=False)
    if run.status == STATUS_NEEDS_CLARIFICATION:
        if st.button("Answer that under Research a prospect", type="primary"):
            set_active(run)
            st.session_state["view"] = "Research a prospect"
            st.rerun()


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------
def main() -> None:
    html(CSS)
    store = get_store()
    active = get_active()

    with st.sidebar:
        st.markdown("## Personalised outreach")
        st.caption("A prospect, one real reason to write, and an email you approve.")
        st.markdown("---")
        st.radio("View", ["Research a prospect", "Past runs"], key="view",
                 label_visibility="collapsed")
        st.markdown("---")

        # The sidebar always agrees with what is on screen: the open run's
        # product while a run is open, otherwise the one picked on the form.
        if active is not None:
            shown = active.product
            st.markdown("**This run is selling**")
        else:
            shown = config.product(selected_product_id())
            st.markdown("**You are selling**")
        st.info(f"**{shown.name}** — {shown.description}")
        st.caption("What it can do, in full:")
        for cap in shown.capabilities:
            st.caption(f"· {cap}")
        st.caption(
            "Every finding is judged against this one product. The app may not claim any "
            "other capability, customer, metric or saving."
        )
        if active is not None:
            st.caption(
                "Changing product starts a new run: it changes what we search for and "
                "how findings are scored."
            )
        st.markdown("---")
        if not config.credentials_available():
            st.caption("**Live research** · unavailable — examples only")
        else:
            st.caption("**Live research** · ready")
        if getattr(store, "warning", ""):
            st.warning(store.warning, icon="⚠️")
        st.caption("No email is ever sent. The last step is always yours.")

    if st.session_state.get("view", "Research a prospect") == "Research a prospect":
        view_research()
    else:
        view_history()


main()
