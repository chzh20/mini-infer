import logging as lg
from typing import Any

from mini_infer.config import ModelConfig
from mini_infer.exceptions import ModelExecutionError


class ModelSession:
    """Manages a session with the model.
    Attributes:
    model_config: ModelConfig
    """

    def __init__(self, model_config: ModelConfig) -> None:
        self.model_config = model_config
        self.model: Any | None = None
        self.owned_resources: list[Any] = []

    def __enter__(self) -> "ModelSession":
        try:
            self._load_model()
        except Exception as exc:
            self._release()
            raise ModelExecutionError(f"Failed to load model: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> bool:
        self._release()
        return False

    def _load_model(self) -> None:
        self.model = "Loaded model Instance"

    def _release(self) -> None:
        for resource in reversed(self.owned_resources):
            try:
                if hasattr(resource, "close"):
                    resource.close()
            except Exception:
                lg.exception(f"Failed to release resource: {resource}")
        self.owned_resources.clear()
        self.model = None
        lg.info("Model released successfully")

    def generate(self, prompt: str) -> str:
        if self.model is None:
            raise ModelExecutionError("Model not loaded", 1001)
        return f"Generated text: {prompt}"
