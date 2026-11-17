# Edge cases to work through

Fourteen cases the prototype does not yet handle well, with what happens today,
why it matters, and how I would fix each one.

Everything marked **verified** below was reproduced by running the project's own
code on 17 November 2026 — the repro is given so you can see it fail yourself.
Everything marked **inferred** comes from reading the code and has not been
reproduced; treat those as hypotheses to confirm before you spend effort on them.

Nothing here needs a Gemini API key except where it says so.

---

## Triage

| # | Case | Severity | Effort | Status |
| --- | --- | --- | --- | --- |
| 1 | A source that **contradicts** the claim passes verification | **High** | S | verified |
| 2 | The quote stripper can pair quotes across two spans and mangle the body | **High** | S | verified |
| 3 | A short claim can never be verified | Medium | S | verified |
| 4 | Non-Latin and accented text breaks keyword matching | **High** | M | verified |
| 5 | Python validates score *ranges* but not the *rubric* | **High** | M | verified by reading |
| 6 | Quotes shorter than 10 characters bypass the guardrail | Medium | S | verified |
| 7 | Duplicate detection misses short paraphrases of one event | Medium | S | verified |
| 8 | Retry re-runs (and re-pays for) research that already succeeded | Medium | M | verified |
| 9 | One unscored finding fails the whole run | Low | S | by design — read the trade-off |
| 10 | Clarification free text is injected into later prompts unbounded | Medium | S | verified by reading |
| 11 | Stale ranking and an orphaned draft survive a retry that finds nothing | Low | S | verified |
| 12 | A namesake can be confirmed as the prospect | **High** | M | inferred |
| 13 | A prospect who has left the company | Medium | M | inferred |
| 14 | Two tabs on one run: last write wins | Low | S | verified by reading |

Suggested order: **1, 2, 4, 5** first — they are the four places where the app
can state something it has not earned, and 1 and 4 are both false positives in
the same gate. Then 12. The rest are robustness.

---

## 1 · A source that contradicts the claim passes verification

**Today.** `verify.claim_overlap` counts what fraction of the claim's content
words appear anywhere on the page. It has no notion of negation, tense or
attribution. A page saying the opposite of the claim scores high, because it
necessarily reuses the claim's vocabulary.

```bash
python -c "import sys; sys.path.insert(0,'.'); from outreach import verify; print(verify.claim_overlap('Northwind Logistics is hiring an accounts payable manager to handle invoice matching', 'This position has been filled and Northwind Logistics is no longer hiring an accounts payable manager; invoice matching duties were absorbed by the existing team.'))"
```

**Verified:** returns `0.888…`, comfortably over the `0.6` gate. The finding is
then labelled *"Claim corroborated by the source page"* and may be drafted from.

**Why it matters.** This is the one failure the whole provenance design exists to
prevent. The email would open on a vacancy that has been filled, citing the page
that says so. It is also the most likely thing an interviewer will try to break.

**How to solve.** Keyword overlap is the wrong tool for the final gate; it is
fine as a cheap pre-filter. Two layers:

1. **Cheap, deterministic, no API call.** Find the page window where the claim's
   keywords actually cluster (say the best-matching 400 characters) rather than
   scoring the whole document, and reject the finding when that window contains
   a negation or closure cue near the matched terms — `no longer`, `has been
   filled`, `was cancelled`, `former`, `stepped down`, `ceased`, `instead of`.
   This catches the common cases and is testable offline.
2. **The honest fix.** One entailment call per candidate: give the model the
   claim and that window only, and ask `supports` / `contradicts` /
   `does not say`, with the span it relied on. Only `supports` may be drafted
   from; `contradicts` is the strongest possible exclusion and should be shown
   to the reviewer as such, because "the source says the opposite" is more useful
   than "unverified".

Keep the overlap score as the window-finder for step 2, so the entailment call
sees 400 characters instead of 400,000.

**Test.** A fixture page that negates the claim must produce an excluded finding
whose note says the source contradicts it — and, if it was the only finding,
`Insufficient evidence` rather than a draft.

---

## 2 · The quote stripper can pair quotes across two spans

**Today.** `_strip_unverified_quotes` uses one regex, `["“]([^"“”]{10,})["”]`.
When the body contains a short quoted span followed by a longer one, the engine
pairs the *closing* mark of the first with the *opening* mark of the second,
because that is the first match that satisfies the 10-character minimum.

