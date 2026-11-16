"""The four-stage workflow: identity -> research -> signal -> draft.

Each stage is a plain function on a ``Run``. ``execute`` drives them in order and
calls ``on_stage(run)`` after each step so the UI can show real progress while
work is happening. Stages are resumable: after the user resolves an ambiguous
identity, ``execute`` is called again with ``skip_identity=True``.

Human review is deliberately outside this module -- the workflow ends at
"Awaiting review" and the Streamlit controls own what happens next.
"""

from __future__ import annotations

from typing import Callable

from . import prompts, verify
from .config import MAX_FINDINGS, SELLER_PROFILE
from .gemini_client import (
    GroundedResult,
    MissingCredentials,
    ResearchProviderError,
    grounded_search,
    json_call,
)
from .schema import (
    PROV_SOURCE_TEXT,
    STATUS_AWAITING_REVIEW,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_RESEARCH_INCOMPLETE,
    STATUS_RUNNING,
    Check,
    Draft,
    Finding,
    Identity,
    Run,
    Source,
)

OnStage = Callable[[Run], None]


def _noop(_: Run) -> None:
    return None


def _hints(run: Run) -> str:
    lines = []
    if run.role:
        lines.append(f'Their stated role: "{run.role}"')
    if run.company_website:
        lines.append(f"Company website: {run.company_website}")
    if run.profile_url:
        lines.append(f"Public profile given by the salesperson: {run.profile_url}")
    if run.identity.resolved_note:
        lines.append(
            "The salesperson clarified: " + run.identity.resolved_note
        )
    return "\n".join(lines)


def _role_line(run: Run) -> str:
    return f", {run.role}," if run.role else ""


def _merge_sources(run: Run, result: GroundedResult) -> None:
    """Add newly cited sources to the run, de-duplicated by URL."""
    by_url = {s.url: s for s in run.sources}
    for payload in result.sources.values():
        url = payload.get("url", "")
        if url in by_url:
            by_url[url].supported_claims.extend(payload.get("supported_claims", []))
            continue
        src = Source.from_dict(payload)
        src.short_id = f"src-{len(run.sources) + 1}"
        run.sources.append(src)
        by_url[url] = src


def _source_table(run: Run) -> str:
    if not run.sources:
        return "(no sources were cited by the search)"
    return "\n".join(
        f"- {s.short_id} | {s.title or s.domain or 'untitled'} | {s.url}"
        for s in run.sources
    )


def _grounding_segments(run: Run) -> list[str]:
    out: list[str] = []
    for s in run.sources:
        for claim in s.supported_claims:
            seg = (claim.get("text_segment") or "").strip()
            if seg:
                out.append(seg)
    return out


# ---------------------------------------------------------------------------
# Stage 1 -- confirm identity
# ---------------------------------------------------------------------------
def stage_identity(run: Run) -> None:
    run.log("Identity", f"Searching for public evidence on {run.prospect_name} at {run.company}.")

    result = grounded_search(
        prompts.IDENTITY_SEARCH.format(
            name=run.prospect_name,
            company=run.company,
            hints=_hints(run),
            rules=prompts.GROUNDING_RULES,
        )
    )
    _merge_sources(run, result)
    run.log(
        "Identity",
        f"{len(result.queries)} search(es) run, {len(run.sources)} source(s) cited.",
    )

    verdict = json_call(
        prompts.IDENTITY_JUDGE.format(
            name=run.prospect_name,
            company=run.company,
            hints=_hints(run),
            research=result.text or "(the search returned no usable summary)",
            sources=_source_table(run),
        )
    )
    if not isinstance(verdict, dict):
        raise ResearchProviderError("Identity check returned an unexpected shape.")

    run.identity = Identity(
        status=str(verdict.get("status", "ambiguous")),
        confidence_reason=str(verdict.get("confidence_reason", "")),
        ambiguity=str(verdict.get("ambiguity", "")),
        candidates=[c for c in (verdict.get("candidates") or []) if isinstance(c, dict)],
        resolved_note=run.identity.resolved_note,
    )

    if run.identity.status == "confirmed":
        run.log("Identity", f"Identity confirmed. {run.identity.confidence_reason}")
        return

    run.status = STATUS_NEEDS_CLARIFICATION
    if run.identity.status == "not_found":
        run.identity.ambiguity = run.identity.ambiguity or (
            "No credible public evidence was found for this person. Check the "
            "spelling, or add a profile link."
        )
    run.log("Identity", f"Paused -- needs clarification. {run.identity.ambiguity}")


