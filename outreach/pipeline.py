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
from .config import MAX_FINDINGS
from .gemini_client import (
    GroundedResult,
    MissingCredentials,
    ResearchProviderError,
    grounded_search,
    json_call,
)
from .schema import (
    CONTEXT_ONLY,
    ELIGIBLE,
    EXCLUDED,
    MIN_PRODUCT_RELEVANCE,
    PROV_SOURCE_TEXT,
    SCORE_COMPONENTS,
    SCORE_MAX,
    STATUS_AWAITING_REVIEW,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_RESEARCH_INCOMPLETE,
    STATUS_RUNNING,
    Check,
    Draft,
    Finding,
    Identity,
    Product,
    Run,
    Score,
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
            seller=prompts.seller_block(run.product),
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

    # Stable ids before anything refers to a finding -- scoring, the UI and the
    # stored run all key off these rather than a list position.
    run.findings = findings
    _assign_finding_ids(run)

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
# Stage 3 -- score every candidate, then rank in Python
# ---------------------------------------------------------------------------
class ScoringFormatError(RuntimeError):
    """The scoring call came back in a shape we refuse to guess at."""


def _assign_finding_ids(run: Run) -> None:
    """Give every finding a stable id before anything refers to it."""
    used: set[str] = set()
    for i, finding in enumerate(run.findings, start=1):
        if not finding.finding_id or finding.finding_id in used:
            finding.finding_id = f"f-{i}"
        used.add(finding.finding_id)


def _format_candidates_for_prompt(candidates: list[Finding]) -> str:
    blocks = []
    for f in candidates:
        quote = (
            f'\n  verified quote from the source: "{f.quote}"'
            if f.quote_verified and f.quote
            else ""
        )
        blocks.append(
            f"finding_id: {f.finding_id}\n"
            f"  claim: {f.claim}\n"
            f"  publisher: {f.publisher or 'unknown'}\n"
            f"  kind: {f.kind or 'unknown'}\n"
            f"  date the source gives: {f.date or 'none stated'}\n"
            f"  url: {f.url}\n"
            f"  how it was verified: {f.verification_note}{quote}"
        )
    return "\n\n".join(blocks)


def _parse_scores(
    payload: object, expected_ids: list[str], product: Product
) -> list[Score]:
    """Validate the model's scoring output. Raises ``ScoringFormatError``.

    Rejects a missing, duplicate or unknown finding_id, a missing component, a
    non-integer and anything outside the rubric's range. A finding scored 2 or
    3 for product relevance must also name one of ``product``'s own listed
    capabilities and give a reason, so the model cannot assert a product
    connection without saying which capability it means.

    There is deliberately no "near enough" path: invalid output is retried
    once, and then the run stops as "Research incomplete" rather than being
    quietly repaired.
    """
    if not isinstance(payload, dict):
        raise ScoringFormatError("the scoring call did not return a JSON object")
    rows = payload.get("scores")
    if not isinstance(rows, list) or not rows:
        raise ScoringFormatError('the scoring call returned no "scores" list')

    expected = list(expected_ids)
    seen: dict[str, Score] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ScoringFormatError("a score entry was not a JSON object")
        fid = str(row.get("finding_id", "")).strip()
        if not fid:
            raise ScoringFormatError("a score entry had no finding_id")
        if fid not in expected:
            raise ScoringFormatError(f"unknown finding_id {fid!r} in the scoring output")
        if fid in seen:
            raise ScoringFormatError(f"finding_id {fid!r} was scored twice")

        values: dict[str, int] = {}
        reasons: dict[str, str] = {}
        for key, label, maximum in SCORE_COMPONENTS:
            if key not in row:
                raise ScoringFormatError(f"{fid}: missing {label.lower()} score")
            raw = row[key]
            if isinstance(raw, bool) or not isinstance(raw, int):
                # A float is accepted only when it is exactly an integer.
                if isinstance(raw, float) and float(raw).is_integer():
                    raw = int(raw)
                else:
                    raise ScoringFormatError(f"{fid}: {label.lower()} was not an integer")
            if not 0 <= raw <= maximum:
                raise ScoringFormatError(
                    f"{fid}: {label.lower()} was {raw}, outside 0-{maximum}"
                )
            values[key] = int(raw)
            reasons[key] = str(row.get(f"{key}_reason", "")).strip()

        # A claimed product connection has to name the capability it rests on.
        capability = str(row.get("capability", "") or "").strip()
        if values["product_relevance"] >= MIN_PRODUCT_RELEVANCE:
            if not capability:
                raise ScoringFormatError(
                    f"{fid}: product relevance {values['product_relevance']} with no "
                    "capability named"
                )
            matched = product.matches_capability(capability)
            if not matched:
                raise ScoringFormatError(
                    f"{fid}: {capability!r} is not a capability of "
                    f"{product.name}"
                )
            capability = matched
            if not reasons["product_relevance"]:
                raise ScoringFormatError(
                    f"{fid}: product relevance {values['product_relevance']} with no "
                    "reason given"
                )
        else:
            # Below the threshold nothing is claimed, so nothing is named.
            capability = ""

        seen[fid] = Score(
            finding_id=fid, reasons=reasons, capability=capability, **values
        )

    missing = [fid for fid in expected if fid not in seen]
    if missing:
        raise ScoringFormatError("no score for " + ", ".join(missing))
    return [seen[fid] for fid in expected]


def _duplicate_of(finding: Finding, kept: list[Finding]) -> Finding | None:
    """A finding reporting the same event as one already kept.

    Two sources covering one announcement should not occupy two ranks, so the
    weaker one is set aside rather than shown twice.
    """
    for other in kept:
        if (
            verify.claim_overlap(finding.claim, other.claim) >= 0.8
            and verify.claim_overlap(other.claim, finding.claim) >= 0.8
        ):
            return other
    return None


def _apply_eligibility(run: Run, scores: list[Score]) -> None:
    """Decide what each scored finding may be used for.

    Verification comes first: a model score can never promote a finding whose
    source did not support the claim. After that the gates are about the
    selected product, so the same finding can be usable for one product and
    background only for another.
    """
    product = run.product
    for score in scores:
        finding = run.finding_by_id(score.finding_id)
        if finding is None:
            continue
        if not verify.is_usable(finding):
            score.eligibility = EXCLUDED
            score.eligibility_reason = (
                "No source supports this claim, so it cannot be ranked or drafted "
                f"from. {finding.verification_note}"
            )
            continue
        if score.evidence_quality == 0:
            score.eligibility = EXCLUDED
            score.eligibility_reason = (
                "Scored 0 for evidence quality - unsupported or contradicted by the "
                "source, so it is excluded from ranking and drafting."
            )
            continue
        if score.product_relevance < MIN_PRODUCT_RELEVANCE:
            score.eligibility = CONTEXT_ONLY
            score.eligibility_reason = (
                f"Product relevance {score.product_relevance} of 3: the source does not "
                f"describe a task {product.name} handles"
                + (
                    f" — {score.reasons['product_relevance'].strip().rstrip('.')}"
                    if score.reasons.get("product_relevance") else ""
                )
                + ". Useful background, but not something to write about."
            )
            continue
        if score.prospect_relevance == 0:
            score.eligibility = CONTEXT_ONLY
            score.eligibility_reason = (
                "Nothing shows this concerns the prospect's own work, so it is "
                "background only and cannot generate a draft."
            )
            continue
        score.eligibility = ELIGIBLE
        score.eligibility_reason = ""


def rank_scores(run: Run, scores: list[Score]) -> list[str]:
    """Order the findings for display and store that order on the run.

    Eligible signals by total descending, tie-broken on product relevance, then
    prospect relevance, then evidence quality, then timeliness, then the
    original research order. Context-only and excluded findings always sit
    below the eligible ones, however high their raw total.
    """
    order = {f.finding_id: i for i, f in enumerate(run.findings)}

    def key(score: Score) -> tuple:
        # Negated so a higher score sorts first, while the original research
        # order still breaks a complete tie ascending.
        return tuple(-v for v in score.sort_key()) + (order.get(score.finding_id, 0),)

    eligible = sorted((s for s in scores if s.eligibility == ELIGIBLE), key=key)
    context = sorted((s for s in scores if s.eligibility == CONTEXT_ONLY), key=key)
    excluded = sorted((s for s in scores if s.eligibility == EXCLUDED), key=key)

    ordered = eligible + context + excluded
    run.scores = ordered
    run.ranking = [s.finding_id for s in ordered]
    return run.ranking


def _checks_from_score(run: Run, score: Score) -> list[Check]:
    """The rubric components as checks a reviewer can argue with."""
    return [
        Check(
            name=label,
            passed=value > 0,
            reason=f"{value} of {maximum} - {reason or 'no reason given'}",
        )
        for _, label, value, maximum, reason in score.components()
    ]


def _shorten(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def winner_rationale(run: Run) -> str:
    """One plain sentence on why the top signal ranked first."""
    eligible = [(f, s) for _, f, s in run.ranked_findings(ELIGIBLE)]
    if not eligible:
        return ""
    _, top = eligible[0]
    if len(eligible) == 1:
        bits = [
            f"{label.lower()} {value} of {maximum}" + (f" ({reason})" if reason else "")
            for _, label, value, maximum, reason in top.components()
            if value > 0
        ]
        return (
            "It is the only finding that qualifies as a reason to write: "
            + ", ".join(bits)
            + f" — {top.total} of {SCORE_MAX} overall."
        )

    runner_finding, runner = eligible[1]
    gaps = sorted(
        (
            (value - int(getattr(runner, key)), label, value, int(getattr(runner, key)), reason)
            for key, label, value, _, reason in top.components()
        ),
        key=lambda g: g[0],
        reverse=True,
    )
    best = gaps[0]
    runner_claim = _shorten(runner_finding.claim, 70)

    if top.total == runner.total:
        return (
            f"It ties the runner-up on {top.total} of {SCORE_MAX} and wins on the first "
            f"tie-break: {best[1].lower()} {best[2]} against {best[3]} "
            f"(“{runner_claim}”)."
        )
    if best[0] <= 0:
        return (
            f"It scores {top.total} of {SCORE_MAX} against {runner.total} for the "
            f"runner-up (“{runner_claim}”)."
        )
    detail = f" — {best[4].rstrip('.')}" if best[4] else ""
    return (
        f"It scores {top.total} of {SCORE_MAX} against {runner.total} for the runner-up "
        f"(“{runner_claim}”), mainly on {best[1].lower()}: {best[2]} against "
        f"{best[3]}{detail}."
    )


def why_it_matters(run: Run, score: Score) -> str:
    """One plain sentence tying the finding to this person and one capability.

    Built from the model's own two reasons plus the capability it named, so it
    asserts nothing that was not already scored and shown.
    """
    product = score.reasons.get("product_relevance", "").strip().rstrip(".")
    prospect = score.reasons.get("prospect_relevance", "").strip().rstrip(".")
    clauses = [c for c in (product, prospect) if c]
    if not clauses:
        return ""
    sentence = "; ".join(clauses) + "."
    # The model is asked to name the capability in its reason, so only spell it
    # out again when it did not.
    if score.capability and score.capability.lower() not in sentence.lower():
        sentence += f" That is one thing {run.product.name} does: {score.capability.lower()}."
    return sentence


def stage_score(run: Run) -> None:
    """Score every candidate, then rank them. One model call, retried once."""
    _assign_finding_ids(run)
    candidates = [f for f in run.findings if verify.is_usable(f)]
    run.log(
        "Signal selection",
        f"Scoring {len(candidates)} verified finding(s) against the 10-point rubric "
        f"for {run.product.name}.",
    )

    prompt = prompts.SIGNAL_SCORE.format(
        seller=prompts.seller_block(run.product),
        name=run.prospect_name,
        role_line=_role_line(run),
        company=run.company,
        findings=_format_candidates_for_prompt(candidates),
    )
    expected_ids = [f.finding_id for f in candidates]

    scores: list[Score] = []
    first_error = ""
    for attempt in (1, 2):
        try:
            scores = _parse_scores(json_call(prompt), expected_ids, run.product)
            break
        except ScoringFormatError as exc:
            first_error = first_error or str(exc)
            if attempt == 1:
                run.log(
                    "Signal selection",
                    f"Scoring output was invalid ({exc}). Retrying once.",
                )
                continue
            raise ResearchProviderError(
                "The scoring step returned unusable output twice "
                f"({first_error}; then {exc}). Nothing was scored and no signal was "
                "chosen - this is a provider problem, not a finding about the prospect."
            ) from exc

    # Findings that failed verification were never sent for scoring. Record them
    # at zero so the reviewer can still see they were considered and why not.
    for finding in run.findings:
        if finding.finding_id not in expected_ids:
            scores.append(
                Score(
                    finding_id=finding.finding_id,
                    reasons={
                        key: "not scored - the claim is not supported by its source"
                        for key, _, _ in SCORE_COMPONENTS
                    },
                )
            )

    _apply_eligibility(run, scores)

    # Set aside a second report of an event that is already ranked.
    kept: list[Finding] = []
    for score in sorted(
        (s for s in scores if s.eligibility == ELIGIBLE),
        key=lambda s: tuple(-v for v in s.sort_key()),
    ):
        finding = run.finding_by_id(score.finding_id)
        if finding is None:
            continue
        duplicate_of = _duplicate_of(finding, kept)
        if duplicate_of is not None:
            score.eligibility = EXCLUDED
            score.eligibility_reason = (
                "Reports the same event as a higher-scoring finding "
                f"({duplicate_of.finding_id}), so it is not ranked separately."
            )
            run.log(
                "Signal selection",
                f"{score.finding_id} reports the same event as {duplicate_of.finding_id}; "
                "kept the better-scored one.",
            )
            continue
        kept.append(finding)

    rank_scores(run, scores)
    eligible = run.ranked_findings(ELIGIBLE)
    context_only = run.ranked_findings(CONTEXT_ONLY)

    if not eligible:
        run.selected_index = -1
        run.active_id = ""
        run.recommended_id = ""
        run.checks = []
        run.status = STATUS_INSUFFICIENT_EVIDENCE
        details = []
        if context_only:
            details.append(
                f"{len(context_only)} finding(s) are real but context only: "
                + "; ".join(
                    f"“{_shorten(f.claim, 70)}” ({s.total} of {SCORE_MAX}, "
                    + s.eligibility_reason.rstrip(".").lower()
                    + ")"
                    for _, f, s in context_only
                )
            )
        excluded = run.ranked_findings(EXCLUDED)
        if excluded:
            details.append(f"{len(excluded)} finding(s) were excluded before ranking")
        run.stop_reason = (
            f"Research completed and the findings were scored for {run.product.name}, "
            "but none of them both describes a task this product handles and concerns "
            "this person's own work, so there is no honest reason to write about it. "
            "Another product may fit this prospect better. "
            + (". ".join(details) + "." if details else "")
        ).strip()
        run.log(
            "Signal selection",
            "No eligible signal after scoring. Stopping with 'Insufficient evidence'.",
        )
        return

    _, top_finding, top_score = eligible[0]
    run.recommended_id = top_finding.finding_id
    run.set_active_finding(top_finding.finding_id)
    run.checks = _checks_from_score(run, top_score)
    run.selection_reason = winner_rationale(run)
    run.log(
        "Signal selection",
        f"Ranked {len(eligible)} eligible signal(s); recommending {top_finding.finding_id} "
        f"at {top_score.total} of {SCORE_MAX}."
        + (f" {len(context_only)} context-only finding(s) below." if context_only else ""),
    )


# ---------------------------------------------------------------------------
# Stage 4 -- draft
# ---------------------------------------------------------------------------
def stage_draft(run: Run, *, chosen_by_reviewer: bool = False) -> None:
    """Write the email from whichever finding is active on the run."""
    finding = run.selected_finding()
    if finding is None:
        raise ResearchProviderError("No signal was selected, so there is nothing to draft.")

    score = run.score_for(finding.finding_id)
    if score is not None and score.eligibility != ELIGIBLE:
        raise ResearchProviderError(
            f"{finding.finding_id} is {score.eligibility.replace('_', ' ')} and cannot "
            "generate a draft: " + score.eligibility_reason
        )

    run.log(
        "Draft",
        "Writing a first-contact email from the selected evidence, for "
        f"{run.product.name}.",
    )
    quotable = finding.quote_verified and finding.provenance == PROV_SOURCE_TEXT and finding.quote
    capability = (score.capability if score is not None else "") or ""

    payload = json_call(
        prompts.DRAFT_EMAIL.format(
            seller=prompts.seller_block(run.product),
            capability_line=(
                f"  The capability this connects to: {capability}\n"
                if capability else ""
            ),
            name=run.prospect_name,
            role_line=_role_line(run),
            company=run.company,
            claim=finding.claim,
            publisher=finding.publisher or "unknown publisher",
            date_line=f"\n  Dated: {finding.date}" if finding.date else "",
            url=finding.url,
            quote_line=f'  Verified quote: "{finding.quote}"' if quotable else "",
            selection_reason=(
                "the salesperson reviewing this run chose this signal themselves."
                if chosen_by_reviewer
                else run.selection_reason or "it is the only verified finding."
            ),
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

    run.draft = Draft(subject=subject, body=body, finding_id=finding.finding_id)
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
# Switching signals after review has started
# ---------------------------------------------------------------------------
class SignalNotEligible(RuntimeError):
    """The reviewer asked for a signal that cannot produce a draft."""


def redraft(run: Run, finding_id: str, *, draft_fn=None) -> Run:
    """Rewrite the draft from a different finding on the SAME run.

    Reuses the research and the scores already on the run: no search, no
    scoring call, no new run. On failure the previous draft and the signal it
    was written from are both restored, so a reviewer never ends up looking at
    one signal's evidence beside another signal's email.

    ``draft_fn`` exists so a fixture run can supply a canned draft instead of
    calling the model; live runs leave it as None.
    """
    score = run.score_for(finding_id)
    finding = run.finding_by_id(finding_id)
    if finding is None:
        raise SignalNotEligible(f"{finding_id} is not a finding on this run.")
    if score is None:
        raise SignalNotEligible(f"{finding_id} was never scored, so it cannot be used.")
    if score.eligibility != ELIGIBLE:
        raise SignalNotEligible(
            f"{finding_id} is {score.eligibility.replace('_', ' ')} and cannot generate "
            "a draft: " + score.eligibility_reason
        )

    # Snapshot exactly what we would have to put back.
    before = {
        "draft": run.draft.to_dict(),
        "active_id": run.active_id,
        "selected_index": run.selected_index,
        "checks": [c.to_dict() for c in run.checks],
        "status": run.status,
        "stage": run.stage,
    }

    run.set_active_finding(finding_id)
    run.checks = _checks_from_score(run, score)
    run.log(
        "Draft",
        f"Salesperson switched to {finding_id} ({score.total} of {SCORE_MAX}). "
        f"Still selling {run.product.name}; reusing the saved research and scores "
        "— no new search.",
    )
    try:
        if draft_fn is not None:
            draft = draft_fn(run, finding)
            if draft is None:
                raise ResearchProviderError(
                    "No draft is available for this signal in fixture mode."
                )
            draft.finding_id = finding_id
            run.draft = draft
            run.status = STATUS_AWAITING_REVIEW
            run.log(
                "Human review",
                "Draft rewritten from the chosen signal; it needs a fresh approval.",
            )
        else:
            stage_draft(run, chosen_by_reviewer=True)
    except Exception as exc:
        run.draft = Draft.from_dict(before["draft"])
        run.active_id = before["active_id"]
        run.selected_index = before["selected_index"]
        run.checks = [Check.from_dict(c) for c in before["checks"]]
        run.status = before["status"]
        run.stage = before["stage"]
        run.error = f"{type(exc).__name__}: {exc}"
        run.log(
            "Human review",
            "Could not rewrite the draft from the chosen signal, so the previous draft "
            f"and its original signal were kept. {run.error}",
        )
        raise

    # A regenerated draft has not been reviewed yet.
    run.draft.decision = ""
    run.draft.decided_at = ""
    run.error = ""
    return run


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

        stage_score(run)
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


def seller_profile(run: Run) -> str:
    """The one-sentence description of what this run is selling."""
    return run.product.description
