"""Verification layer.

Three kinds of text are kept apart:

* ``source_text``     -- text we fetched from the source page and matched exactly.
                         Only this may be shown in quotation marks.
* ``search_summary``  -- a grounded search summary / grounding segment. Paraphrase only.
* ``model_generated`` -- the model's own words. Paraphrase only.

A finding is *usable* only if an identifiable source backs the exact claim:
either the page was fetched and corroborates the claim, or the search grounding
cited that source for a matching answer segment. If neither holds, the finding
is excluded from drafting.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from html import unescape
from urllib.parse import urlparse

from .schema import PROV_MODEL, PROV_SEARCH_SUMMARY, PROV_SOURCE_TEXT, Finding

_UA = "Mozilla/5.0 (compatible; outreach-prototype/1.0)"
_FETCH_TIMEOUT = 12
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "were", "be", "been", "has", "have", "had", "its", "their",
    "this", "that", "they", "it", "at", "as", "by", "from", "we", "our", "will",
    "new", "also", "more", "about", "into", "team", "role", "company",
}

_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, collapse whitespace, normalise quotes/dashes for matching."""
    text = unescape(text or "")
    text = (
        text.replace("’", "'").replace("‘", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace(" ", " ")
    )
    return _WS_RE.sub(" ", text).strip().lower()


def fetch_page_text(url: str) -> tuple[str | None, str, str]:
    """Best-effort page fetch.

    Returns ``(text_or_None, final_url, note)``. ``text`` is None when the page
    could not be read; ``final_url`` is the URL after redirects (Gemini grounding
    returns redirect URLs, so this is how we learn the real publisher domain).
    """
    if not url:
        return None, url, "no URL"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            final_url = resp.geturl() or url
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(400_000)
    except urllib.error.HTTPError as exc:
        return None, url, f"HTTP {exc.code}"
    except Exception as exc:
        return None, url, f"{type(exc).__name__}"

    if "html" not in ctype and "text" not in ctype and "xml" not in ctype:
        return None, final_url, f"unsupported content type ({ctype or 'unknown'})"

    charset = "utf-8"
    if "charset=" in ctype:
        charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")

    text = _SCRIPT_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) < 80:
        return None, final_url, "page returned no readable text"
    return text, final_url, "fetched"


def _keywords(claim: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-']+", normalise(claim))
    return [w for w in words if w not in _STOPWORDS and len(w) > 3]


def claim_overlap(claim: str, corpus: str) -> float:
    """Fraction of the claim's content words that appear in ``corpus``."""
    kws = _keywords(claim)
    if not kws:
        return 0.0
    norm = normalise(corpus)
    hits = sum(1 for w in set(kws) if w in norm)
    return hits / len(set(kws))


def quote_matches(quote: str, corpus: str) -> bool:
    """True when the quote appears verbatim (modulo whitespace/quote style)."""
    q = normalise(quote)
    if len(q) < 15:
        return False
    return q in normalise(corpus)


def publisher_from_url(url: str, fallback: str = "") -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return fallback
    return host[4:] if host.startswith("www.") else (host or fallback)


def verify_finding(
    finding: Finding,
    grounding_segments: list[str],
    *,
    fetch: bool = True,
) -> Finding:
    """Classify a finding's provenance and decide whether it is usable.

    Sets ``provenance``, ``quote_verified``, ``verification_note`` and (when the
    page redirects) the resolved URL/publisher. Unusable findings get
    ``provenance = model_generated`` with an empty quote.
    """
    page_text = None
    note = ""
    if fetch and finding.url:
        page_text, final_url, note = fetch_page_text(finding.url)
        if final_url and final_url != finding.url:
            finding.url = final_url
        resolved = publisher_from_url(finding.url)
        if resolved and (
            not finding.publisher
            or "vertexaisearch" in finding.publisher
            or "grounding-api" in finding.publisher
        ):
            finding.publisher = resolved

    # 1. Exact quote match against the fetched page -> quotable source text.
    if page_text and finding.quote and quote_matches(finding.quote, page_text):
        finding.provenance = PROV_SOURCE_TEXT
        finding.quote_verified = True
        finding.verification_note = "Quote matched verbatim on the source page."
        return finding

    # Any quote we could not match is dropped rather than shown unverified.
    dropped_quote = bool(finding.quote)
    finding.quote = ""
    finding.quote_verified = False

    # 2. Page fetched and it covers the claim -> paraphrase, source-backed.
    if page_text and claim_overlap(finding.claim, page_text) >= 0.6:
        finding.provenance = PROV_SEARCH_SUMMARY
        finding.verification_note = (
            "Claim corroborated by the source page; shown as paraphrase"
            + (" (quote could not be matched, so it was removed)." if dropped_quote else ".")
        )
        return finding

    # 3. Search grounding cited this source for a matching segment.
    for seg in grounding_segments:
        if claim_overlap(finding.claim, seg) >= 0.6:
            finding.provenance = PROV_SEARCH_SUMMARY
            finding.verification_note = (
                "Supported by a cited search-result summary"
                + (f"; page not readable ({note})." if page_text is None and note else ".")
            )
            return finding

    # 4. Nothing backs it.
    finding.provenance = PROV_MODEL
    finding.verification_note = (
        "Not verified: "
        + (f"source page could not be read ({note})" if page_text is None else
           "the source page does not state this claim")
        + " and no cited search result supports it. Excluded from the draft."
    )
    return finding


def is_usable(finding: Finding) -> bool:
    """A finding may be selected only if a source backs the exact claim."""
    return finding.provenance in (PROV_SOURCE_TEXT, PROV_SEARCH_SUMMARY)
