"""Personalised outreach — from prospect to draft.

Streamlit front end. Two views: "Research prospect" and "Run history".

The run view is built around three questions a salesperson needs answered at a
glance: what did we learn about this prospect, where did we find it and why does
it matter, and does the email use that finding accurately. Hence the two-column
result — selected signal on the left, editable draft on the right, evidence
visible the whole time you are editing.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from outreach import config, fixtures, verify
from outreach.pipeline import SignalNotEligible, execute, redraft
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

# Statuses are text labels, not colour or icon alone.
STATUS_TONE = {
    STATUS_RUNNING: "running",
    STATUS_NEEDS_CLARIFICATION: "attention",
    STATUS_INSUFFICIENT_EVIDENCE: "stopped",
    STATUS_RESEARCH_INCOMPLETE: "attention",
    STATUS_AWAITING_REVIEW: "review",
    STATUS_APPROVED: "good",
    STATUS_REJECTED: "stopped",
}

PROV_LABEL = {
    PROV_SOURCE_TEXT: (
        "Verified source text",
        "Fetched from the source page and matched word for word, so it may be quoted.",
    ),
    PROV_SEARCH_SUMMARY: (
        "Source-backed paraphrase",
        "A source supports this claim, but exact wording was not matched. Not quotable.",
    ),
    PROV_MODEL: (
        "Unverified",
        "No source backs this claim, so it is excluded from selection and the draft.",
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

/* Tighten Streamlit's default vertical rhythm. */
.block-container { padding-top: 2.2rem; max-width: 1340px; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }

/* ---- prospect header ---- */
.prospect-head {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: .55rem .85rem;
  margin: 0 0 .15rem 0;
}
.prospect-name { font-size: 1.6rem; font-weight: 650; color: var(--ink); line-height: 1.2; }
.prospect-meta { font-size: 1rem; color: var(--ink-soft); }
.run-meta { font-size: .8rem; color: var(--ink-faint); margin-bottom: 1rem; }

/* ---- status pills: always carry a text label ---- */
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

/* ---- compact stage strip ---- */
.stages { display: flex; gap: .4rem; flex-wrap: wrap; margin: .2rem 0 .5rem; }
.stage {
  flex: 1 1 0; min-width: 120px; padding: .45rem .65rem;
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
.signal-claim { font-size: 1.07rem; line-height: 1.5; color: var(--ink); font-weight: 500; }
.source-line { font-size: .86rem; color: var(--ink-soft); margin-top: .6rem; }
.source-line a { color: var(--accent); text-decoration: none; }
.source-line a:hover { text-decoration: underline; }
.excerpt {
  border-left: 3px solid var(--accent); background: var(--surface-soft);
  padding: .55rem .75rem; margin: .7rem 0 .2rem; border-radius: 0 6px 6px 0;
  font-size: .9rem; color: var(--ink); line-height: 1.5;
}
.excerpt .tag { display: block; font-size: .72rem; color: var(--ink-faint); margin-top: .35rem; }
.why { font-size: .92rem; color: var(--ink-soft); line-height: 1.55; margin-top: .25rem; }

/* ---- the four checks ---- */
.checks { display: grid; grid-template-columns: 1fr 1fr; gap: .45rem; margin-top: .3rem; }
.check {
  border: 1px solid var(--line); border-radius: 9px; padding: .5rem .65rem; background: var(--surface);
}
.check .top { display: flex; align-items: center; justify-content: space-between; gap: .4rem; }
.check .nm { font-size: .84rem; font-weight: 650; color: var(--ink); }
.check .vd { font-size: .71rem; font-weight: 700; padding: .08rem .42rem; border-radius: 999px; }
.check.met .vd    { background: #E8F3EC; color: #1C6B3C; }
.check.unmet .vd  { background: #FBEBEB; color: #9B2C2C; }
.check.unmet      { border-color: #F0CFCF; background: #FEFAFA; }
.check .rs { font-size: .79rem; color: var(--ink-soft); line-height: 1.45; margin-top: .25rem; }
.tally { font-size: .84rem; color: var(--ink-soft); margin: .55rem 0 .15rem; }
.tally .cap { color: var(--ink-faint); font-size: .78rem; }

/* ---- ranked signals ---- */
.card-head { display: flex; align-items: center; flex-wrap: wrap; gap: .4rem .6rem; margin-bottom: .5rem; }
.score { font-size: 1.15rem; font-weight: 700; color: var(--ink); line-height: 1; }
.score.sm { font-size: 1rem; }
.score .of { font-size: .78rem; font-weight: 600; color: var(--ink-faint); }
.rank {
  font-size: .82rem; font-weight: 700; color: var(--accent);
  background: #EEF3FF; border: 1px solid #C6D6FB; border-radius: 6px; padding: .1rem .4rem;
}
.rank-claim { font-size: .97rem; line-height: 1.5; color: var(--ink); font-weight: 500; }
.comps { display: flex; flex-wrap: wrap; gap: .35rem; margin: .6rem 0 .15rem; }
.comp {
  border: 1px solid var(--line); border-radius: 7px; background: var(--surface-soft);
  padding: .22rem .5rem; font-size: .78rem; color: var(--ink-soft);
  display: flex; align-items: baseline; gap: .35rem;
}
.comp .cv { font-weight: 700; color: var(--ink); }
.comp .cm { font-weight: 600; color: var(--ink-faint); font-size: .72rem; }
.comp-why { font-size: .82rem; color: var(--ink-soft); line-height: 1.5; margin: .22rem 0; }
.comp-why .n { font-weight: 650; color: var(--ink); }
.draft-from { font-size: .82rem; color: var(--ink-faint); margin: .1rem 0 .5rem; }

/* ---- exception states ---- */
.exception { border-radius: 12px; padding: 1rem 1.15rem; margin-bottom: .85rem; border: 1px solid; }
.exception.attention { background: #FFFBF3; border-color: #F0DCB4; }
.exception.stopped   { background: #FEF7F7; border-color: #F0CFCF; }
.exception h4 { margin: 0 0 .35rem; font-size: 1rem; color: var(--ink); }
.exception p  { margin: 0 0 .4rem; font-size: .9rem; color: var(--ink-soft); line-height: 1.55; }
.candidate {
  border: 1px solid var(--line); border-radius: 9px; background: var(--surface);
  padding: .55rem .7rem; margin-bottom: .4rem; font-size: .87rem; color: var(--ink);
}
.candidate .why { font-size: .81rem; margin-top: .2rem; }
.candidate a { color: var(--accent); font-size: .81rem; text-decoration: none; }

/* ---- alt findings ---- */
.alt { border-top: 1px solid var(--line); padding: .6rem 0 .1rem; font-size: .88rem; }
.alt:first-child { border-top: none; }
.alt .cl { color: var(--ink); line-height: 1.45; }
.alt .mt { font-size: .78rem; color: var(--ink-faint); margin-top: .22rem; }
.alt .mt a { color: var(--accent); text-decoration: none; }

/* Buttons: one accent colour for the primary action. */
.stButton > button { border-radius: 8px; font-weight: 600; }

/* ---- run history rows ---- */
.hist-head {
  font-size: .73rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: var(--ink-faint); padding-bottom: .25rem;
}
.hist-cell { font-size: .87rem; color: var(--ink); line-height: 1.45; padding-top: .45rem; }
.hist-sub  { font-size: .76rem; color: var(--ink-faint); margin-top: .15rem; }
.hist-rule { border-top: 1px solid var(--line); margin: .3rem 0 .55rem; }

/* Narrow screens: stack the signal above the draft. */
@media (max-width: 900px) {
  [data-testid="stHorizontalBlock"] { flex-direction: column; }
  [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; }
  .checks { grid-template-columns: 1fr; }
}
</style>
"""


