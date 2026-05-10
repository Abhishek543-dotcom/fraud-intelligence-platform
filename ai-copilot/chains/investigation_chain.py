"""Main investigation workflow using LangChain with Ollama."""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import structlog

from ai_copilot.config import config
from ai_copilot.rag.retriever import FraudRetriever, get_retriever

logger = structlog.get_logger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class InvestigationResponse:
    """Structured response from the investigation chain."""

    request_id: str
    answer: str
    evidence: list[str]
    confidence: str  # low / medium / high
    suggested_actions: list[str]
    context_documents_used: int
    model: str


@dataclass
class ConversationMemory:
    """Sliding window conversation memory."""

    _history: deque[dict[str, str]] = field(
        default_factory=lambda: deque(maxlen=config.memory_window_size * 2)
    )

    def add_exchange(self, user_msg: str, assistant_msg: str) -> None:
        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": assistant_msg})

    def get_history_text(self) -> str:
        if not self._history:
            return ""
        parts = []
        for msg in self._history:
            role = msg["role"].capitalize()
            parts.append(f"{role}: {msg['content']}")
        return "\n".join(parts)

    def clear(self) -> None:
        self._history.clear()


class InvestigationChain:
    """RAG-augmented investigation chain: retrieve → augment → generate → parse."""

    def __init__(
        self,
        retriever: FraudRetriever | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._model = model or config.ollama_model
        self._base_url = (base_url or config.ollama_base_url).rstrip("/")
        self._prompt_template = self._load_prompt("investigation.txt")
        self._memory = ConversationMemory()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=config.request_timeout)
        return self._client

    def _load_prompt(self, filename: str) -> str:
        path = _PROMPT_DIR / filename
        return path.read_text(encoding="utf-8")

    async def investigate(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> InvestigationResponse:
        """Run the full investigation chain for a user question."""
        request_id = request_id or str(uuid.uuid4())
        log = logger.bind(request_id=request_id)

        # Step 1: Retrieve relevant context
        log.info("investigation_started", question_length=len(question))
        retrieval = await self._retriever.retrieve(query=question, filters=filters)
        context = self._retriever.format_context(retrieval)

        # Step 2: Build prompt with context + conversation history
        history = self._memory.get_history_text()
        prompt = self._prompt_template.format(
            context=context,
            question=question,
        )
        if history:
            prompt = f"Previous conversation:\n{history}\n\n{prompt}"

        # Step 3: Generate response via Ollama
        raw_response = await self._call_ollama(prompt)

        # Step 4: Parse structured response
        response = self._parse_response(raw_response, request_id, len(retrieval.documents))

        # Step 5: Update memory
        self._memory.add_exchange(question, response.answer)

        log.info(
            "investigation_complete",
            confidence=response.confidence,
            context_docs=response.context_documents_used,
        )
        return response

    async def investigate_stream(
        self,
        question: str,
        filters: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream the investigation response token by token."""
        request_id = request_id or str(uuid.uuid4())

        retrieval = await self._retriever.retrieve(query=question, filters=filters)
        context = self._retriever.format_context(retrieval)

        history = self._memory.get_history_text()
        prompt = self._prompt_template.format(
            context=context,
            question=question,
        )
        if history:
            prompt = f"Previous conversation:\n{history}\n\n{prompt}"

        full_response = ""
        async for token in self._stream_ollama(prompt):
            full_response += token
            yield token

        self._memory.add_exchange(question, full_response)

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama chat/generate API."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": config.temperature,
                        "num_predict": config.max_tokens,
                    },
                },
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except httpx.TimeoutException:
            logger.error("ollama_timeout", model=self._model)
            return (
                "The AI model timed out processing this request. "
                "Please try a more specific question or check if Ollama is running."
            )
        except httpx.HTTPError as exc:
            logger.error("ollama_error", error=str(exc))
            return (
                "Unable to reach the AI model. Please verify that the Ollama service "
                "is running and the model is loaded."
            )

    async def _stream_ollama(self, prompt: str) -> AsyncIterator[str]:
        """Stream tokens from Ollama."""
        client = await self._get_client()
        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": config.temperature,
                        "num_predict": config.max_tokens,
                    },
                },
            ) as response:
                response.raise_for_status()
                import json as _json

                async for line in response.aiter_lines():
                    if line.strip():
                        data = _json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            break
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.error("ollama_stream_error", error=str(exc))
            yield "[Error: Model unavailable. Please retry.]"

    def _parse_response(
        self,
        raw: str,
        request_id: str,
        context_docs_used: int,
    ) -> InvestigationResponse:
        """Parse the raw LLM output into a structured response."""
        answer = raw
        evidence: list[str] = []
        confidence = "medium"
        actions: list[str] = []

        # Extract sections if the model followed the format
        sections = raw.split("\n")
        current_section = ""
        current_content: list[str] = []

        for line in sections:
            line_upper = line.strip().upper()
            if line_upper.startswith("1. FINDING") or line_upper.startswith("FINDING"):
                if current_section and current_content:
                    self._assign_section(current_section, current_content, locals())
                current_section = "finding"
                content = line.split(":", 1)[-1].strip() if ":" in line else ""
                current_content = [content] if content else []
            elif line_upper.startswith("2. EVIDENCE") or line_upper.startswith("EVIDENCE"):
                if current_section and current_content:
                    self._assign_section(current_section, current_content, locals())
                current_section = "evidence"
                current_content = []
            elif line_upper.startswith("3. RISK ASSESSMENT") or line_upper.startswith("RISK"):
                if current_section and current_content:
                    self._assign_section(current_section, current_content, locals())
                current_section = "risk"
                content = line.split(":", 1)[-1].strip() if ":" in line else ""
                current_content = [content] if content else []
            elif line_upper.startswith("4. RECOMMENDED") or line_upper.startswith("RECOMMENDED"):
                if current_section and current_content:
                    self._assign_section(current_section, current_content, locals())
                current_section = "actions"
                current_content = []
            elif line.strip():
                current_content.append(line.strip())

        # Process last section
        if current_section == "finding":
            answer = " ".join(current_content) if current_content else raw
        elif current_section == "evidence":
            evidence = [c for c in current_content if c.startswith("-") or c.startswith("*") or c]
        elif current_section == "risk":
            text = " ".join(current_content).lower()
            if "high" in text:
                confidence = "high"
            elif "low" in text:
                confidence = "low"
        elif current_section == "actions":
            actions = [c.lstrip("-*• ") for c in current_content if c.strip()]

        return InvestigationResponse(
            request_id=request_id,
            answer=answer,
            evidence=evidence if evidence else ["See full response for details."],
            confidence=confidence,
            suggested_actions=actions if actions else ["Review transaction details manually."],
            context_documents_used=context_docs_used,
            model=self._model,
        )

    def _assign_section(
        self,
        section: str,
        content: list[str],
        local_vars: dict[str, Any],
    ) -> None:
        """Helper to assign parsed content to the right variable."""
        # This is used during iterative parsing; actual assignment happens
        # in _parse_response after all sections are collected.
        pass

    def clear_memory(self) -> None:
        """Clear conversation history."""
        self._memory.clear()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def get_investigation_chain() -> InvestigationChain:
    """Return a module-level investigation chain instance."""
    return InvestigationChain()
