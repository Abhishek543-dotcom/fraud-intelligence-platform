"""Generate formal investigation reports for fraud cases."""

from __future__ import annotations

import json
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
class InvestigationReport:
    """Structured fraud investigation report."""

    request_id: str
    case_id: str
    executive_summary: str
    transaction_analysis: str
    behavioral_anomalies: str
    risk_score: int  # 1-10
    risk_justification: str
    similar_cases: str
    recommended_actions: list[str]
    conclusion: str
    raw_report: str
    model: str


class ReportGeneratorChain:
    """Generates formal fraud investigation reports."""

    def __init__(
        self,
        retriever: FraudRetriever | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._model = model or config.ollama_model
        self._base_url = (base_url or config.ollama_base_url).rstrip("/")
        self._prompt_template = (_PROMPT_DIR / "report.txt").read_text(
            encoding="utf-8"
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)  # Reports need more time
        return self._client

    async def generate_report(
        self,
        case_id: str,
        alert_date: str,
        customer_id: str,
        transactions: list[dict[str, Any]],
        risk_indicators: list[dict[str, Any]],
        request_id: str | None = None,
    ) -> InvestigationReport:
        """Generate a complete investigation report for a fraud case."""
        request_id = request_id or str(uuid.uuid4())
        log = logger.bind(request_id=request_id, case_id=case_id)
        log.info("report_generation_started")

        # Retrieve similar historical cases
        similar_result = await self._retriever.retrieve(
            query=f"fraud cases similar to customer {customer_id} with risk indicators",
            top_k=3,
        )
        similar_context = self._retriever.format_context(similar_result)

        # Format timeline
        timeline = self._format_timeline(transactions)

        # Format risk indicators
        indicators_text = self._format_risk_indicators(risk_indicators)

        # Build prompt
        prompt = self._prompt_template.format(
            case_id=case_id,
            alert_date=alert_date,
            customer_id=customer_id,
            transaction_timeline=timeline,
            risk_indicators=indicators_text,
            similar_cases=similar_context,
        )

        # Generate report
        raw_report = await self._call_ollama(prompt)

        # Parse structured sections
        report = self._parse_report(raw_report, request_id, case_id)

        log.info("report_generation_complete", risk_score=report.risk_score)
        return report

    def _format_timeline(self, transactions: list[dict[str, Any]]) -> str:
        """Format transactions into a readable timeline."""
        if not transactions:
            return "No transaction data available."
        lines = []
        for txn in sorted(transactions, key=lambda t: t.get("timestamp", "")):
            lines.append(
                f"  [{txn.get('timestamp', 'N/A')}] "
                f"TXN {txn.get('transaction_id', 'N/A')} — "
                f"${txn.get('amount', 0.0):.2f} at {txn.get('merchant_id', 'N/A')} "
                f"({txn.get('location', 'N/A')}) "
                f"[score: {txn.get('fraud_score', 'N/A')}]"
            )
        return "\n".join(lines)

    def _format_risk_indicators(self, indicators: list[dict[str, Any]]) -> str:
        """Format risk indicators into readable text."""
        if not indicators:
            return "No specific risk indicators identified."
        lines = []
        for ind in indicators:
            lines.append(
                f"  - {ind.get('indicator', 'Unknown')}: "
                f"{ind.get('description', 'N/A')} "
                f"(severity: {ind.get('severity', 'unknown')})"
            )
        return "\n".join(lines)

    def _parse_report(
        self,
        raw: str,
        request_id: str,
        case_id: str,
    ) -> InvestigationReport:
        """Parse the raw LLM output into structured report sections."""
        sections: dict[str, list[str]] = {}
        current_section = "preamble"
        sections[current_section] = []

        section_map = {
            "EXECUTIVE SUMMARY": "executive_summary",
            "TRANSACTION ANALYSIS": "transaction_analysis",
            "BEHAVIORAL ANOMALIES": "behavioral_anomalies",
            "RISK ASSESSMENT": "risk_assessment",
            "SIMILAR CASE": "similar_cases",
            "RECOMMENDED ACTIONS": "recommended_actions",
            "CONCLUSION": "conclusion",
        }

        for line in raw.split("\n"):
            matched = False
            for header, key in section_map.items():
                if header in line.upper():
                    current_section = key
                    sections.setdefault(current_section, [])
                    matched = True
                    break
            if not matched:
                sections.setdefault(current_section, []).append(line)

        def join_section(key: str) -> str:
            return "\n".join(sections.get(key, [])).strip()

        # Extract risk score from risk_assessment section
        risk_text = join_section("risk_assessment")
        risk_score = 5  # default
        for word in risk_text.split():
            try:
                val = int(word.strip("/10").strip("(").strip(")"))
                if 1 <= val <= 10:
                    risk_score = val
                    break
            except ValueError:
                continue

        # Extract action items
        actions_text = join_section("recommended_actions")
        actions = [
            line.lstrip("-*•0123456789. ").strip()
            for line in actions_text.split("\n")
            if line.strip() and not line.strip().upper().startswith("RECOMMENDED")
        ]

        return InvestigationReport(
            request_id=request_id,
            case_id=case_id,
            executive_summary=join_section("executive_summary") or "Report generation in progress.",
            transaction_analysis=join_section("transaction_analysis") or "See raw report.",
            behavioral_anomalies=join_section("behavioral_anomalies") or "See raw report.",
            risk_score=risk_score,
            risk_justification=risk_text,
            similar_cases=join_section("similar_cases") or "No similar cases found.",
            recommended_actions=actions if actions else ["Manual review recommended."],
            conclusion=join_section("conclusion") or "See raw report for details.",
            raw_report=raw,
            model=self._model,
        )

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama for report generation."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.15,
                        "num_predict": 4096,
                    },
                },
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except httpx.TimeoutException:
            logger.error("ollama_timeout_report", model=self._model)
            return "Report generation timed out. The model may be overloaded."
        except httpx.HTTPError as exc:
            logger.error("ollama_error_report", error=str(exc))
            return "Unable to generate report. Please check the Ollama service."

    def to_json(self, report: InvestigationReport) -> str:
        """Serialize report to JSON for API response."""
        return json.dumps({
            "request_id": report.request_id,
            "case_id": report.case_id,
            "executive_summary": report.executive_summary,
            "transaction_analysis": report.transaction_analysis,
            "behavioral_anomalies": report.behavioral_anomalies,
            "risk_score": report.risk_score,
            "risk_justification": report.risk_justification,
            "similar_cases": report.similar_cases,
            "recommended_actions": report.recommended_actions,
            "conclusion": report.conclusion,
            "model": report.model,
        }, indent=2)

    def to_markdown(self, report: InvestigationReport) -> str:
        """Export report as Markdown."""
        actions_md = "\n".join(f"- {a}" for a in report.recommended_actions)
        return f"""# Fraud Investigation Report — Case {report.case_id}

## Executive Summary
{report.executive_summary}

## Transaction Analysis
{report.transaction_analysis}

## Behavioral Anomalies
{report.behavioral_anomalies}

## Risk Assessment
**Score: {report.risk_score}/10**

{report.risk_justification}

## Similar Case Precedents
{report.similar_cases}

## Recommended Actions
{actions_md}

## Conclusion
{report.conclusion}

---
*Generated by Fraud Investigation Copilot (model: {report.model})*
"""

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def get_report_generator() -> ReportGeneratorChain:
    """Return a module-level report generator instance."""
    return ReportGeneratorChain()