# ---------------------------------------------------------------------------
# Stage 2 -- candidate signals
# ---------------------------------------------------------------------------
def stage_research(run: Run) -> None:
    run.log("Research", "Searching company pages, job postings, announcements and interviews.")

    result = grounded_search(
        prompts.RESEARCH_SEARCH.format(
            name=run.prospect_name,
            company=run.company,
            role_line=f"Their role: {run.role}" if run.role else "",
            hints=_hints(run),
            identity_note=(
                f"Identity already confirmed: {run.identity.confidence_reason}"
                if run.identity.confidence_reason else ""
            ),
            rules=prompts.GROUNDING_RULES,
        )
    )
    _merge_sources(run, result)
    run.log("Research", f"{len(run.sources)} source(s) cited in total. Extracting findings.")

    extracted = json_call(
        prompts.RESEARCH_EXTRACT.format(
            max_findings=MAX_FINDINGS,
            name=run.prospect_name,
            company=run.company,
            role_line=f"Their role: {run.role}" if run.role else "",
            research=result.text or "(the search returned no usable summary)",
            sources=_source_table(run),
        )
    )
    raw = extracted.get("findings", []) if isinstance(extracted, dict) else []
    allowed_urls = {s.url for s in run.sources}

    findings: list[Finding] = []
    for item in raw[:MAX_FINDINGS]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if url not in allowed_urls:
            run.log(
                "Research",
                f"Dropped a finding whose URL was not in the cited sources: {url[:80] or '(blank)'}",
            )
            continue
        src = next((s for s in run.sources if s.url == url), None)
        findings.append(
            Finding(
                claim=str(item.get("claim", "")).strip(),
                publisher=str(item.get("publisher", "")).strip() or (src.domain if src else ""),
                url=url,
                date=str(item.get("date", "")).strip(),
                source_id=src.short_id if src else "",
                kind=str(item.get("kind", "")).strip(),
                quote=str(item.get("quote", "")).strip(),
            )
        )

    if not findings:
        run.findings = []
        run.status = STATUS_INSUFFICIENT_EVIDENCE
        run.stop_reason = (
            "The search returned nothing specific and attributable about this "
            "person or their team, so there is no fact to build outreach on."
        )
        run.log("Research", "No attributable findings. Stopping with 'Insufficient evidence'.")
        return

    # Verify each finding against its source page before it can be used.
    run.log("Research", f"Verifying {len(findings)} finding(s) against their sources.")
    segments = _grounding_segments(run)
    for finding in findings:
        verify.verify_finding(finding, segments)
        run.log(
            "Research",
            f"{finding.publisher or 'source'}: {finding.verification_note}",
        )
    run.findings = findings

    usable = [f for f in findings if verify.is_usable(f)]
    if not usable:
        run.status = STATUS_INSUFFICIENT_EVIDENCE
        run.stop_reason = (
            "Every candidate finding failed verification — the source pages could "
            "not be read or did not state the claim -- so nothing can be quoted or "
            "referenced in a draft."
        )
        run.log("Research", "All findings failed verification. Stopping.")
        return

    run.log("Research", f"{len(usable)} of {len(findings)} finding(s) verified and usable.")


