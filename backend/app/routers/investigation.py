"""Investigation copilot endpoint — uses the RAG pipeline from ai-copilot when
available, falls back to an enhanced direct Ollama call with conversation memory."""

from __future__ import annotations

import json
import sys
import uuid
from collections import deque
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.models.schemas import InvestigationRequest, InvestigationResponse

router = APIRouter()
logger = structlog.get_logger()
settings = get_settings()

# ---------------------------------------------------------------------------
# Try importing the RAG investigation chain from ai-copilot
# ---------------------------------------------------------------------------

_InvestigationChain = None

try:
    # Append ai-copilot root so that ``from ai_copilot.chains...`` resolves
    _copilot_root = str(Path(__file__).resolve().parents[3] / "ai-copilot")
    if _copilot_root not in sys.path:
        sys.path.insert(0, _copilot_root)

    from chains.investigation_chain import InvestigationChain as _IC  # type: ignore[import-untyped]

    _InvestigationChain = _IC
    logger.info("rag_chain_imported_successfully")
except Exception as exc:
    logger.info("rag_chain_import_failed_using_fallback", error=str(exc))

# Singleton RAG chain (lazy init)
_rag_chain = None


def _get_rag_chain():
    global _rag_chain
    if _InvestigationChain is None:
        return None
    if _rag_chain is None:
        try:
            _rag_chain = _InvestigationChain()
        except Exception as exc:
            logger.warning("rag_chain_init_failed", error=str(exc))
            return None
    return _rag_chain


# ---------------------------------------------------------------------------
# Fallback: enhanced direct Ollama call with conversation memory
# ---------------------------------------------------------------------------

_CONVERSATION_MEMORY: deque[dict[str, str]] = deque(maxlen=10)  # 5 exchanges

_SYSTEM_PROMPT = """\
You are an expert fraud investigation assistant for a financial institution. \
You help analysts investigate suspicious transactions and fraud patterns.

You have access to the following data infrastructure:
- Transaction data in Apache Iceberg tables (bronze.raw_transactions)
- ML models: XGBoost, Random Forest, Isolation Forest, and a weighted Ensemble
- Real-time fraud alerts via Kafka
- Historical alert data with case management

When responding:
1. Be data-driven — reference specific metrics, scores, and patterns
2. Provide actionable recommendations with clear next steps
3. Assess risk level (LOW / MEDIUM / HIGH / CRITICAL)
4. Suggest SQL queries or data lookups when helpful
5. Consider velocity patterns, geographic anomalies, and device fingerprints

Keep responses concise and well-structured. Use numbered lists and headers."""

_AVAILABLE_TABLES_CONTEXT = """\
Available data tables:
- bronze.raw_transactions: Raw transaction data (transaction_id, customer_id, merchant_id, \
amount, currency, timestamp, channel, merchant_name, merchant_category, customer_name, \
location_lat, location_lon, country, is_fraud, fraud_score, status)
- silver.fraud_features: Engineered features (amount_zscore, velocity_1h, distance_km, \
device_score, merchant_risk, time_since_last)
- gold.fraud_alerts: Aggregated alerts with severity and case status"""


def _build_fallback_prompt(message: str) -> str:
    """Construct the full prompt including system instruction, history, and context."""
    parts = [_SYSTEM_PROMPT, "", _AVAILABLE_TABLES_CONTEXT, ""]

    if _CONVERSATION_MEMORY:
        parts.append("Previous conversation:")
        for msg in _CONVERSATION_MEMORY:
            role = msg["role"].capitalize()
            parts.append(f"{role}: {msg['content']}")
        parts.append("")

    parts.append(f"Analyst: {message}")
    parts.append("")
    parts.append("Assistant:")
    return "\n".join(parts)


