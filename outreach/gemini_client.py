"""Gemini access: grounded web search and plain JSON reasoning calls.

The source-collection logic in ``collect_sources_from_response`` is adapted from
``shared/deep_search_agent.py`` in the Agentic-Harness repo, which carries the
notice below. It maps grounded answer text segments back to the web sources that
support them -- the same claim/source mapping, rewritten to read a
``google-genai`` response directly instead of ADK session events.

    Copyright 2026 Google LLC

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

The original ``shared/research_agent.py`` helper returned summary text only.
``grounded_search`` here returns both the summary text and its sources, so the
workflow can attribute every claim it keeps.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from . import config


class ResearchProviderError(RuntimeError):
    """The search/model provider failed. Maps to status 'Research incomplete'."""


class MissingCredentials(ResearchProviderError):
    pass


@dataclass
class GroundedResult:
    """Output of one grounded search call."""

    text: str                       # the model's summary -- NOT source text
    sources: dict[str, dict[str, Any]]
    queries: list[str]

    def segments(self) -> list[str]:
        """All answer segments that at least one source was cited for."""
        out: list[str] = []
        for src in self.sources.values():
            for claim in src.get("supported_claims", []):
                seg = (claim.get("text_segment") or "").strip()
                if seg:
                    out.append(seg)
        return out


def _client():
    key = config.google_api_key()
    if not key:
        raise MissingCredentials(
            "GOOGLE_API_KEY is not configured. Add it to .env or "
            ".streamlit/secrets.toml to run live research."
        )
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover
        raise ResearchProviderError(f"google-genai is not installed: {exc}") from exc
    return genai.Client(api_key=key, http_options={"api_version": "v1beta"})


# ---------------------------------------------------------------------------
# Source collection (adapted from collect_research_sources_callback)
# ---------------------------------------------------------------------------
def collect_sources_from_response(
    response: Any,
    url_to_short_id: dict[str, str] | None = None,
    sources: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Extract web sources and the answer segments each one supports.

    Mirrors the ADK callback: ``grounding_chunks`` give the URL/title/domain of
    each source, and ``grounding_supports`` tie answer text segments (with
    confidence scores) to those chunks. Accumulates across calls so a run builds
    one source table.
    """
    url_to_short_id = dict(url_to_short_id or {})
    sources = dict(sources or {})
    id_counter = len(url_to_short_id) + 1

    for candidate in getattr(response, "candidates", None) or []:
        meta = getattr(candidate, "grounding_metadata", None)
        if not meta or not getattr(meta, "grounding_chunks", None):
            continue

        chunks_info: dict[int, str] = {}
        for idx, chunk in enumerate(meta.grounding_chunks):
            web = getattr(chunk, "web", None)
            if not web:
                continue
            url = web.uri
            if not url:
                continue
            domain = getattr(web, "domain", "") or ""
            title = web.title if web.title and web.title != domain else (domain or web.title or url)
            if url not in url_to_short_id:
                short_id = f"src-{id_counter}"
                url_to_short_id[url] = short_id
                sources[short_id] = {
                    "short_id": short_id,
                    "title": title or url,
                    "url": url,
                    "domain": domain,
                    "supported_claims": [],
                }
                id_counter += 1
            chunks_info[idx] = url_to_short_id[url]

        for support in getattr(meta, "grounding_supports", None) or []:
            confidence_scores = support.confidence_scores or []
            chunk_indices = support.grounding_chunk_indices or []
            for i, chunk_idx in enumerate(chunk_indices):
                if chunk_idx not in chunks_info:
                    continue
                short_id = chunks_info[chunk_idx]
                confidence = (
                    confidence_scores[i] if i < len(confidence_scores) else 0.5
                )
                text_segment = support.segment.text if support.segment else ""
                sources[short_id]["supported_claims"].append(
                    {"text_segment": text_segment, "confidence": confidence}
                )

    return url_to_short_id, sources


def _search_queries(response: Any) -> list[str]:
    queries: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        meta = getattr(candidate, "grounding_metadata", None)
        for q in (getattr(meta, "web_search_queries", None) or []) if meta else []:
            if q not in queries:
                queries.append(q)
    return queries


# ---------------------------------------------------------------------------
# Public calls
# ---------------------------------------------------------------------------
def grounded_search(prompt: str, *, temperature: float = 0.2) -> GroundedResult:
    """Run one Gemini call with the google_search tool and keep its sources."""
    from google.genai import types

    client = _client()
    try:
        response = client.models.generate_content(
            model=config.RESEARCH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=temperature,
            ),
        )
    except Exception as exc:  # network, quota, auth, safety-block
        raise ResearchProviderError(f"{type(exc).__name__}: {exc}") from exc

    _, sources = collect_sources_from_response(response)
    return GroundedResult(
        text=(getattr(response, "text", None) or "").strip(),
        sources=sources,
        queries=_search_queries(response),
    )


_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def json_call(prompt: str, *, temperature: float = 0.1) -> Any:
    """Ask Gemini for JSON. No search tool, so no paid search is triggered."""
    from google.genai import types

    client = _client()
    try:
        response = client.models.generate_content(
            model=config.REASONING_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        raise ResearchProviderError(f"{type(exc).__name__}: {exc}") from exc

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ResearchProviderError("Model returned an empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise ResearchProviderError(f"Model did not return valid JSON: {text[:300]}")