# ---------------------------------------------------------------------------
# Small HTML helpers
# ---------------------------------------------------------------------------
def pill(label: str, tone: str) -> str:
    return f'<span class="pill {tone}">{escape(label)}</span>'


def status_pill(status: str) -> str:
    return pill(status, STATUS_TONE.get(status, "running"))


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# State helpers — survive Streamlit reruns
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
        st.warning(f"Could not save this run to history: {type(exc).__name__}: {exc}")
    set_active(run)


# ---------------------------------------------------------------------------
# Header and progress
# ---------------------------------------------------------------------------
def render_prospect_head(run: Run) -> None:
    bits = [f'<span class="prospect-name">{escape(run.prospect_name)}</span>']
    meta = " · ".join(x for x in (run.role, run.company) if x)
    if meta:
        bits.append(f'<span class="prospect-meta">{escape(meta)}</span>')
    bits.append(status_pill(run.status))
    bits.append(pill("Fixture — no web search" if run.mode == "fixture" else "Live web research", "mode"))
    html(f'<div class="prospect-head">{"".join(bits)}</div>')
    html(
        f'<div class="run-meta">Run {escape(run.run_id)} · started '
        f'{escape(run.created_at[:16].replace("T", " "))} UTC</div>'
    )


def render_progress(run: Run, slot=None) -> None:
    """Compact four-stage indicator; stage 5 is the human review the UI hosts."""
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
        cells.append(f'<div class="stage {cls}"><span class="n">{i}</span>{escape(stage)}</div>')
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
    with st.spinner("Researching — live web search in progress…"):
        result = execute(run, lambda r: render_progress(r, slot), skip_identity=skip_identity)
    render_progress(result, slot)
    persist(result)
    return result


