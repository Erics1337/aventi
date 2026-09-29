"""Canonical ingestion taxonomy; feeds use these persisted categories unchanged."""

from typing import Any, get_args

from aventi_backend.models.schemas import EventCategory


def normalize_category(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in get_args(EventCategory):
        return normalized
    for category, words in (
        ("comedy", ("comedy", "stand-up", "standup", "improv")),
        ("markets", ("market", "craft fair", "flea")),
        ("sports", ("sport", "baseball", "basketball", "football", "soccer", "hockey")),
        ("outdoors", ("outdoor", "hiking", "trail", "kayak")),
        ("tech", ("technology", "tech meetup", "hackathon", "startup", "coding")),
        ("concerts", ("music", "concert", "show")),
        ("dining", ("food", "drink", "dining")),
        ("wellness", ("wellness", "fitness", "yoga")),
        ("nightlife", ("night", "club", "bar")),
    ):
        if any(word in normalized for word in words):
            return category
    return "experiences"