# ---------------------------------------------------------------------------
# Stage 3 -- select one signal
# ---------------------------------------------------------------------------
def _format_findings_for_prompt(run: Run, usable: list[tuple[int, Finding]]) -> str:
    blocks = []
    for idx, f in usable:
        quote = f'\n  verified quote: "{f.quote}"' if f.quote_verified and f.quote else ""
        blocks.append(
            f"[{idx}] claim: {f.claim}\n"
            f"  publisher: {f.publisher or 'unknown'}\n"
            f"  kind: {f.kind or 'unknown'}\n"
            f"  date: {f.date or 'not stated by the source'}\n"
            f"  url: {f.url}{quote}"
        )
    return "\n\n".join(blocks)


def stage_signal(run: Run) -> None:
    usable = [(i, f) for i, f in enumerate(run.findings) if verify.is_usable(f)]
    run.log("Signal selection", f"Comparing {len(usable)} verified finding(s) against our offer.")

    verdict = json_call(
        prompts.SIGNAL_SELECT.format(
            seller=prompts.SELLER_BLOCK,
            name=run.prospect_name,
            role_line=_role_line(run),
            company=run.company,
            findings=_format_findings_for_prompt(run, usable),
        )
    )
    if not isinstance(verdict, dict):
        raise ResearchProviderError("Signal selection returned an unexpected shape.")

    run.checks = [
        Check.from_dict(c)
        for c in (verdict.get("checks") or [])
        if isinstance(c, dict) and "name" in c and "passed" in c
    ]
    run.selection_reason = str(verdict.get("selection_reason", ""))

    idx = verdict.get("selected_index", -1)
    valid_indices = {i for i, _ in usable}
    if not isinstance(idx, int) or idx not in valid_indices:
        idx = next(iter(sorted(valid_indices)), -1)
    run.selected_index = idx

    met, total = run.checks_met()

    # A check tally never overrides evidence. These two gates come first.
    evidence_check = next((c for c in run.checks if c.name.lower().startswith("evidence")), None)
    if evidence_check and not evidence_check.passed:
        run.status = STATUS_INSUFFICIENT_EVIDENCE
        run.stop_reason = (
            "The evidence check failed, so the selected claim is not supported by "
            f"an identifiable source: {evidence_check.reason}"
        )
        run.log("Signal selection", "Evidence check failed. Stopping before drafting.")
        return

    if not verdict.get("sufficient", True):
        run.status = STATUS_INSUFFICIENT_EVIDENCE
        run.stop_reason = str(verdict.get("insufficient_reason", "")) or (
            "Nothing in the available evidence connects this prospect to invoice-to-PO "
            "matching or discrepancy review, so personalised outreach would have to "
            "invent a reason to write."
        )
        run.log(
            "Signal selection",
            f"No credible connection to our offer ({met} of {total} checks met). Stopping.",
        )
        return

    selected = run.selected_finding()
    run.log(
        "Signal selection",
        f"Selected: {selected.claim if selected else '(none)'} ({met} of {total} checks met).",
    )


