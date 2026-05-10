"""FastAPI routes for the Fraud Investigation Copilot."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_copilot.chains.alert_explainer import AlertExplainerChain, get_alert_explainer
from ai_copilot.chains.fraud_search import FraudSearchChain, get_fraud_search
from ai_copilot.chains.investigation_chain import InvestigationChain, get_investigation_chain
from ai_copilot.chains.report_generator import ReportGeneratorChain, get_report_generator
from ai_copilot.rag.indexer import FraudIndexer, get_indexer
from ai_copilot.rag.vector_store import get_vector_store

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class InvestigateRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    filters: dict[str, Any] | None = None


class InvestigateResponse(BaseModel):
    request_id: str
    answer: str
    evidence: list[str]
    confidence: str
    suggested_actions: list[str]
    context_documents_used: int
    model: str


class ExplainRequest(BaseModel):
    transaction_details: dict[str, Any]
    feature_values: dict[str, Any] | None = None
    fraud_score: float = 0.0
    threshold: float = 0.5


class ExplainResponse(BaseModel):
    request_id: str
    transaction_id: str
    explanation: str
    anomalous_features: list[dict[str, Any]]
    behavior_comparison: str
    confidence_level: str
    model: str


class ReportRequest(BaseModel):
    alert_date: str
    customer_id: str
    transactions: list[dict[str, Any]]
    risk_indicators: list[dict[str, Any]] = Field(default_factory=list)


class ReportResponse(BaseModel):
    request_id: str
    case_id: str
    executive_summary: str
    transaction_analysis: str
    behavioral_anomalies: str
    risk_score: int
    risk_justification: str
    similar_cases: str
    recommended_actions: list[str]
    conclusion: str
    raw_report: str
    model: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)


class SearchResponse(BaseModel):
    request_id: str
    original_query: str
    structured_query: dict[str, Any]
    summary: str
    model: str


class IndexRequest(BaseModel):
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)


class IndexResponse(BaseModel):
    request_id: str
    alerts_indexed: int
    notes_indexed: int


class HealthResponse(BaseModel):
    ollama: bool
    chromadb: bool
    collection_count: int
    model: str


class ConversationEntry(BaseModel):
    role: str
    content: str


# ---------------------------------------------------------------------------
# Singletons (lazy-loaded)
# ---------------------------------------------------------------------------

_investigation_chain: InvestigationChain | None = None
_alert_explainer: AlertExplainerChain | None = None
_report_generator: ReportGeneratorChain | None = None
_fraud_search: FraudSearchChain | None = None
_indexer: FraudIndexer | None = None

_conversation_log: list[dict[str, str]] = []


def _get_investigation() -> InvestigationChain:
    global _investigation_chain
    if _investigation_chain is None:
        _investigation_chain = get_investigation_chain()
    return _investigation_chain


def _get_explainer() -> AlertExplainerChain:
    global _alert_explainer
    if _alert_explainer is None:
        _alert_explainer = get_alert_explainer()
    return _alert_explainer


def _get_reporter() -> ReportGeneratorChain:
    global _report_generator
    if _report_generator is None:
        _report_generator = get_report_generator()
    return _report_generator


def _get_search() -> FraudSearchChain:
    global _fraud_search
    if _fraud_search is None:
        _fraud_search = get_fraud_search()
    return _fraud_search


def _get_indexer() -> FraudIndexer:
    global _indexer
    if _indexer is None:
        _indexer = get_indexer()
    return _indexer


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate(req: InvestigateRequest) -> InvestigateResponse:
    """Ask an investigation question with RAG-augmented context."""
    request_id = str(uuid.uuid4())
    log = logger.bind(request_id=request_id)
    log.info("copilot_investigate", question_length=len(req.question))

    try:
        chain = _get_investigation()
        result = await chain.investigate(
            question=req.question,
            filters=req.filters,
            request_id=request_id,
        )

        _conversation_log.append({"role": "user", "content": req.question})
        _conversation_log.append({"role": "assistant", "content": result.answer})

        return InvestigateResponse(
            request_id=result.request_id,
            answer=result.answer,
            evidence=result.evidence,
            confidence=result.confidence,
            suggested_actions=result.suggested_actions,
            context_documents_used=result.context_documents_used,
            model=result.model,
        )
    except Exception as exc:
        log.error("investigate_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {exc}",
        )


@router.post("/investigate/stream")
async def investigate_stream(req: InvestigateRequest) -> StreamingResponse:
    """Stream an investigation response via Server-Sent Events."""
    request_id = str(uuid.uuid4())

    async def event_generator():
        try:
            chain = _get_investigation()
            async for token in chain.investigate_stream(
                question=req.question,
                filters=req.filters,
                request_id=request_id,
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("stream_failed", request_id=request_id, error=str(exc))
            yield f"data: [ERROR] {exc}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": request_id,
        },
    )


@router.post("/explain/{transaction_id}", response_model=ExplainResponse)
async def explain_alert(transaction_id: str, req: ExplainRequest) -> ExplainResponse:
    """Explain why a specific transaction was flagged as fraud."""
    request_id = str(uuid.uuid4())
    log = logger.bind(request_id=request_id, transaction_id=transaction_id)
    log.info("copilot_explain")

    try:
        explainer = _get_explainer()
        result = await explainer.explain(
            transaction_id=transaction_id,
            transaction_details=req.transaction_details,
            feature_values=req.feature_values,
            fraud_score=req.fraud_score,
            threshold=req.threshold,
            request_id=request_id,
        )

        return ExplainResponse(
            request_id=result.request_id,
            transaction_id=result.transaction_id,
            explanation=result.explanation,
            anomalous_features=result.anomalous_features,
            behavior_comparison=result.behavior_comparison,
            confidence_level=result.confidence_level,
            model=result.model,
        )
    except Exception as exc:
        log.error("explain_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Explanation failed: {exc}",
        )


@router.post("/report/{case_id}", response_model=ReportResponse)
async def generate_report(case_id: str, req: ReportRequest) -> ReportResponse:
    """Generate a formal investigation report for a fraud case."""
    request_id = str(uuid.uuid4())
    log = logger.bind(request_id=request_id, case_id=case_id)
    log.info("copilot_report")

    try:
        generator = _get_reporter()
        result = await generator.generate_report(
            case_id=case_id,
            alert_date=req.alert_date,
            customer_id=req.customer_id,
            transactions=req.transactions,
            risk_indicators=req.risk_indicators,
            request_id=request_id,
        )

        return ReportResponse(
            request_id=result.request_id,
            case_id=result.case_id,
            executive_summary=result.executive_summary,
            transaction_analysis=result.transaction_analysis,
            behavioral_anomalies=result.behavioral_anomalies,
            risk_score=result.risk_score,
            risk_justification=result.risk_justification,
            similar_cases=result.similar_cases,
            recommended_actions=result.recommended_actions,
            conclusion=result.conclusion,
            raw_report=result.raw_report,
            model=result.model,
        )
    except Exception as exc:
        log.error("report_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {exc}",
        )


@router.post("/search", response_model=SearchResponse)
async def fraud_search(req: SearchRequest) -> SearchResponse:
    """Translate natural language query into structured fraud search."""
    request_id = str(uuid.uuid4())
    log = logger.bind(request_id=request_id)
    log.info("copilot_search", query=req.query)

    try:
        search = _get_search()
        result = await search.search(query=req.query, request_id=request_id)

        return SearchResponse(
            request_id=result.request_id,
            original_query=result.original_query,
            structured_query={
                "filters": result.structured_query.filters,
                "time_range": result.structured_query.time_range,
                "sort_by": result.structured_query.sort_by,
                "limit": result.structured_query.limit,
            },
            summary=result.summary,
            model=result.model,
        )
    except Exception as exc:
        log.error("search_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        )


@router.get("/history", response_model=list[ConversationEntry])
async def get_history() -> list[ConversationEntry]:
    """Get the current conversation history."""
    return [
        ConversationEntry(role=entry["role"], content=entry["content"])
        for entry in _conversation_log[-20:]  # Last 20 entries
    ]


@router.post("/index", response_model=IndexResponse)
async def index_documents(req: IndexRequest) -> IndexResponse:
    """Trigger indexing of fraud alerts and notes into the vector store."""
    request_id = str(uuid.uuid4())
    log = logger.bind(request_id=request_id)
    log.info("copilot_index", alerts=len(req.alerts), notes=len(req.notes))

    indexer = _get_indexer()

    alerts_indexed = 0
    notes_indexed = 0

    if req.alerts:
        alerts_indexed = await indexer.index_batch_alerts(req.alerts)

    for note_data in req.notes:
        try:
            await indexer.index_investigation_note(
                case_id=note_data.get("case_id", "unknown"),
                note=note_data.get("note", ""),
                analyst=note_data.get("analyst", "system"),
                customer_id=note_data.get("customer_id"),
            )
            notes_indexed += 1
        except Exception as exc:
            log.error("note_indexing_failed", error=str(exc))

    return IndexResponse(
        request_id=request_id,
        alerts_indexed=alerts_indexed,
        notes_indexed=notes_indexed,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check connectivity to Ollama and ChromaDB."""
    import httpx as _httpx

    from ai_copilot.config import config as _config

    # Check Ollama
    ollama_ok = False
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_config.ollama_base_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    # Check ChromaDB
    chromadb_ok = False
    collection_count = 0
    try:
        store = get_vector_store()
        chromadb_ok = store.health_check()
        if chromadb_ok:
            collection_count = store.count()
    except Exception:
        pass

    return HealthResponse(
        ollama=ollama_ok,
        chromadb=chromadb_ok,
        collection_count=collection_count,
        model=_config.ollama_model,
    )