async def _stream_ollama_tokens(prompt: str):
    """Yield SSE events from a streaming Ollama generate call."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_host}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_predict": 1024,
                    },
                },
            ) as response:
                response.raise_for_status()
                full_text = ""
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        full_text += token
                        yield f"data: {json.dumps({'token': token})}\n\n"
                    if data.get("done", False):
                        break

                # Store in memory
                _CONVERSATION_MEMORY.append({"role": "user", "content": prompt.rsplit("Analyst: ", 1)[-1].split("\n")[0]})
                _CONVERSATION_MEMORY.append({"role": "assistant", "content": full_text})

                yield f"data: {json.dumps({'done': True})}\n\n"

    except httpx.ConnectError:
        yield f"data: {json.dumps({'token': 'The AI copilot is not available. Run `make up-ai` and pull a model.', 'done': True})}\n\n"
    except Exception as exc:
        logger.error("ollama_stream_error", error=str(exc))
        yield f"data: {json.dumps({'token': f'Error: {exc}', 'done': True})}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/investigation/chat", response_model=InvestigationResponse)
async def investigation_chat(body: InvestigationRequest):
    """Send a message to the fraud investigation copilot (non-streaming)."""

    # --- RAG path ---
    chain = _get_rag_chain()
    if chain is not None:
        try:
            result = await chain.investigate(
                question=body.message,
                filters={"alert_id": body.alert_id} if body.alert_id else None,
            )
            return InvestigationResponse(
                data=result.answer,
                message=f"confidence={result.confidence} | docs={result.context_documents_used}",
            )
        except Exception as exc:
            logger.warning("rag_chain_error_falling_back", error=str(exc))

    # --- Enhanced fallback path ---
    prompt = _build_fallback_prompt(body.message)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ollama_host}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_predict": 1024,
                    },
                },
            )

            if response.status_code == 200:
                result = response.json()
                answer = result.get("response", "No response generated.")
                # Update memory
                _CONVERSATION_MEMORY.append({"role": "user", "content": body.message})
                _CONVERSATION_MEMORY.append({"role": "assistant", "content": answer})
                return InvestigationResponse(data=answer)
            else:
                logger.warning("ollama_error", status=response.status_code)
                return InvestigationResponse(
                    data="The AI service is currently unavailable. Please try again later.",
                    message="ollama_unavailable",
                )
    except httpx.ConnectError:
        logger.warning("ollama_connection_error")
        return InvestigationResponse(
            data=(
                "The AI copilot is not yet available. To enable it:\n"
                "1. Run: make up-ai\n"
                "2. Pull a model: docker exec fraud-ollama ollama pull mistral\n"
                "3. Try again."
            ),
            message="ollama_not_running",
        )
    except Exception as e:
        logger.error("investigation_error", error=str(e))
        return InvestigationResponse(
            data=f"An error occurred: {str(e)}",
            message="error",
        )


@router.post("/investigation/chat/stream")
async def investigation_chat_stream(body: InvestigationRequest):
    """Stream investigation responses via SSE.

    The frontend can consume this with an EventSource or fetch + ReadableStream.
    Each event is: ``data: {"token": "..."}\n\n``
    Final event:  ``data: {"done": true}\n\n``
    """

    # --- RAG streaming path ---
    chain = _get_rag_chain()
    if chain is not None:
        try:

            async def _rag_sse():
                try:
                    async for token in chain.investigate_stream(
                        question=body.message,
                        filters={"alert_id": body.alert_id} if body.alert_id else None,
                    ):
                        yield f"data: {json.dumps({'token': token})}\n\n"
                    yield f"data: {json.dumps({'done': True})}\n\n"
                except Exception as exc:
                    logger.error("rag_stream_error", error=str(exc))
                    yield f"data: {json.dumps({'token': f'Error: {exc}', 'done': True})}\n\n"

            return StreamingResponse(_rag_sse(), media_type="text/event-stream")
        except Exception as exc:
            logger.warning("rag_stream_init_error_falling_back", error=str(exc))

    # --- Fallback streaming path ---
    prompt = _build_fallback_prompt(body.message)
    return StreamingResponse(
        _stream_ollama_tokens(prompt),
        media_type="text/event-stream",
    )
