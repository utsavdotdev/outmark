"""Errors for stored state and session transitions."""


class StorageError(Exception):
    """The JSON document cannot be trusted and was left unchanged."""


class ValidationError(Exception):
    """The activity or report input is not usable."""


class TransitionError(Exception):
    """The requested change is not allowed from the current state."""

    def __init__(self, message: str, *, remaining_seconds: float | None = None) -> None:
        super().__init__(message)
        self.remaining_seconds = remaining_seconds


class DisplayError(Exception):
    """A matrix command was rejected before it was sent."""


class LocalModelError(Exception):
    """The local model could not be used. Callers fall back instead of leaving the device."""
