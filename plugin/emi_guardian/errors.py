"""Application-specific exceptions."""

from __future__ import annotations


class EmiGuardianError(RuntimeError):
    """Base exception for recoverable EMI Guardian failures."""


class CapabilityError(EmiGuardianError):
    """Raised when the running KiCad API lacks a required capability."""


class ValidationError(EmiGuardianError):
    """Raised when user-provided settings are invalid."""


class MutationSafetyError(EmiGuardianError):
    """Raised when a requested mutation violates a safety guard."""