# ---------------------------------------------------------------------------
# Stage 4 -- draft
# ---------------------------------------------------------------------------
def stage_draft(run: Run) -> None:
    finding = run.selected_finding()
    if finding is None:
        raise ResearchProviderError("No signal was selected, so there is nothing to draft.")

    run.log("Draft", "Writing a first-contact email from the selected evidence.")
    quotable = finding.quote_verified and finding.provenance == PROV_SOURCE_TEXT and finding.quote

    payload = json_call(
        prompts.DRAFT_EMAIL.format(
            seller=prompts.SELLER_BLOCK,
            name=run.prospect_name,
            role_line=_role_line(run),
            company=run.company,
            claim=finding.claim,
            publisher=finding.publisher or "unknown publisher",
            date_line=f"\n  Dated: {finding.date}" if finding.date else "",
            url=finding.url,
            quote_line=f'  Verified quote: "{finding.quote}"' if quotable else "",
            selection_reason=run.selection_reason or "it is the only verified finding.",
            quote_rule=prompts.QUOTE_RULE_ALLOWED if quotable else prompts.QUOTE_RULE_FORBIDDEN,
        ),
        temperature=0.45,
    )
    if not isinstance(payload, dict):
        raise ResearchProviderError("Draft generation returned an unexpected shape.")

    subject = str(payload.get("subject", "")).strip()
    body = str(payload.get("body", "")).strip()
    if not subject or not body:
        raise ResearchProviderError("Draft generation returned an empty subject or body.")

    # Guardrail: strip any quotation the draft invented. Only a verified quote
    # from the source page may appear in quotation marks.
    body, removed = _strip_unverified_quotes(body, finding.quote if quotable else "")
    if removed:
        run.log(
            "Draft",
            f"Removed {removed} unverified quotation(s) from the draft; the fact is "
            "referenced as paraphrase instead.",
        )

    run.draft = Draft(subject=subject, body=body)
    run.status = STATUS_AWAITING_REVIEW
    run.log("Human review", "Draft ready for the salesperson to edit, approve or reject.")


_QUOTE_CHARS = ('"', "“", "”")


def _strip_unverified_quotes(body: str, allowed_quote: str) -> tuple[str, int]:
    """Unwrap quoted spans unless they reproduce ``allowed_quote`` verbatim."""
    import re

    pattern = re.compile(r'["“]([^"“”]{10,})["”]')
    removed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal removed
        inner = match.group(1)
        if allowed_quote and verify.normalise(inner) in verify.normalise(allowed_quote):
            return match.group(0)
        removed += 1
        return inner

    return pattern.sub(repl, body), removed


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def execute(run: Run, on_stage: OnStage | None = None, *, skip_identity: bool = False) -> Run:
    """Run the workflow to the next human decision point.

    Returns the same ``Run`` with a terminal-for-now status:
    Needs clarification, Insufficient evidence, Research incomplete, or
    Awaiting review.
    """
    cb = on_stage or _noop
    run.status = STATUS_RUNNING
    run.error = ""
    cb(run)

    try:
        if not skip_identity:
            stage_identity(run)
            cb(run)
            if run.status == STATUS_NEEDS_CLARIFICATION:
                return run
        else:
            run.log("Identity", f"Identity confirmed by the salesperson: {run.identity.resolved_note}")
            cb(run)

        stage_research(run)
        cb(run)
        if run.status == STATUS_INSUFFICIENT_EVIDENCE:
            return run

        stage_signal(run)
        cb(run)
        if run.status == STATUS_INSUFFICIENT_EVIDENCE:
            return run

        stage_draft(run)
        cb(run)
        return run

    except MissingCredentials as exc:
        run.status = STATUS_RESEARCH_INCOMPLETE
        run.error = str(exc)
        run.stop_reason = (
            "The research provider is not configured, so no search was performed. "
            "This is a setup problem, not a finding about the prospect."
        )
        run.log(run.stage, f"Research incomplete: {exc}")
        cb(run)
        return run
    except ResearchProviderError as exc:
        run.status = STATUS_RESEARCH_INCOMPLETE
        run.error = str(exc)
        run.stop_reason = (
            "The search provider failed part-way through, so we do not know whether "
            "a usable signal exists. Retry before concluding anything."
        )
        run.log(run.stage, f"Research incomplete: {exc}")
        cb(run)
        return run
    except Exception as exc:  # defensive: never leave a run in 'Running'
        run.status = STATUS_RESEARCH_INCOMPLETE
        run.error = f"{type(exc).__name__}: {exc}"
        run.stop_reason = "The run stopped on an unexpected error. Retry is safe."
        run.log(run.stage, f"Unexpected error: {run.error}")
        cb(run)
        return run


def seller_profile() -> str:
    return SELLER_PROFILE
