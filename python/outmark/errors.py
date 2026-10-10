"""Errors for stored state and session transitions."""


class StorageError(Exception):
    """The JSON document cannot be trusted and was left unchanged."""


class ValidationError(Exception):
    """The activity or report input is not usable."""


class TransitionError(Exception):
    """The requested change is not allowed from the current state."""


class DisplayError(Exception):
    """A matrix command was rejected before it was sent."""
