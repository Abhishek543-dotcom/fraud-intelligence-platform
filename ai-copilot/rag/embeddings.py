"""Document embedding pipeline with Ollama and sentence-transformers fallback."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    pass

from ai_copilot.config import config

logger = structlog.get_logger(__name__)


class OllamaEmbeddings:
    """Generate embeddings using Ollama's embedding API with LRU caching."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or config.ollama_base_url).rstrip("/")
        self.model = model or config.ollama_embedding_model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._fallback: _SentenceTransformerFallback | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        cache_key = _cache_key(text, self.model)
        cached = _embedding_cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]
            _embedding_cache_put(cache_key, embedding)
            return embedding
        except (httpx.HTTPError, KeyError) as exc:
            logger.warning(
                "ollama_embedding_failed",
                error=str(exc),
                fallback="sentence-transformers",
            )
            return await self._embed_with_fallback(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts, using cache where possible."""
        results: list[list[float]] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            cache_key = _cache_key(text, self.model)
            cached = _embedding_cache_get(cache_key)
            if cached is not None:
                results.append(cached)
            else:
                results.append([])  # placeholder
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            try:
                client = await self._get_client()
                for idx, text in zip(uncached_indices, uncached_texts):
                    response = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                    response.raise_for_status()
                    embedding = response.json()["embedding"]
                    cache_key = _cache_key(text, self.model)
                    _embedding_cache_put(cache_key, embedding)
                    results[idx] = embedding
            except (httpx.HTTPError, KeyError) as exc:
                logger.warning(
                    "ollama_batch_embedding_failed",
                    error=str(exc),
                    remaining=len(uncached_texts),
                )
                for idx, text in zip(uncached_indices, uncached_texts):
                    if not results[idx]:
                        results[idx] = await self._embed_with_fallback(text)

        return results

    async def _embed_with_fallback(self, text: str) -> list[float]:
        """Fall back to sentence-transformers for embedding."""
        if self._fallback is None:
            self._fallback = _SentenceTransformerFallback()
        return self._fallback.embed(text)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class _SentenceTransformerFallback:
    """CPU-only fallback using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("loading_sentence_transformer_fallback", model=model_name)
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()


# ---------------------------------------------------------------------------
# Simple LRU embedding cache
# ---------------------------------------------------------------------------

_CACHE: dict[str, list[float]] = {}
_CACHE_MAX = 2048


def _cache_key(text: str, model: str) -> str:
    h = hashlib.sha256(f"{model}:{text}".encode()).hexdigest()[:16]
    return h


def _embedding_cache_get(key: str) -> list[float] | None:
    return _CACHE.get(key)


def _embedding_cache_put(key: str, embedding: list[float]) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        # Evict oldest 25%
        keys_to_remove = list(_CACHE.keys())[: _CACHE_MAX // 4]
        for k in keys_to_remove:
            del _CACHE[k]
    _CACHE[key] = embedding


@lru_cache(maxsize=1)
def get_embeddings_client() -> OllamaEmbeddings:
    """Return a module-level singleton embeddings client."""
    return OllamaEmbeddings()