```bash
python -c "import sys; sys.path.insert(0,'.'); from outreach.pipeline import _strip_unverified_quotes; print(_strip_unverified_quotes('You mentioned \"AP chaos\" last month, and that \"the manual matching work is endless\".', ''))"
```

**Verified.** Input:

> You mentioned `"AP chaos"` last month, and that `"the manual matching work is endless"`.

Output — one quotation removed, and the result is *worse* than the input:

> You mentioned `"AP chaos last month, and that the manual matching work is endless"`.

Both invented quotations survived, merged into a single quoted span that the
prospect certainly never said, and the sentence now reads as a direct quote.

**Why it matters.** This is the last guardrail before a human reads the draft. It
currently has a path that manufactures a fabricated quotation out of two smaller
ones. The reviewer sees quotation marks and reasonably assumes the app verified
them — that is the whole contract of the provenance model.

**How to solve.** Stop using a single regex with a length floor. Walk the body
once, collect quote characters in order, pair them 1-2, 3-4, 5-6, and decide per
pair:

- pair reproduces (a substring of) the verified quote → keep the marks;
- anything else → unwrap, whatever its length.

Drop the `{10,}` floor entirely; it exists only to avoid matching apostrophes,
and pairing in document order already solves that. Count every unwrap and log
it, as the current code does. An odd number of quote characters means the model
produced unbalanced output: unwrap them all and log that explicitly rather than
guessing which one is the opener.

**Test.** The repro above, plus: two invented quotes both unwrapped; a verified
quote kept alongside an invented one; an unbalanced single quote character
unwrapped; an apostrophe left alone.

---

## 3 · A short claim can never be verified

**Today.** `_keywords` drops stopwords and anything four characters or shorter.
`company`, `team` and `role` are in the stopword list, so a terse claim reduces
to nothing, and `claim_overlap` returns `0.0` by its own empty-keyword guard.

```bash
python -c "import sys; sys.path.insert(0,'.'); from outreach import verify; print(verify._keywords('She is in the AP team'), verify.claim_overlap('She is in the AP team','She is in the AP team'))"
```

**Verified:** `[] 0.0` — a claim does not verify even against *itself*. Note that
`AP`, the single most relevant token in this domain, is two characters and is
always discarded.

**Why it matters.** A false negative, so it fails safe: the finding is excluded
and the run may end as `Insufficient evidence` when evidence existed. Cheap to
fix, and silent — the reviewer is told the source "does not state this claim",
which is untrue.