def run_fixture(fixture_id: str) -> Run:
    st.info(
        "Fixture run — no web search and no model call. The people, companies and "
        "source URLs are fictional. This rehearses the interface and the decision "
        "logic; it is not evidence that live research works.",
        icon="🧪",
    )
    slot = st.empty()
    with st.spinner("Replaying fixture stages…"):
        result = fixtures.replay(fixture_id, lambda r: render_progress(r, slot))
    render_progress(result, slot)
    persist(result)
    return result


# ---------------------------------------------------------------------------
# LEFT column — the ranked signals and the one under review
# ---------------------------------------------------------------------------
ELIGIBILITY_LABEL = {
    ELIGIBLE: ("Eligible signal", "good"),
    CONTEXT_ONLY: ("Context only", "attention"),
    EXCLUDED: ("Excluded", "stopped"),
}


def _shorten(text: str, limit: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def source_line(finding) -> str:
    """Publisher · date · link · text status, as one line."""
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
            '<span class="tag">Verified excerpt — matched word for word on the '
            "source page.</span></div>"
        )
    _, tooltip = PROV_LABEL.get(finding.provenance, ("Unknown", ""))
    return (
        '<div class="excerpt" style="border-left-color:#C8CEDA">'
        f'<span class="tag" style="margin-top:0">No verified excerpt — {escape(tooltip)}'
        "</span></div>"
    )


def render_component_scores(score, *, key: str, open_default: bool = False) -> None:
    """The four rubric scores. Numbers always visible, reasons collapsed."""
    chips = "".join(
        f'<div class="comp"><span class="cl">{escape(label)}</span>'
        f'<span class="cv">{value}<span class="cm">/{maximum}</span></span></div>'
        for _, label, value, maximum, _ in score.components()
    )
    html(f'<div class="comps">{chips}</div>')
    if st.toggle("Why these scores", value=open_default, key=f"why_{key}"):
        rows = "".join(
            f'<div class="comp-why"><span class="n">{escape(label)} '
            f"{value} of {maximum}</span> — {escape(reason or 'no reason given')}</div>"
            for _, label, value, maximum, reason in score.components()
        )
        html(f"<div>{rows}</div>")


def render_active_signal(run: Run) -> None:
    """The signal the draft is currently written from, in full."""
    finding = run.selected_finding()
    if finding is None:
        return
    score = run.score_for(finding.finding_id)
    rank = next(
        (r for r, f, _ in run.ranked_findings(ELIGIBLE) if f.finding_id == finding.finding_id),
        0,
    )

    heads = ['<div class="card-label" style="margin:0">Selected signal</div>']
    if score is not None:
        heads.append(f'<span class="score">{score.total}<span class="of"> / {SCORE_MAX}</span></span>')
    if rank:
        heads.append(pill(f"Ranked #{rank}", "mode"))
    if run.recommended_id == finding.finding_id:
        heads.append(pill("Recommended by the app", "review"))
    elif run.recommendation_was_overridden():
        heads.append(pill("Your choice — not the app's pick", "attention"))

    html(
        '<div class="card">'
        f'<div class="card-head">{"".join(heads)}</div>'
        f'<div class="signal-claim">{escape(finding.claim)}</div>'
        f"{source_line(finding)}{excerpt_block(finding)}"
        + (
            f'<div class="why"><strong>Why it ranked first:</strong> '
            f"{escape(run.selection_reason)}</div>"
            if run.selection_reason and run.recommended_id == finding.finding_id
            else ""
        )
        + "</div>"
    )

    if score is not None:
        with st.container(border=True):
            render_component_scores(score, key=f"active_{run.run_id}", open_default=False)
            st.caption(
                f"{score.total} of {SCORE_MAX} scores the strength of this outreach angle. "
                "It is not a prediction that they will buy, and it never overrides an "
                "unresolved identity or an unsupported claim."
            )
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
                f"The app recommended #{rec_rank or 1} — “{_shorten(rec.claim, 90)}”"
                + (f" ({rec_score.total} of {SCORE_MAX})" if rec_score else "")
                + ". You chose a different signal; both are kept on this run."
            )


