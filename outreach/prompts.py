"""Prompt templates. Kept in one place so the reviewer can read the rules."""

from __future__ import annotations

from .config import SELLER_CAPABILITIES, SELLER_PROFILE

GROUNDING_RULES = """
Hard rules:
- Use only what the search results actually say. Never invent a quote, a date,
  a URL, a publisher, or a search result.
- If you did not find something, say so plainly. An empty answer is correct and
  useful; a plausible-sounding guess is a failure.
- Do not speculate about what a company needs, buys, or struggles with.
""".strip()

SELLER_BLOCK = f"""
What we sell (this is the complete and only description of our product):
"{SELLER_PROFILE}"

Our stated capabilities, in full:
- {SELLER_CAPABILITIES[0]}
- {SELLER_CAPABILITIES[1]}

You must not attribute any other capability, customer, metric, or saving to us.
""".strip()

# ---------------------------------------------------------------------------
# Stage 1 -- identity
# ---------------------------------------------------------------------------
IDENTITY_SEARCH = """
Find public evidence about who this person is and where they currently work.

Person: {name}
Stated company: {company}
{hints}

Search for their current employer and role. Report:
1. Every distinct person you find matching this name in a professional context,
   with their employer and role, and where that came from.
2. Whether any source connects this name to "{company}".
3. Any disagreement between sources about the current employer (for example an
   older page showing a previous employer, or a newer announcement showing a move).

{rules}
""".strip()

IDENTITY_JUDGE = """
You are deciding whether the research below identifies ONE specific person at a
specific company, well enough for a salesperson to write to them.

Person asked for: {name}
Company asked for: {company}
{hints}

Research summary (a search-result summary written by a model, not source text):
---
{research}
---

Sources cited by the search:
{sources}

Decide one status:
- "confirmed": the evidence connects this name to {company} and there is no
  meaningful competing candidate or employer conflict.
- "ambiguous": several different people fit the name, OR sources disagree about
  this person's current employer, OR the only evidence is weak/indirect.
- "not_found": no credible public evidence about this person at all.

Return JSON only:
{{
  "status": "confirmed" | "ambiguous" | "not_found",
  "confidence_reason": "one sentence citing what the evidence shows",
  "ambiguity": "if ambiguous: one or two sentences a salesperson can act on, naming the competing options or the conflict. Empty string otherwise.",
  "candidates": [
    {{"description": "name, role, employer", "why": "what source suggests this", "url": "url from the list above or empty"}}
  ]
}}
Use at most 4 candidates. Only include a url that appears in the source list.
""".strip()

# ---------------------------------------------------------------------------
# Stage 2 -- candidate signals
# ---------------------------------------------------------------------------
RESEARCH_SEARCH = """
Research what this person and their team are publicly doing right now.

Person: {name}
Company: {company}
{role_line}
{hints}
{identity_note}

Look for, in this order of usefulness:
1. The person's own public statements -- interviews, podcasts, conference talks,
   bylined posts, quotes in press releases.
2. Evidence of what their team is doing -- active job postings for their team,
   official company pages about their function, product or process announcements.
3. Company news that plausibly touches their responsibilities -- funding,
   expansion, acquisitions, new systems, new markets, new entities.

Prefer official company pages, active job postings, announcements and interviews.
For each thing you find, state: the specific fact, who published it, the URL, and
the date if the page gives one.

{rules}
""".strip()

RESEARCH_EXTRACT = """
Turn the research below into at most {max_findings} separate, specific findings.

Person: {name}
Company: {company}
{role_line}

Research summary (model-written summary of search results -- NOT source text):
---
{research}
---

Sources the search cited (use these URLs and nothing else):
{sources}

A good finding is one concrete, checkable fact. Bad: "the company is growing".
Good: "Posted a job opening for an Accounts Payable Specialist in Pune on 3 March".

Return JSON only:
{{
  "findings": [
    {{
      "claim": "one sentence stating the specific fact, in your own words",
      "publisher": "who published it, e.g. 'Acme careers site' or 'TechCrunch'",
      "url": "exact URL copied from the source list above",
      "date": "date the source gives, as written, or empty string if none",
      "kind": "job posting | announcement | interview | official page | news | other",
      "quote": "a short verbatim sentence from the source if the research clearly contains one, otherwise empty string"
    }}
  ]
}}

Rules:
- Every finding must have a url copied exactly from the source list. Drop any
  finding you cannot attribute to one of those URLs.
- Leave "date" empty rather than guessing. Leave "quote" empty unless you are
  reproducing words verbatim.
- Return {{"findings": []}} if the research contains nothing specific.
""".strip()