**How to solve.** Keep a small domain allowlist that survives the length filter
(`ap`, `po`, `erp`, `sap`, `cfo`, `vp`, `ar`), and lower the floor to three
characters. Then treat a claim with fewer than three usable keywords as
*unscorable rather than unsupported*: a distinct note ("the claim is too short to
verify against a source — ask the extractor for a fuller sentence") instead of
the current wording, which asserts something about the page.

**Test.** `claim_overlap(c, c) == 1.0` for every claim in the fixtures — a
property worth asserting across the board, since it currently fails.

---

## 4 · Non-Latin and accented text breaks keyword matching

**Today.** `_keywords` matches `[a-z0-9][a-z0-9\-']+` after `normalise`, which
lowercases and tidies quotes but does **not** strip accents or handle non-Latin
scripts.

```bash
python -I -X utf8 -c "import sys; sys.path.insert(0,'.'); from outreach import verify; print(verify._keywords('Müller übernimmt die Kreditorenbuchhaltung bei Siemens')); print(verify._keywords('田中さんは買掛金チームを率いています'))"
```

**Verified.** `Müller` becomes `ller`, `übernimmt` becomes `bernimmt`, and the
Japanese claim yields `[]` — so it can never verify, exactly as case 3.

The fragments are worse than useless: `ller` is a substring of `controller`,
`smaller` and `taller`, so an unrelated page can satisfy the gate. That turns a
false negative into a **false positive**:

```bash
python -I -X utf8 -c "import sys; sys.path.insert(0,'.'); from outreach import verify; print(verify.claim_overlap('Müller übernimmt die Kreditorenbuchhaltung', 'the new financial controller joined; Kreditorenbuchhaltung übernimmt neue Aufgaben'))"
```

**Verified:** `1.0`. The claim "Müller takes over accounts payable" is reported as
fully corroborated by a page that never mentions Müller — `ller` matched
`controller`. At `1.0` it clears the gate outright and becomes quotable material.

**Why it matters.** Any European or Asian prospect — a realistic ask for this
product — is either unverifiable or verifiable against the wrong page. It also
means the prototype quietly assumes English-language sources.

**How to solve.** Normalise with Unicode NFKD and strip combining marks so
`Müller` → `muller` on both sides of the comparison, and widen the token regex to
`\w` with `re.UNICODE`. For CJK, word boundaries do not exist, so fall back to
character n-grams (3-grams work well) when a claim produces no word tokens —
overlap then compares n-gram sets instead. Decide deliberately whether
non-English sources are in scope and say so in the README either way; "we only
support English sources today" is a perfectly good answer, but it should be a
stated limitation rather than an accident of a regex.

**Test.** `Müller` and `muller` produce the same keywords; the accented claim
verifies against its own text and does *not* verify against a page about a
"controller"; a CJK claim verifies against its own text.

---

## 5 · Python validates score ranges but not the rubric

**Today.** `_parse_scores` is strict about *shape*: unknown, duplicate and
missing `finding_id`s, missing components, non-integers and out-of-range values
are all rejected. It says nothing about whether a score is *consistent with the
finding it describes*. Two gaps follow directly:

- The rubric says timeliness `0` means "stale or undated", but a finding with
  `date == ""` can be given timeliness `2` and nothing objects.
- The rubric says product relevance `3` means "explicitly concerns
  invoice-to-PO matching or discrepancy review", but a claim that never mentions
  invoices, purchase orders or discrepancies can be given `3`.

Both are reachable by reading `_parse_scores` — the only per-value check is
`0 <= raw <= maximum`.

**Why it matters.** The project's defence of its own number is "the model gives
the integers, Python does the arithmetic and the gates". That defence is weaker
than it sounds while Python never checks the integers against the evidence. This
is the case most likely to be probed in an interview, because the README makes
the claim explicitly.

**How to solve.** A `_sanity_check_scores` pass between parsing and eligibility,
applying only rules that are decidable from data already on the `Finding`:

| Condition | Action |
| --- | --- |
| `finding.date` is empty and `kind` is not an open role | cap timeliness at `1` |
| the claim and verified quote contain no invoice / PO / three-way-match / discrepancy term | cap product relevance at `2` |
| `finding.provenance` is a search summary, not source text | cap evidence quality at `1` |

That last one is almost free: the rubric's `2` is "a direct source", which is
precisely what `PROV_SOURCE_TEXT` already means, so Python can decide it rather
than asking the model.

Cap, do not reject — a cap is explainable, and the reviewer should see it. Write
the reason into `Score.reasons` ("capped from 2: the source gives no date") and
log it, so the screen shows what was overridden and why. Rejecting instead would
burn the retry and end good runs as `Research incomplete`.

Keep these rules narrow and evidence-based. The temptation is to start scoring in
Python; the point is only to stop the model claiming something the finding
visibly does not support.

**Test.** An undated finding scored `timeliness: 2` ends up with `1` and a stated
reason; a claim with no AP vocabulary cannot reach product relevance `3`; a
paraphrase-provenance finding cannot reach evidence quality `2`; a well-formed
score is passed through untouched.

---

## 6 · Quotes shorter than 10 characters bypass the guardrail

**Today.** The `{10,}` floor in the stripper means `"AP chaos"` — eight
characters — is never examined. An invented short quotation reaches the reviewer
in quotation marks.

**Why it matters.** Short quotes are the plausible ones. `"AP chaos"`,
`"a nightmare"`, `"three-way match hell"` all read like something a person
actually said.

**How to solve.** Fixed by case 2's rewrite: pairing in document order removes
the need for a length floor. Worth listing separately so it gets its own test.

**Test.** `_strip_unverified_quotes('He called it "AP chaos".', '')` unwraps it.

---

## 7 · Duplicate detection misses short paraphrases of one event

**Today.** `_duplicate_of` requires `claim_overlap >= 0.8` in **both**
directions. Short claims have few keywords, so one differing word drops the
ratio below the threshold.

```bash
python -c "import sys; sys.path.insert(0,'.'); from outreach import verify; print(verify.claim_overlap('Priya leads the AP team','Priya joined the AP team'))"
```

**Verified:** `0.5` each way — two reports of effectively one fact take two
separate ranks.

**Why it matters.** Mild. The reviewer sees the same fact twice and the ranked
list looks padded. The opposite error also exists: two long claims that share
boilerplate ("Northwind Logistics, the Chicago-based third-party logistics
provider, …") can exceed `0.8` while describing genuinely different events, and
one is then wrongly set aside. A fixed keyword-ratio threshold is simply the
wrong shape for this job.

**How to solve.** Compare *events*, not sentences. The extractor already returns
`kind`, `url` and `date`; treat two findings as the same event when they share a
URL, or share `kind` and a date within a week, or when their claims overlap
heavily **and** are of comparable length. Make the length guard explicit:
require both claims to have at least four usable keywords before the overlap
threshold is trusted at all, and fall back to "not a duplicate" below that,
because a false merge loses a signal while a false split merely repeats one.

**Test.** The pair above is not merged; two long claims sharing only a company
boilerplate preamble are not merged; two findings on one URL about one posting
are merged.

---

## 8 · Retry re-runs research that already succeeded

**Today.** The retry button sets `retry_run`, and `view_research` calls
`run_live(run, skip_identity=run.identity.status == "confirmed")`. `execute` then
restarts at `stage_research` — a fresh grounded search — even when the previous
attempt's research and verification succeeded and only the scoring call failed.
Sources accumulate across attempts, because `_merge_sources` appends.

**Why it matters.** Case 5's failure mode (`Research incomplete` from malformed
scoring) is exactly the one where retrying is attractive, and it is also the one
where nothing about the research needs redoing. Every retry pays for grounded
search again, and a live demo is where that is most likely to happen.

**How to solve.** The stages are already separable; the orchestrator just does
not know what is still good. Record the furthest completed stage on the `Run`
(`research_complete`, say, set at the end of `stage_research`), and give
`execute` a `resume_from` that skips any stage already complete, in the same
spirit as the existing `skip_identity`. The retry button then resumes from
scoring, and the log should say so — "reusing the research from the previous
attempt" — because a reviewer needs to know the sources were not re-fetched.
Guard `_merge_sources` against re-adding on resume while you are there.

**Test.** A run that fails at scoring, then retries, makes **no** further
`grounded_search` call and exactly one more `json_call`; the source list does not
grow.

---

## 9 · One unscored finding fails the whole run

**Today.** `_parse_scores` requires a row for every candidate. If the model
returns two of three, the run retries once and then becomes
`Research incomplete` — including the two findings that *were* scored correctly.

**This is deliberate**, and the brief asked for it: reject missing ids rather
than guess. It is listed here so the trade-off is on the record rather than
discovered under questioning.

**The argument for leaving it.** Partial scoring means ranking a subset while
silently ignoring a candidate the reviewer can see on screen. "I scored two of
your three findings and will not say why" is a worse product than "scoring
failed, retry".

**The argument for softening it.** `MAX_FINDINGS` is 3, so one dropped row
discards two good findings and the whole research spend.

**If you soften it**, do it visibly: accept a partial set only when at least one
row validates, mark every unscored finding `EXCLUDED` with the reason "the
scoring step returned no score for this finding", and show that in the ranked
list. Never let an unscored finding be silently absent. I would keep it strict
for the demo and mention the trade-off out loud — it is a stronger answer than
either implementation.

---

## 10 · Clarification free text is injected into later prompts unbounded

**Today.** The clarification box writes `identity.resolved_note`, which `_hints`
pastes verbatim into the research prompt, and `skip_identity=True` means no
identity check runs afterwards. There is no length limit and no cap on how many
times a run can be clarified and re-run.

**Why it matters.** Two separate problems sharing one cause. The reviewer's text
is typed by a trusted user, so this is not an attack scenario — but it is an
accuracy one: a note like "he's the one who runs their invoice automation
programme" is pasted into the prompt as given and can seed research with an
assertion nobody verified, which then comes back as a "finding". Second, each
clarification round costs another grounded search with no ceiling.

**How to solve.** Cap the note at a few hundred characters, strip newlines, and
label it inside the prompt as *an unverified hint from the salesperson, not
evidence* — the prompts already separate verified from unverified material, and
this is the one input that bypasses that discipline. Cap the clarification rounds
per run (two is plenty) and say so in the UI. Worth asserting in a test that a
hint's wording cannot reach the draft except through a verified finding.

---

## 11 · Stale ranking and an orphaned draft survive a retry that finds nothing

**Today.** `execute` does not reset ranking state at the start of a run. When a
retry's research comes back empty, `stage_research` sets `run.findings = []` and
the status to `Insufficient evidence`, but `scores`, `ranking`, `recommended_id`,
`active_id` and `draft` all still hold the previous attempt's values.

**Verified.** After that sequence, `has_ranking()` returns `True` with zero
findings, and `run.draft` still carries the earlier subject and body.

The damage is limited: `ranked_findings` skips ids it cannot resolve and returns
`[]`, the history row degrades to "no signal selected", and the
`Insufficient evidence` screen shows no draft. So **nothing wrong is displayed
today** — but a run is saved whose payload contains a draft it is not entitled
to, and any future code that trusts `has_ranking()` inherits the bug.

**How to solve.** Clear `scores`, `ranking`, `recommended_id`, `active_id`,
`checks`, `selection_reason` and `draft` at the top of `execute` (and keep them
when resuming, per case 8 — the reset belongs to "starting a stage", not
"starting a function"). Then make `has_ranking()` require that at least one id in
`ranking` resolves to a finding.

**Test.** A run that ranked, then re-ran and found nothing, has no draft and
`has_ranking() is False`.

---

## 12 · A namesake can be confirmed as the prospect

**Today.** `stage_identity` asks the model for `confirmed` / `ambiguous` /
`not_found` and Python trusts the verdict; any status other than `confirmed`
routes to clarification. Nothing independently checks that the sources behind a
`confirmed` verdict actually tie the person to *this company*.

**Inferred** — not reproduced, because it needs a live call. It is the highest
remaining risk, so confirm it early with a deliberately ambiguous real name.

**Why it matters.** Every downstream gate protects the *claim*; none protects the
*person*. An email about the right fact and the wrong human is the worst output
the app can produce, and it is the failure a salesperson would be most
embarrassed by. Worth noting that prospect relevance `3` ("the person owns or
publicly discussed this initiative") is scored on the assumption that identity
was settled — so a namesake error propagates straight into the top score.

**How to solve.** Make `confirmed` provable from the sources rather than
asserted. Require the model to name which source ids establish the
person-at-company link, validate those ids against `run.sources` the same way
finding URLs are validated in `stage_research`, and require at least one of those
pages to mention both the name and the company. No corroborating source, no
`confirmed` — route to clarification, which already exists and is the right
destination. Where a company's own domain appears among the sources, weight it
above third parties.

**Test.** A `confirmed` verdict citing a source id that is not in the run's
sources is treated as ambiguous; a verdict whose cited page mentions the name but
not the company is treated as ambiguous.

---

## 13 · A prospect who has left the company

**Today.** Findings are tied to the person and to the company independently.
Nothing checks that the person still works there, and the timeliness component
scores *the finding's* date, not the employment relationship.

**Inferred.** The plausible bad output: a 2024 interview given while at a
previous employer, scored `prospect_relevance: 3` because she clearly discussed
it herself, producing an email to her at a company she left.

**Why it matters.** Cheap to produce, mortifying to send, and invisible to every
gate currently in place. It is also the natural follow-up question to case 12.

**How to solve.** Two parts, and the first is nearly free: carry the employer the
*source* attributes to the person, and refuse to draft when a finding's implied
employer differs from `run.company` — the extractor can return it, and a
mismatch is a stronger exclusion than any score. Then treat the identity stage's
most recent corroborating source as an "as of" date and surface it beside the
prospect's name, so the reviewer sees how fresh the employment evidence is rather
than assuming it. Do not try to prove current employment from search results; the
honest move is to show the reviewer what the evidence is and let them judge.

**Test.** A finding whose source places the prospect at a different employer is
excluded with that reason, not merely ranked low.

---

## 14 · Two tabs on one run: last write wins

**Today.** `store.save` upserts on `run_id`, so two browser tabs with the same
run open will each write the whole payload. The second save silently overwrites
the first — approve in one tab, save an edit in the other, and the decision can
disappear.

**Verified by reading** `save` and the schema; not reproduced.

**Why it matters.** Low for a single-operator prototype, and worth saying so
plainly rather than pre-building for it. It is the first thing that breaks if
this becomes a team tool, which makes it a good "what would you do next" answer.

**How to solve.** Add a monotonic `revision` to the payload, make the update
conditional on the revision you loaded, and on conflict reload and tell the
reviewer the run changed elsewhere rather than merging. Not worth building now;
worth knowing the shape of.

---

## Where these came from

Cases 1, 2, 3, 4, 7 and 11 were reproduced against the current code with the
snippets above. Case 5's two gaps follow from `_parse_scores` performing only
range checks. Cases 10 and 14 are read off `_hints` / `execute` and
`store.save`. Cases 12 and 13 are reasoned from the identity stage's structure
and need a live run to confirm — which is also the first thing an API key buys
you beyond the two live checks already listed in `HANDOFF.md`.