def render_ranked_signals(run: Run, *, allow_switch: bool = False) -> None:
    """Every scored finding in rank order, with the switch control."""
    entries = run.ranked_findings()
    if not entries:
        return
    eligible_count = sum(1 for _, _, s in entries if s.eligibility == ELIGIBLE)
    html(
        '<div class="card-label" style="margin:.9rem 0 .4rem">'
        f"Ranked signals · {eligible_count} eligible of {len(entries)} scored</div>"
    )

    for rank, finding, score in entries:
        label, tone = ELIGIBILITY_LABEL.get(score.eligibility, ("Scored", "mode"))
        is_active = finding.finding_id == run.active_id
        is_top = rank == 1
        with st.container(border=True):
            head = [
                f'<span class="rank">{"#" + str(rank) if rank else "—"}</span>',
                f'<span class="score sm">{score.total}<span class="of"> / {SCORE_MAX}</span></span>',
                pill(label, tone),
            ]
            if finding.finding_id == run.recommended_id:
                head.append(pill("Recommended", "review"))
            if is_active:
                head.append(pill("In review", "good"))
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
                    '<div class="why"><strong>Why the app ranked this first:</strong> '
                    f"{escape(run.selection_reason)}</div>"
                )
            # The top eligible signal opens with its reasons showing; the rest
            # stay collapsed until asked for.
            render_component_scores(
                score,
                key=f"{run.run_id}_{finding.finding_id}",
                open_default=is_top and is_active,
            )
            if finding.quote_verified and finding.quote and not is_active:
                html(excerpt_block(finding))
            if allow_switch and score.eligibility == ELIGIBLE and not is_active:
                if st.button(
                    "Use this signal",
                    key=f"use_{run.run_id}_{finding.finding_id}",
                    width="stretch",
                    help="Rewrites the draft from this finding. No new web research.",
                ):
                    request_switch(run, finding.finding_id)


def render_legacy_signal(run: Run) -> None:
    """A run saved before ranked signals existed: show it as it was stored."""
    finding = run.selected_finding()
    if finding is None:
        return
    html(
        '<div class="card">'
        '<div class="card-label">Selected signal</div>'
        f'<div class="signal-claim">{escape(finding.claim)}</div>'
        f"{source_line(finding)}{excerpt_block(finding)}"
        + (
            f'<div class="why"><strong>Why it matters here:</strong> '
            f"{escape(run.selection_reason)}</div>"
            if run.selection_reason
            else ""
        )
        + "</div>"
    )
    st.caption(
        "This run was saved before ranked signals were added, so it has no rubric "
        "scores and no alternatives to switch to. Nothing has been scored "
        "retrospectively — the evidence and draft are exactly as they were stored."
    )
    render_checks(run)
    render_alternatives(run)


def render_signal_panel(run: Run, *, allow_switch: bool = False) -> None:
    """Left column: the signal under review, then the whole ranked list.

    ``allow_switch`` is false for a finalised run, so an approved or rejected
    run stays read-only under the same rule as the draft editor.
    """
    if not run.has_ranking():
        render_legacy_signal(run)
        return
    render_active_signal(run)
    render_ranked_signals(run, allow_switch=allow_switch)


def render_checks(run: Run) -> None:
    """Pass/fail view of the active signal's components (legacy runs included)."""
    if not run.checks:
        return
    met, total = run.checks_met()
    cells = []
    for c in run.checks:
        cls = "met" if c.passed else "unmet"
        verdict = "Met" if c.passed else "Not met"
        cells.append(
            f'<div class="check {cls}"><div class="top"><span class="nm">{escape(c.name)}</span>'
            f'<span class="vd">{verdict}</span></div>'
            f'<div class="rs">{escape(c.reason)}</div></div>'
        )
    html(
        '<div class="card">'
        '<div class="card-label">Checks</div>'
        f'<div class="checks">{"".join(cells)}</div>'
        f'<div class="tally"><strong>{met} of {total} checks met</strong><br>'
        '<span class="cap">A review aid, not a buying probability. The tally never '
        "overrides an unresolved identity or an unsupported claim.</span></div>"
        "</div>"
    )


def render_alternatives(run: Run) -> None:
    """Other findings, for runs with no ranking data."""
    others = [(i, f) for i, f in enumerate(run.findings) if i != run.selected_index]
    if not others:
        return
    with st.expander(f"Other findings considered ({len(others)})"):
        for _, f in others:
            label, _ = PROV_LABEL.get(f.provenance, ("Unknown", ""))
            excluded = "" if verify.is_usable(f) else " · excluded from the draft"
            source_name = f.publisher or verify.publisher_from_url(f.url, "source")
            date = f" · {escape(f.date)}" if f.date else ""
            html(
                f'<div class="alt"><div class="cl">{escape(f.claim)}</div>'
                f'<div class="mt"><a href="{escape(f.url)}" target="_blank">{escape(source_name)}</a>'
                f'{date} · {escape(label)}{excluded}</div></div>'
            )
            st.caption(f.verification_note)