# ---------------------------------------------------------------------------
# Stage 3 -- signal selection
# ---------------------------------------------------------------------------
SIGNAL_SELECT = """
Pick the single strongest signal for first-contact outreach, and score it.

{seller}

Prospect: {name}{role_line} at {company}

Verified findings (each is backed by the source shown; index is 0-based):
{findings}

Definitions you must respect:
- A SIGNAL is a verified fact about the prospect or their team.
- A HOOK is the connection between that fact, this person's responsibilities, and
  our offer. A hook is an opening for a question, never a claim about their needs.

Choose the finding that gives the best hook. Then answer four checks honestly --
a "false" with a clear reason is a good outcome, not a failure:

1. "Evidence": does an identifiable source support the exact claim?
2. "Role relevance": does the finding concern this person's responsibilities or team?
3. "Product relevance": is there a specific connection to our two stated
   capabilities (invoice-to-PO matching, routing discrepancies to a reviewer)?
   A company merely being large, funded or growing is NOT a specific connection.
4. "Timeliness": is there evidence this still matters now (a date within roughly
   the last 12 months, an active posting, or an ongoing programme)?

If no finding has a specific connection to our capabilities AND relevance to this
person's work, set "sufficient" to false.

Return JSON only:
{{
  "selected_index": 0,
  "sufficient": true,
  "selection_reason": "one sentence on why this finding beats the others",
  "insufficient_reason": "if sufficient is false: two sentences on what the evidence does and does not support. Empty string otherwise.",
  "checks": [
    {{"name": "Evidence", "passed": true, "reason": "short reason"}},
    {{"name": "Role relevance", "passed": true, "reason": "short reason"}},
    {{"name": "Product relevance", "passed": true, "reason": "short reason"}},
    {{"name": "Timeliness", "passed": true, "reason": "short reason"}}
  ]
}}
""".strip()

# ---------------------------------------------------------------------------
# Stage 4 -- draft
# ---------------------------------------------------------------------------
DRAFT_EMAIL = """
Write a short first-contact email from a salesperson to this prospect.

{seller}

To: {name}{role_line} at {company}

The one signal this email is built on:
  Fact: {claim}
  Published by: {publisher}{date_line}
  Source: {url}
{quote_line}

Why it was chosen: {selection_reason}

Write it so it reads like one person writing to another: plain words, no
marketing voice, no bullet lists, no "I hope this finds you well", no flattery.
60-120 words in the body. Reference the fact specifically enough that it could
not have been sent to anyone else.

What you may and may not say:
- You MAY note the fact and ask how they handle something related to it.
- You MAY NOT claim or imply they have a backlog, are losing money, are making
  errors, are inefficient, or want new software. A job posting mentioning invoice
  matching supports asking how the team handles discrepancies today. It does not
  establish a problem.
- You MAY NOT invent customers, metrics, savings, mutual contacts, or product
  features beyond our two stated capabilities.
{quote_rule}

End the body with exactly one question mark, in the final sentence.

Return JSON only:
{{"subject": "under 60 characters, specific, no colon-heavy marketing phrasing",
  "body": "the email body including a greeting line and a sign-off of '[Your name]'"}}
""".strip()

QUOTE_RULE_ALLOWED = (
    '- You MAY quote the verified sentence above verbatim inside quotation marks. '
    "Copy it exactly or do not quote at all."
)
QUOTE_RULE_FORBIDDEN = (
    "- There is no verified quote for this finding, so you MUST NOT put anything "
    "in quotation marks. Paraphrase the fact instead."
)
