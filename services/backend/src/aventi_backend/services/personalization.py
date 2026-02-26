from collections.abc import Iterable

from aventi_backend.services.constants import (
    BASELINE_WEIGHT,
    LIKE_BONUS,
    LIKE_MULTIPLIER,
    PASS_MULTIPLIER,
)


def apply_vibe_update(
    weights: dict[str, float], vibes: Iterable[str], action: str
) -> dict[str, float]:
    next_weights = dict(weights)
    for vibe in vibes:
        current = next_weights.get(vibe, BASELINE_WEIGHT)
        next_weights[vibe] = (
            current * LIKE_MULTIPLIER + LIKE_BONUS if action == "like" else current * PASS_MULTIPLIER
        )
    return next_weights