# ---------------------------------------------------------------------------
# Switching the signal under review
# ---------------------------------------------------------------------------
def draft_keys(run: Run) -> tuple[str, str]:
    """Widget keys for the draft editor, revised whenever the draft is replaced.

    Streamlit keeps a widget's value against its key, so re-rendering the same
    key after a switch would show the previous signal's email next to the new
    signal's evidence. Bumping the revision gives the new draft its own widgets.
    """
    rev = st.session_state.get(f"draft_rev_{run.run_id}", 0)
    return f"subj_{run.run_id}_{rev}", f"body_{run.run_id}_{rev}"


def _has_unsaved_edits(run: Run) -> bool:
    """True when the editor holds text the run has not stored."""
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
    """Ask to switch signals, confirming first if edits would be lost."""
    if _has_unsaved_edits(run):
        subj_key, body_key = draft_keys(run)
        # Hold the unsaved text while we ask, so no path through the dialog can
        # lose it -- including the one where the switch itself fails.
        st.session_state["pending_switch"] = finding_id
        st.session_state["pending_edits"] = (
            st.session_state.get(subj_key, run.draft.final_subject()),
            st.session_state.get(body_key, run.draft.final_body()),
        )
        st.rerun()
    do_switch(run, finding_id)


def _restore_pending_edits(run: Run) -> None:
    """Put held text back into the editor."""
    held = st.session_state.pop("pending_edits", None)
    if not held:
        return
    subj_key, body_key = draft_keys(run)
    st.session_state[subj_key], st.session_state[body_key] = held


def do_switch(run: Run, finding_id: str) -> None:
    """Rewrite the draft from another finding. No new research, same run."""
    st.session_state.pop("pending_switch", None)
    draft_fn = None
    if run.mode == "fixture":
        canned = fixtures.alternate_draft(run.fixture_id, finding_id)
        if canned is None:
            st.error(
                "This fixture has no stored draft for that signal, and generating one "
                "would need a live model call. Fixture A's two eligible signals are the "
                "ones wired for this."
            )
            _restore_pending_edits(run)
            return
        draft_fn = lambda _run, _finding: canned  # noqa: E731 - fixture, not the model
    elif not config.credentials_available():
        st.error(
            "Rewriting the draft needs GOOGLE_API_KEY. The saved research and scores are "
            "untouched, and the current draft has been kept."
        )
        _restore_pending_edits(run)
        return

    try:
        with st.spinner("Rewriting the draft from the chosen signal…"):
            redraft(run, finding_id, draft_fn=draft_fn)
    except SignalNotEligible as exc:
        st.error(str(exc))
        _restore_pending_edits(run)
        return
    except Exception as exc:
        st.error(
            f"Could not rewrite the draft: {type(exc).__name__}: {exc}. The previous "
            "draft and its original signal were kept — try again, or keep the one you have."
        )
        persist(run)
        _restore_pending_edits(run)
        return

    # The reviewer chose to replace their edits, so drop the held text.
    st.session_state.pop("pending_edits", None)
    # Give the rewritten draft its own editor widgets.
    st.session_state[f"draft_rev_{run.run_id}"] = (
        st.session_state.get(f"draft_rev_{run.run_id}", 0) + 1
    )
    persist(run)
    st.toast("Draft rewritten from the chosen signal. It needs a fresh approval.")
    st.rerun()


def render_pending_switch(run: Run) -> None:
    """Confirm before replacing edits the reviewer has not saved."""
    finding_id = st.session_state.get("pending_switch")
    if not finding_id:
        return
    finding = run.finding_by_id(finding_id)
    st.warning(
        "You have unsaved edits in the draft. Switching to "
        f"“{_shorten(finding.claim, 80) if finding else finding_id}” replaces them with a "
        "newly written draft.",
        icon="✏️",
    )
    c1, c2, c3 = st.columns([1.2, 1, 1])
    if c1.button("Replace my edits", key=f"sw_yes_{run.run_id}", type="primary", width="stretch"):
        do_switch(run, finding_id)
    if c2.button("Keep my edits", key=f"sw_no_{run.run_id}", width="stretch"):
        st.session_state.pop("pending_switch", None)
        _restore_pending_edits(run)
        st.rerun()
    if c3.button("Save edits first", key=f"sw_save_{run.run_id}", width="stretch"):
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
# RIGHT column — the draft
# ---------------------------------------------------------------------------
def render_draft_panel(run: Run, *, allow_review: bool) -> None:
    editable = allow_review and run.status == STATUS_AWAITING_REVIEW
    html('<div class="card-label" style="margin-bottom:.35rem">Draft for review</div>')

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
            bits.append(f"{score.total} of {SCORE_MAX}")
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
    subject = st.text_input(
        "Subject", key=subj_key, disabled=not editable, **subj_kwargs,
    )
    body = st.text_area(
        "Email body", height=330, key=body_key, disabled=not editable, **body_kwargs,
    )

    if editable:
        c1, c2, c3 = st.columns([1.1, 1, 1])
        if c1.button("Approve draft", key=f"appr_{run.run_id}", type="primary",
                     width="stretch"):
            _decide(run, STATUS_APPROVED, subject, body)
        if c2.button("Reject draft", key=f"rej_{run.run_id}", width="stretch"):
            _decide(run, STATUS_REJECTED, subject, body)
        if c3.button("Save edits", key=f"save_{run.run_id}", width="stretch"):
            run.draft.edited_subject = subject
            run.draft.edited_body = body
            run.log("Human review", "Salesperson saved edits to the draft.")
            persist(run)
            st.toast("Edits saved.")
            st.rerun()
        st.caption(
            "Editing, approving, rejecting or switching signal never re-runs research "
            "and never creates another run. No email is sent — the workflow ends here."
        )
    elif run.draft.decision:
        tone = "good" if run.draft.decision == "approved" else "stopped"
        html(
            f'<div style="margin-top:.4rem">{pill("Review saved: " + run.draft.decision, tone)}'
            f'<span style="font-size:.82rem;color:var(--ink-faint);margin-left:.5rem">'
            f'{escape(run.draft.decided_at.replace("T", " ")[:19])} UTC · this is the '
            f"reviewed version that was stored</span></div>"
        )


