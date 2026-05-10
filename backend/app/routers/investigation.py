import httpx
import structlog
from fastapi import APIRouter
from app.config import get_settings
from app.models.schemas import InvestigationRequest, InvestigationResponse

router = APIRouter()
logger = structlog.get_logger()
settings = get_settings()


@router.post("/investigation/chat", response_model=InvestigationResponse)
async def investigation_chat(body: InvestigationRequest):
    """Send a message to the fraud investigation copilot."""
    prompt = (
        "You are a fraud investigation assistant for a financial institution. "
        "You help analysts investigate suspicious transactions and fraud patterns. "
        "Be concise, data-driven, and actionable in your responses.\n\n"
        f"Analyst: {body.message}\n\n"
        "Assistant:"
    )

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
                        "num_predict": 512,
                    },
                },
            )

            if response.status_code == 200:
                result = response.json()
                return InvestigationResponse(data=result.get("response", "No response generated."))
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
