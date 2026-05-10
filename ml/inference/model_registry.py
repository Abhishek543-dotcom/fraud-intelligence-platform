"""File-based model registry for fraud detection models."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "models" / "registry.json"


class ModelRegistry:
    """Lightweight file-based model registry.

    Tracks model versions, metrics, and status without requiring MLflow.
    """

    def __init__(self, registry_path: str | Path | None = None):
        self.path = Path(registry_path) if registry_path else REGISTRY_PATH
        self._ensure_registry()

    def _ensure_registry(self) -> None:
        """Create registry file if it doesn't exist."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"models": {}})

    def _load(self) -> dict:
        with open(self.path) as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def register_model(
        self,
        model_name: str,
        version: str,
        model_path: str,
        metrics: dict[str, float],
        params: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> dict:
        """Register a new model version.

        Args:
            model_name: Name of the model (e.g., "xgboost", "ensemble").
            version: Version string.
            model_path: Path to saved model file.
            metrics: Evaluation metrics dict.
            params: Training hyperparameters.
            tags: Optional metadata tags.

        Returns:
            The registered model entry.
        """
        registry = self._load()
        if model_name not in registry["models"]:
            registry["models"][model_name] = {"versions": []}

        entry = {
            "version": version,
            "path": model_path,
            "metrics": metrics,
            "params": params or {},
            "tags": tags or {},
            "status": "staged",
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "promoted_at": None,
        }

        registry["models"][model_name]["versions"].append(entry)
        self._save(registry)

        logger.info(
            "model_registered",
            model_name=model_name,
            version=version,
            status="staged",
        )
        return entry

    def promote_model(self, model_name: str, version: str) -> dict:
        """Promote a model version to active status.

        Demotes any currently active version to archived.
        """
        registry = self._load()
        if model_name not in registry["models"]:
            raise ValueError(f"Model '{model_name}' not found in registry")

        versions = registry["models"][model_name]["versions"]
        promoted = None

        for entry in versions:
            if entry["status"] == "active":
                entry["status"] = "archived"
            if entry["version"] == version:
                entry["status"] = "active"
                entry["promoted_at"] = datetime.now(timezone.utc).isoformat()
                promoted = entry

        if promoted is None:
            raise ValueError(f"Version '{version}' not found for model '{model_name}'")

        self._save(registry)
        logger.info("model_promoted", model_name=model_name, version=version)
        return promoted

    def get_active_model(self, model_name: str) -> dict | None:
        """Get the currently active model version."""
        registry = self._load()
        if model_name not in registry["models"]:
            return None

        for entry in registry["models"][model_name]["versions"]:
            if entry["status"] == "active":
                return entry

        # If no active model, return latest staged
        versions = registry["models"][model_name]["versions"]
        if versions:
            return versions[-1]
        return None

    def list_models(self) -> dict[str, list[dict]]:
        """List all registered models and their versions."""
        registry = self._load()
        result = {}
        for model_name, data in registry["models"].items():
            result[model_name] = [
                {
                    "version": v["version"],
                    "status": v["status"],
                    "auc_roc": v["metrics"].get("auc_roc", 0),
                    "f1": v["metrics"].get("f1", 0),
                    "registered_at": v["registered_at"],
                }
                for v in data["versions"]
            ]
        return result

    def get_model_path(self, model_name: str, version: str | None = None) -> str | None:
        """Get the file path for a specific model version (or active version)."""
        if version:
            registry = self._load()
            if model_name in registry["models"]:
                for entry in registry["models"][model_name]["versions"]:
                    if entry["version"] == version:
                        return entry["path"]
            return None

        active = self.get_active_model(model_name)
        return active["path"] if active else None

    def delete_version(self, model_name: str, version: str) -> bool:
        """Remove a model version from the registry."""
        registry = self._load()
        if model_name not in registry["models"]:
            return False

        versions = registry["models"][model_name]["versions"]
        original_len = len(versions)
        registry["models"][model_name]["versions"] = [
            v for v in versions if v["version"] != version
        ]

        if len(registry["models"][model_name]["versions"]) < original_len:
            self._save(registry)
            logger.info("model_version_deleted", model_name=model_name, version=version)
            return True
        return False
