"""
Denial tracking infrastructure for permission classifiers.
Mirrors src/utils/permissions/denialTracking.ts
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DenialTrackingState",
    "DENIAL_LIMITS",
    "create_denial_tracking_state",
    "record_denial",
    "record_success",
    "should_fallback_to_prompting",
]

DENIAL_LIMITS = {
    "maxConsecutive": 3,
    "maxTotal": 20,
}


@dataclass
class DenialTrackingState:
    consecutive_denials: int = 0
    total_denials: int = 0


def create_denial_tracking_state() -> DenialTrackingState:
    """Returns a fresh denial tracking state."""
    return DenialTrackingState(consecutive_denials=0, total_denials=0)


def record_denial(state: DenialTrackingState) -> DenialTrackingState:
    """Returns updated state after recording a denial."""
    return DenialTrackingState(
        consecutive_denials=state.consecutive_denials + 1,
        total_denials=state.total_denials + 1,
    )


def record_success(state: DenialTrackingState) -> DenialTrackingState:
    """Returns updated state after a successful tool use (resets consecutive denials)."""
    if state.consecutive_denials == 0:
        return state
    return DenialTrackingState(
        consecutive_denials=0,
        total_denials=state.total_denials,
    )


def should_fallback_to_prompting(state: DenialTrackingState) -> bool:
    """Returns True when denial limits are exceeded and we should prompt the user."""
    return (
        state.consecutive_denials >= DENIAL_LIMITS["maxConsecutive"]
        or state.total_denials >= DENIAL_LIMITS["maxTotal"]
    )