def _decide(run: Run, status: str, subject: str, body: str) -> None:
    from datetime import datetime, timezone

    run.draft.edited_subject = subject
    run.draft.edited_body = body
    run.draft.decision = "approved" if status == STATUS_APPROVED else "rejected"
    run.draft.decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run.status = status
    run.log("Human review", f"Salesperson {run.draft.decision} the draft.")
    persist(run)
    st.rerun()


# ---------------------------------------------------------------------------
# Exception states — each one actionable
# ---------------------------------------------------------------------------
def render_identity_note(run: Run) -> None:
    if run.identity.status != "confirmed" or not run.identity.confidence_reason:
        return
    with st.expander("Identity confirmed — how we know", expanded=False):
        st.write(run.identity.confidence_reason)
        if run.identity.resolved_note:
            st.caption(f"Salesperson's clarification: {run.identity.resolved_note}")


def render_clarification(run: Run) -> None:
    """Ambiguous identity: show the possible matches and ask for a profile link."""
    cands = "".join(
        '<div class="candidate">'
        f'<strong>{escape(str(c.get("description", "?")))}</strong>'
        f'<div class="why">{escape(str(c.get("why", "")))}</div>'
        + (f'<a href="{escape(str(c.get("url")))}" target="_blank">View source</a>'
           if c.get("url") else "")
        + "</div>"
        for c in run.identity.candidates
    )
    html(
        '<div class="exception attention">'
        "<h4>Needs clarification — which person do you mean?</h4>"
        f"<p>{escape(run.identity.ambiguity or 'The evidence does not single out one person.')}</p>"
        "<p>Research has not run yet, so nothing has been spent on this prospect beyond "
        "the identity search.</p>"
        f"{cands}</div>"
    )

    if run.mode == "fixture":
        st.warning(
            "This is a fixture run. Continuing switches it to live web research for the "
            "remaining stages, and the run will be relabelled accordingly.",
            icon="🧪",
        )

    with st.form(f"clarify_{run.run_id}"):
        profile_url = st.text_input(
            "Public profile URL", value=run.profile_url,
            placeholder="LinkedIn, company bio or any page that identifies the right person",
        )
        note = st.text_area(
            "Or a correction in your own words",
            placeholder="e.g. “Right person — he moved to Veridian Health in 2023, still VP Finance.”",
            height=90,
        )
        c1, c2 = st.columns([1.2, 1])
        go = c1.form_submit_button("Confirm and continue research", type="primary",
                                   width="stretch")
        abandon = c2.form_submit_button("Abandon run", width="stretch")

    if go:
        if not (profile_url.strip() or note.strip()):
            st.error("Add a profile link or a note before continuing.")
            return
        if not config.credentials_available():
            st.error(
                "Continuing runs live web research, which needs GOOGLE_API_KEY. "
                "Configure it in .env or .streamlit/secrets.toml first."
            )
            return
        if run.mode == "fixture":
            run.mode = "live"
            run.fixture_id = f"{run.fixture_id} (continued live)"
            run.log("Identity", "Fixture run continued as a live research run.")
        run.profile_url = profile_url.strip() or run.profile_url
        run.identity.resolved_note = note.strip() or f"Confirmed via {run.profile_url}"
        run.identity.status = "confirmed"
        run.identity.confidence_reason = "Confirmed by the salesperson: " + run.identity.resolved_note
        persist(run)
        st.session_state["resume_run"] = True
        st.rerun()

    if abandon:
        run.status = STATUS_REJECTED
        run.stop_reason = "Abandoned by the salesperson at the identity step."
        run.log("Identity", "Run abandoned by the salesperson.")
        persist(run)
        st.rerun()


