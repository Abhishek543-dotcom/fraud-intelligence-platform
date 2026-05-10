"""Explain why a transaction was flagged as fraudulent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

from ai_copilot.config import config
from ai_copilot.rag.retriever import FraudRetriever, get_retriever

logger = structlog.get_logger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class AlertExplanation:
    """Structured explanation of a fraud alert."""

    request_id: str
    transaction_id: str
    explanation: str
    anomalous_features: list[dict[str, Any]]
    behavior_comparison: str
    confidence_level: str
    model: str


class AlertExplainerChain:
    """Generates human-readable explanations for fraud alerts."""

    def __init__(
        self,
        retriever: FraudRetriever | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._model = model or config.ollama_model
        self._base_url = (base_url or config.ollama_base_url).rstrip("/")
        self._prompt_template = (_PROMPT_DIR / "explanation.txt").read_text(
            encoding="utf-8"
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=config.request_timeout)
        return self._client

    async def explain(
        self,
        transaction_id: str,
        transaction_details: dict[str, Any],
        feature_values: dict[str, Any] | None = None,
        fraud_score: float = 0.0,
        threshold: float = 0.5,
        request_id: str | None = None,
    ) -> AlertExplanation:
        """Generate a detailed explanation for why a transaction was flagged."""
        request_id = request_id or str(uuid.uuid4())
        log = logger.bind(request_id=request_id, transaction_id=transaction_id)
        log.info("alert_explanation_started")

        # Retrieve customer history from vector store
        customer_id = transaction_details.get("customer_id", "")
        history_result = await self._retriever.retrieve_for_customer(
            query=f"transaction history for customer {customer_id}",
            customer_id=customer_id,
            top_k=3,
        )
        customer_history = self._retriever.format_context(history_result)

        # Format feature values
        feature_text = self._format_features(feature_values or {})

        # Format transaction details
        details_text = "\n".join(
            f"  {k}: {v}" for k, v in transaction_details.items()
        )

        # Build prompt
        prompt = self._prompt_template.format(
            transaction_details=details_text,
            feature_values=feature_text,
            fraud_score=f"{fraud_score:.4f}",
            threshold=f"{threshold:.4f}",
            customer_history=customer_history,
        )

        # Generate explanation
        raw_response = await self._call_ollama(prompt)

        # Parse into structured output
        anomalous = self._extract_anomalous_features(feature_values or {}, threshold)

        explanation = AlertExplanation(
            request_id=request_id,
            transaction_id=transaction_id,
            explanation=raw_response,
            anomalous_features=anomalous,
            behavior_comparison=self._extract_behavior_section(raw_response),
            confidence_level=self._determine_confidence(fraud_score, threshold),
            model=self._model,
        )

        log.info("alert_explanation_complete", confidence=explanation.confidence_level)
        return explanation

    def _format_features(self, features: dict[str, Any]) -> str:
        """Format feature values into readable text."""
        if not features:
            return "No feature data available."
        lines = []
        for name, value in features.items():
            if isinstance(value, float):
                lines.append(f"  {name}: {value:.4f}")
            else:
                lines.append(f"  {name}: {value}")
        return "\n".join(lines)

    def _extract_anomalous_features(
        self,
        features: dict[str, Any],
        threshold: float,
    ) -> list[dict[str, Any]]:
        """Identify features that likely contributed to the fraud score."""
        anomalous = []
        # Heuristic: features with values that are normalized scores above threshold
        for name, value in features.items():
            if isinstance(value, (int, float)):
                if abs(value) > threshold or "anomal" in name.lower() or "risk" in name.lower():
                    anomalous.append({
                        "feature": name,
                        "value": value,
                        "significance": "high" if abs(value) > 0.8 else "medium",
                    })
        return anomalous

    def _extract_behavior_section(self, response: str) -> str:
        """Extract the behavior comparison section from the response."""
        lines = response.split("\n")
        in_section = False
        section_lines: list[str] = []

        for line in lines:
            if "normal behavior" in line.lower() or "compare" in line.lower():
                in_section = True
            elif in_section and line.strip().startswith(("1.", "2.", "3.", "4.")):
                in_section = False
                break
            if in_section:
                section_lines.append(line)

        return "\n".join(section_lines).strip() if section_lines else "See full explanation above."

    def _determine_confidence(self, score: float, threshold: float) -> str:
        """Determine confidence level based on how far score is from threshold."""
        margin = score - threshold
        if margin > 0.3:
            return "high"
        elif margin > 0.1:
            return "medium"
        else:
            return "low"

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama for text generation."""
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
            logger.error("ollama_timeout_explain", model=self._model)
            return "Explanation generation timed out. The model may be overloaded."
        except httpx.HTTPError as exc:
            logger.error("ollama_error_explain", error=str(exc))
            return "Unable to generate explanation. Please check the Ollama service."

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def get_alert_explainer() -> AlertExplainerChain:
    """Return a module-level alert explainer instance."""
    return AlertExplainerChain()
