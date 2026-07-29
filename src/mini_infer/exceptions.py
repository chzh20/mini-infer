"""Domain exceptions exposed by mini-infer."""


class MiniInferError(Exception):
    """Base class for recoverable mini-infer errors."""

    def __init__(self, message: str, error_code: int | None = None):
        self.message = message
        self.error_code = error_code

    def to_dict(self):
        return {
            "message": self.message,
            "error_code": self.error_code,
        }


class ConfigurationError(MiniInferError):
    """Raised when user-provided configuration is invalid."""


class TokenizationError(MiniInferError):
    """Raised when text cannot be encoded or tokens cannot be decoded."""


class ModelExecutionError(MiniInferError):
    """Raised when a model backend fails."""


class CacheCapacityError(MiniInferError):
    """Raised when a cache cannot reserve the requested capacity."""