def render_insufficient(run: Run) -> None:
    """Show what was checked and why no draft was produced."""
    html(
        '<div class="exception stopped">'
        "<h4>Insufficient evidence — no draft was produced</h4>"
        f"<p>{escape(run.stop_reason)}</p>"
        "<p>This is a decision, not a crash: the app refused to invent a reason to make "
        "contact. Everything it checked is below.</p>"
        "</div>"
    )
    if run.has_ranking():
        st.caption(
            "Every finding below was verified and scored against the same 10-point "
            "rubric. None of them is eligible to write from, and the app will not "
            "invent a connection to make one eligible."
        )
        render_ranked_signals(run)
        return

    left, right = st.columns([1, 1])
    with left:
        if run.selected_finding() is not None:
            html('<div class="card-label">Closest finding</div>')
            f = run.selected_finding()
            source_name = f.publisher or verify.publisher_from_url(f.url, "source")
            html(
                '<div class="card">'
                f'<div class="signal-claim">{escape(f.claim)}</div>'
                f'<div class="source-line"><a href="{escape(f.url)}" target="_blank">'
                f'{escape(source_name)}</a>'
                + (f" · {escape(f.date)}" if f.date else "")
                + "</div>"
                + (f'<div class="why">{escape(run.selection_reason)}</div>'
                   if run.selection_reason else "")
                + "</div>"
            )
        render_alternatives(run)
    with right:
        render_checks(run)
        if not run.checks and run.findings:
            st.caption("No checks were recorded — the run stopped during research.")


