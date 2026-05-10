"""Natural language fraud search — translate queries to structured filters."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

from ai_copilot.config import config

logger = structlog.get_logger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class StructuredQuery:
    """Parsed structured query from natural language."""

    filters: list[dict[str, Any]]
    time_range: dict[str, str]
    sort_by: dict[str, str]
    limit: int


@dataclass
class FraudSearchResult:
    """Result of a natural language fraud search."""

    request_id: str
    original_query: str
    structured_query: StructuredQuery
    summary: str
    raw_llm_output: str
    model: str


class FraudSearchChain:
    """Translates natural language queries into structured fraud data searches."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model or config.ollama_model
        self._base_url = (base_url or config.ollama_base_url).rstrip("/")
        self._prompt_template = (_PROMPT_DIR / "search.txt").read_text(
            encoding="utf-8"
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=config.request_timeout)
        return self._client

    async def search(
        self,
        query: str,
        request_id: str | None = None,
    ) -> FraudSearchResult:
        """Translate a natural language query into a structured search and execute it."""
        request_id = request_id or str(uuid.uuid4())
        log = logger.bind(request_id=request_id)
        log.info("fraud_search_started", query=query)

        # Step 1: Translate to structured query via LLM
        prompt = self._prompt_template.format(query=query)
        raw_output = await self._call_ollama(prompt)

        # Step 2: Parse the JSON from LLM output
        structured = self._parse_structured_query(raw_output)

        # Step 3: Generate summary
        summary = self._generate_query_summary(query, structured)

        result = FraudSearchResult(
            request_id=request_id,
            original_query=query,
            structured_query=structured,
            summary=summary,
            raw_llm_output=raw_output,
            model=self._model,
        )

        log.info(
            "fraud_search_complete",
            filters_count=len(structured.filters),
            limit=structured.limit,
        )
        return result

    def _parse_structured_query(self, raw: str) -> StructuredQuery:
        """Extract JSON from the LLM output and parse into StructuredQuery."""
        # Find JSON in the response (may be surrounded by explanation text)
        json_str = self._extract_json(raw)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("json_parse_failed", raw_length=len(raw))
            return StructuredQuery(
                filters=[],
                time_range={"start": "now-7d", "end": "now"},
                sort_by={"field": "timestamp", "direction": "desc"},
                limit=50,
            )

        filters = data.get("filters", [])
        validated_filters = []
        valid_fields = {
            "transaction_id", "customer_id", "merchant_id", "amount",
            "timestamp", "fraud_score", "fraud_type", "merchant_category",
            "location", "device_id",
        }
        valid_operators = {"eq", "neq", "gt", "lt", "gte", "lte", "contains", "in", "not_in"}

        for f in filters:
            if (
                isinstance(f, dict)
                and f.get("field") in valid_fields
                and f.get("operator") in valid_operators
            ):
                validated_filters.append(f)

        time_range = data.get("time_range", {"start": "now-7d", "end": "now"})
        sort_by = data.get("sort_by", {"field": "timestamp", "direction": "desc"})

        limit = data.get("limit", 50)
        if not isinstance(limit, int) or limit < 1:
            limit = 50
        limit = min(limit, 1000)

        return StructuredQuery(
            filters=validated_filters,
            time_range=time_range,
            sort_by=sort_by,
            limit=limit,
        )

    def _extract_json(self, text: str) -> str:
        """Extract JSON object from text that may contain surrounding explanation."""
        # Try to find JSON between braces
        depth = 0
        start = -1
        for i, char in enumerate(text):
            if char == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    return text[start : i + 1]

        # Fallback: try the whole text
        return text.strip()

    def _generate_query_summary(self, query: str, structured: StructuredQuery) -> str:
        """Generate a human-readable summary of the parsed query."""
        parts = [f'Search for: "{query}"']

        if structured.filters:
            filter_descs = []
            for f in structured.filters:
                filter_descs.append(
                    f"{f['field']} {f['operator']} {f['value']}"
                )
            parts.append(f"Filters: {', '.join(filter_descs)}")

        parts.append(
            f"Time range: {structured.time_range.get('start', '?')} to "
            f"{structured.time_range.get('end', '?')}"
        )
        parts.append(
            f"Sort: {structured.sort_by.get('field', 'timestamp')} "
            f"{structured.sort_by.get('direction', 'desc')}"
        )
        parts.append(f"Limit: {structured.limit}")

        return " | ".join(parts)

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama for query translation."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.05,  # Very low for structured output
                        "num_predict": 512,
                    },
                },
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except httpx.TimeoutException:
            logger.error("ollama_timeout_search", model=self._model)
            return "{}"
        except httpx.HTTPError as exc:
            logger.error("ollama_error_search", error=str(exc))
            return "{}"

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def get_fraud_search() -> FraudSearchChain:
    """Return a module-level fraud search instance."""
    return FraudSearchChain()
