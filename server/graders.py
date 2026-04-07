"""Task grader callables referenced by openenv.yaml.

These classes are intentionally lightweight wrappers that extract task_score
from observations and keep scores strictly inside (0, 1).
"""

from __future__ import annotations

from typing import Any


def _extract_score(observation: Any, *args: Any, **kwargs: Any) -> float:
    # Accept both dict and object observations used by different runners.
    source = observation
    if source is None and args:
        source = args[0]
    if source is None:
        source = kwargs.get("observation")

    score: float | None = None
    if isinstance(source, dict):
        raw = source.get("task_score", 0.0)
        score = float(raw)
    elif source is not None and hasattr(source, "task_score"):
        score = float(getattr(source, "task_score", 0.0))

    if score is None:
        score = 0.0

    # Validator requires strictly interior scores.
    if score <= 0.0:
        return 0.01
    if score >= 1.0:
        return 0.99
    return score


class EasyGrader:
    def __call__(self, observation: Any = None, *args: Any, **kwargs: Any) -> float:
        return _extract_score(observation, *args, **kwargs)


class MediumGrader:
    def __call__(self, observation: Any = None, *args: Any, **kwargs: Any) -> float:
        return _extract_score(observation, *args, **kwargs)


class HardGrader:
    def __call__(self, observation: Any = None, *args: Any, **kwargs: Any) -> float:
        return _extract_score(observation, *args, **kwargs)