def render_incomplete(run: Run) -> None:
    html(
        '<div class="exception attention">'
        "<h4>Research incomplete — the provider failed</h4>"
        f"<p>{escape(run.stop_reason)}</p>"
        "<p>This is not the same as finding nothing: we do not know what the evidence "
        "says, because the search did not complete.</p>"
        "</div>"
    )
    if run.error:
        st.code(run.error, language="text")
    if st.button("Retry this run", key=f"retry_{run.run_id}", type="primary"):
        st.session_state["retry_run"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Whole-run rendering
# ---------------------------------------------------------------------------
def render_run(run: Run, *, allow_review: bool = True, show_gate: bool = True) -> None:
    render_prospect_head(run)
    render_progress(run)

    if run.mode == "fixture":
        st.caption("Fixture run — synthetic data; no web search was performed.")

    render_identity_note(run)

    if run.status == STATUS_NEEDS_CLARIFICATION:
        if show_gate:
            render_clarification(run)
        else:
            html(
                '<div class="exception attention">'
                "<h4>Needs clarification</h4>"
                f"<p>{escape(run.identity.ambiguity)}</p>"
                "<p>Open this run in Research prospect to resolve it.</p></div>"
            )
    elif run.status == STATUS_INSUFFICIENT_EVIDENCE:
        render_insufficient(run)
    elif run.status == STATUS_RESEARCH_INCOMPLETE:
        render_incomplete(run)
    elif run.draft.subject or run.draft.body:
        left, right = st.columns([1, 1], gap="large")
        allow_switch = allow_review and run.status == STATUS_AWAITING_REVIEW
        with left:
            render_signal_panel(run, allow_switch=allow_switch)
        with right:
            render_draft_panel(run, allow_review=allow_review)

    with st.expander("Stage log — what actually ran"):
        for e in run.stage_log:
            st.markdown(f"**{e['stage']}** · {e['message']}")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
def view_research() -> None:
    # Resume after clarification or retry, without creating a new run.
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
        if st.button("Research another prospect"):
            set_active(None)
            st.rerun()
        return

    st.markdown("### Research prospect")
    st.caption(
        "Enter a prospect. The app confirms who they are, finds public signals, picks "
        "one, and drafts an email for you to review. Nothing is ever sent."
    )

    left, right = st.columns([1.15, 1], gap="large")

    with left:
        with st.form("new_run"):
            st.markdown("**New prospect** · live web research")
            name = st.text_input("Prospect name *", placeholder="e.g. Priya Raghavan")
            company = st.text_input("Company *", placeholder="e.g. Northwind Logistics")
            c1, c2 = st.columns(2)
            role = c1.text_input("Role", placeholder="Head of Finance Operations")
            website = c2.text_input("Company website", placeholder="https://…")
            profile = st.text_input(
                "Public profile URL",
                placeholder="LinkedIn or company bio — helps identify the right person",
            )
            st.caption("Role, website and profile are optional but improve identity matching.")
            submitted = st.form_submit_button("Run research", type="primary")

        if submitted:
            if not name.strip() or not company.strip():
                st.error("Prospect name and company are both required.")
            elif not config.credentials_available():
                st.error(
                    "GOOGLE_API_KEY is not configured, so live research cannot run. Add it "
                    "to .env or .streamlit/secrets.toml. The fixture scenarios still work."
                )
            else:
                run = Run(
                    prospect_name=name.strip(), company=company.strip(),
                    role=role.strip(), company_website=website.strip(),
                    profile_url=profile.strip(), mode="live",
                )
                persist(run)
                run_live(run)
                st.rerun()

    with right:
        st.markdown("**Rehearsal fixtures** · no web search, no model call")
        st.caption(
            "Repeatable scenarios for rehearsing the demo. Stored and labelled as "
            "fixtures, so they stay visibly separate from live research."
        )
        for fid, spec in fixtures.FIXTURES.items():
            with st.container(border=True):
                st.markdown(f"**{spec['label']}**")
                st.caption(str(spec["summary"]))
                html(f'<div style="margin:.1rem 0 .55rem">Expected: '
                     f'{status_pill(str(spec["expected"]))}</div>')
                if st.button("Replay fixture", key=f"fx_{fid}", width="stretch"):
                    run_fixture(fid)
                    st.rerun()


def view_history() -> None:
    st.markdown("### Run history")
    store = get_store()
    try:
        rows = store.list_runs()
    except Exception as exc:
        st.error(f"Could not read history: {type(exc).__name__}: {exc}")
        return

    if not rows:
        st.info("No runs yet. Start one in Research prospect.")
        return

    st.caption(f"{len(rows)} run(s) · stored in {store.describe()} · select a row to reopen it")

    # One row per run. A plain row list rather than a data grid: the selected
    # signal is a sentence that needs to wrap, and this stays clickable at any
    # width.
    cols = [2.0, 1.7, 4.4, 1.5, 1.2]
    head = st.columns(cols, gap="small")
    for col, title in zip(head, ("Prospect", "Company", "Selected signal", "Status", "Date (UTC)")):
        col.markdown(f'<div class="hist-head">{title}</div>', unsafe_allow_html=True)

    opened = st.session_state.get("history_open")
    for r in rows:
        rid = r["run_id"]
        is_open = rid == opened
        c = st.columns(cols, gap="small")
        with c[0]:
            if st.button(
                r["prospect_name"] or "(unnamed)",
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
        c[2].markdown(f'<div class="hist-cell">{escape(r["signal"])}</div>', unsafe_allow_html=True)
        with c[3]:
            html(status_pill(r["status"]))
            html(f'<div class="hist-sub">{"Fixture" if r["mode"] == "fixture" else "Live"}</div>')
        c[4].markdown(
            f'<div class="hist-cell">{escape(str(r["created_at"])[:16].replace("T", " "))}</div>',
            unsafe_allow_html=True,
        )
        html('<div class="hist-rule"></div>')

    if not opened:
        return
    run = store.get(opened)
    if not run:
        st.error("That run could not be loaded.")
        return

    st.divider()
    render_run(run, allow_review=True, show_gate=False)
    if run.status == STATUS_NEEDS_CLARIFICATION:
        if st.button("Continue this run in Research prospect", type="primary"):
            set_active(run)
            st.session_state["view"] = "Research prospect"
            st.rerun()


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------
def main() -> None:
    html(CSS)
    store = get_store()

    with st.sidebar:
        st.markdown("## Personalised outreach")
        st.caption("Prospect → research → one signal → draft → human review")
        st.markdown("---")
        st.markdown("**What we sell**")
        st.info(config.SELLER_PROFILE)
        st.caption(
            "Every finding is judged against this one sentence. The app may not claim "
            "any other capability, customer, metric or saving."
        )
        st.markdown("---")
        st.radio("View", ["Research prospect", "Run history"], key="view",
                 label_visibility="collapsed")
        st.markdown("---")
        st.caption(f"**History** · {store.describe()}")
        if getattr(store, "warning", ""):
            st.warning(store.warning, icon="⚠️")
        st.caption(
            "**Research** · "
            + ("Gemini + Google Search configured" if config.credentials_available()
               else "GOOGLE_API_KEY missing — fixtures only")
        )
        st.caption(f"**Model** · {config.RESEARCH_MODEL}")
        st.caption("No email integration. The workflow ends at human review.")

    if st.session_state.get("view", "Research prospect") == "Research prospect":
        view_research()
    else:
        view_history()


main()
