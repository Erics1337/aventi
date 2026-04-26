"""Feed query builder and filtering utilities."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class FeedQueryResult:
    """Result of a feed query with metadata for filtering."""
    rows: list[dict[str, Any]]
    tag_map: dict[str, list[str]]
    ticket_map: dict[str, list[dict[str, Any]]]
    user_weights: dict[str, float]


@dataclass
class FeedFilterContext:
    """Context for client-side filtering of feed results."""
    user_latitude: float
    user_longitude: float
    radius_miles: float | None = None
    time_of_day: str | None = None
    selected_vibes: list[str] | None = None
    categories: list[str] | None = None
    supported_vibe_tags: set[str] = field(default_factory=lambda: {
        "chill", "energetic", "intellectual", "romantic", "social",
        "luxury", "live-music", "wellness", "late-night",
    })


class FeedQueryBuilder:
    """Builds and executes feed queries with dynamic filters."""

    def __init__(
        self,
        session: AsyncSession,
        user_id: str,
        start_ts: datetime,
        end_ts: datetime,
        eligible_statuses: list[str],
        seen_window_days: int,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.eligible_statuses = eligible_statuses
        self.seen_window_days = seen_window_days
        self._price_clause: str = ""
        self._query_params: dict[str, Any] = {}

    def with_price_filter(self, price: str | None) -> "FeedQueryBuilder":
        """Add price filter (free/paid)."""
        if price in {"free", "paid"}:
            self._price_clause = "and e.is_free = :is_free"
            self._query_params["is_free"] = price == "free"
        return self

    def _build_base_params(self) -> dict[str, Any]:
        """Build base query parameters."""
        return {
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "user_id": self.user_id,
            "limit_rows": 100,  # Over-fetch for client-side filtering
            "eligible_statuses": list(self.eligible_statuses),
            "seen_window_days": str(self.seen_window_days),
            **self._query_params,
        }

    def _build_seen_clause(self) -> str:
        """Build the seen events exclusion clause."""
        return """and not exists (
                select 1
                from public.feed_impressions seen
                where seen.user_id = :user_id
                  and seen.event_id = e.id
                  and seen.served_at >= now() - cast(:seen_window_days || ' days' as interval)
              )"""

    def build_query(self) -> str:
        """Build the complete feed query."""
        seen_clause = self._build_seen_clause()
        return f"""
            with next_occurrence as (
              select distinct on (eo.event_id)
                eo.event_id,
                eo.starts_at,
                eo.ends_at,
                eo.timezone
              from public.event_occurrences eo
              where eo.cancelled = false
                and eo.starts_at >= :start_ts
                and eo.starts_at < :end_ts
              order by eo.event_id, eo.starts_at asc
            ),
            user_exclusions as (
              select favored.event_id, saved.normalized_title
              from public.favorites favored
              join public.events saved on saved.id = favored.event_id
              where favored.user_id = :user_id

              union

              select passed.event_id, dismissed.normalized_title
              from public.swipe_actions passed
              join public.events dismissed on dismissed.id = passed.event_id
              where passed.user_id = :user_id
                and passed.action = 'pass'
            )
            select
              e.id::text as id,
              e.title,
              e.normalized_title,
              coalesce(e.description, '') as description,
              e.category,
              coalesce(v.name, 'Unknown Venue') as venue_name,
              coalesce(v.city, '') as city,
              no.starts_at,
              no.ends_at,
              no.timezone,
              e.booking_url,
              e.image_url,
              e.price_label,
              e.is_free,
              e.verification_status,
              v.latitude,
              v.longitude,
              v.rating as venue_rating,
              v.review_count as venue_review_count
            from public.events e
            join next_occurrence no on no.event_id = e.id
            left join public.venues v on v.id = e.venue_id
            where e.hidden = false
              and e.verification_status = any(:eligible_statuses)
              and not exists (
                select 1
                from user_exclusions excluded
                where excluded.event_id = e.id
                   or excluded.normalized_title = e.normalized_title
              )
              {seen_clause}
              {self._price_clause}
            order by no.starts_at asc, e.created_at desc
            limit :limit_rows
            """

    async def fetch_user_weights(self) -> dict[str, float]:
        """Fetch user vibe weights for scoring."""
        result = await self.session.execute(
            text("""
                select vibe, weight
                from public.user_vibe_weights
                where user_id = :user_id
            """),
            {"user_id": self.user_id},
        )
        return {str(row[0]): float(row[1]) for row in result.all()}

    async def fetch_tags(self, event_ids: list[str]) -> dict[str, list[str]]:
        """Fetch tags for events."""
        if not event_ids:
            return {}
        result = await self.session.execute(
            text("""
                select event_id::text as event_id, tag
                from public.event_tags
                where event_id in :event_ids
                order by event_id, tag
            """).bindparams(bindparam("event_ids", expanding=True)),
            {"event_ids": event_ids},
        )
        tag_map: dict[str, list[str]] = {eid: [] for eid in event_ids}
        for row in result.mappings().all():
            tag_map.setdefault(row["event_id"], []).append(str(row["tag"]))
        return tag_map

    async def fetch_ticket_offers(self, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Fetch ticket offers for events."""
        if not event_ids:
            return {}
        result = await self.session.execute(
            text("""
                select event_id::text as event_id, url, provider, price_label, is_free
                from public.ticket_offers
                where event_id in :event_ids
                order by event_id, sort_order, created_at
            """).bindparams(bindparam("event_ids", expanding=True)),
            {"event_ids": event_ids},
        )
        ticket_map: dict[str, list[dict[str, Any]]] = {eid: [] for eid in event_ids}
        for row in result.mappings().all():
            ticket_map.setdefault(str(row["event_id"]), []).append({
                "url": str(row["url"]),
                "provider": row["provider"],
                "priceLabel": row["price_label"],
                "isFree": row["is_free"],
            })
        return ticket_map

    async def execute(self) -> FeedQueryResult:
        """Execute the full feed query pipeline."""
        # Fetch user weights
        user_weights = await self.fetch_user_weights()

        # Execute main query
        result = await self.session.execute(
            text(self.build_query()),
            self._build_base_params(),
        )
        rows = [dict(row) for row in result.mappings().all()]

        # Fetch related data
        event_ids = [row["id"] for row in rows]
        tag_map = await self.fetch_tags(event_ids)
        ticket_map = await self.fetch_ticket_offers(event_ids)

        return FeedQueryResult(
            rows=rows,
            tag_map=tag_map,
            ticket_map=ticket_map,
            user_weights=user_weights,
        )


class FeedItemFilter:
    """Client-side filtering and scoring of feed items."""

    def __init__(self, context: FeedFilterContext) -> None:
        self.context = context

    @staticmethod
    def _haversine_miles(lat1: float, lon1: float, lat2: float | None, lon2: float | None) -> float | None:
        """Calculate distance between two points in miles."""
        if lat2 is None or lon2 is None:
            return None
        from math import acos, cos, radians, sin
        return 3958.7613 * acos(
            min(
                1.0,
                max(
                    -1.0,
                    cos(radians(lat1)) * cos(radians(lat2)) * cos(radians(lon2) - radians(lon1))
                    + sin(radians(lat1)) * sin(radians(lat2)),
                ),
            )
        )

    @staticmethod
    def _time_of_day_matches(starts_at: datetime, bucket: str | None, venue_tz: str | None = None) -> bool:
        """Check if event time matches the time-of-day bucket using local time."""
        if not bucket:
            return True
        # Use event's local timezone (or UTC if not available)
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(venue_tz) if venue_tz else timezone.utc
        try:
            local_dt = starts_at.astimezone(tz) if starts_at.tzinfo else starts_at.replace(tzinfo=tz)
        except Exception:
            local_dt = starts_at.replace(tzinfo=timezone.utc)
        hour = local_dt.hour
        buckets = {
            "morning": (5, 12),
            "afternoon": (12, 17),
            "evening": (17, 22),
            "night": (22, 5),  # Special case: wraps around
        }
        if bucket == "night":
            return hour >= 22 or hour < 5
        start, end = buckets.get(bucket, (0, 24))
        return start <= hour < end

    @staticmethod
    def _refine_event_category(
        category: str | None,
        title: str | None,
        description: str | None,
        vibes: list[str],
        tags: list[str],
    ) -> str:
        """Refine event category based on content analysis."""
        text_content = f"{title or ''} {description or ''} {' '.join(vibes)} {' '.join(tags)}".lower()

        category_keywords = {
            "concerts": ["concert", "music", "musica", "dj", "band", "live music", "orchestra", "opera", "recital"],
            "dining": ["food", "dinner", "lunch", "brunch", "restaurant", "tasting", "cocktail", "wine", "bar"],
            "nightlife": ["party", "club", "nightclub", "dance"],
            "wellness": ["wellness", "yoga", "meditation", "fitness", "spa"],
            "experiences": ["poetry", "poet", "literary", "reading", "book", "author", "lecture", "talk", "workshop"],
        }

        for cat, keywords in category_keywords.items():
            if any(word in text_content for word in keywords):
                return cat

        normalized = (category or "").strip().lower()
        valid_categories = {"nightlife", "dining", "concerts", "wellness", "experiences"}
        if normalized in valid_categories:
            return normalized
        if "energetic" in vibes:
            return "nightlife"
        if "chill" in vibes:
            return "wellness"
        return "experiences"

    def passes_filters(
        self,
        row: dict[str, Any],
        tags: list[str],
    ) -> tuple[bool, str, list[str], float | None]:
        """
        Check if an event passes all client-side filters.
        Returns: (passes, refined_category, effective_vibes, distance_miles)
        """
        # Distance filter
        miles = self._haversine_miles(
            self.context.user_latitude,
            self.context.user_longitude,
            row.get("latitude"),
            row.get("longitude"),
        )
        if self.context.radius_miles is not None and miles is not None:
            if miles > self.context.radius_miles:
                return False, "", [], miles

        # Time of day filter
        starts_at = row["starts_at"]
        venue_tz = row.get("timezone")
        if not self._time_of_day_matches(starts_at, self.context.time_of_day, venue_tz):
            return False, "", [], miles

        # Extract vibes from tags
        event_vibes = [tag for tag in tags if tag in self.context.supported_vibe_tags]
        effective_vibes = event_vibes or ["social"]

        # Category refinement and filter
        refined_category = self._refine_event_category(
            row.get("category"),
            row.get("title"),
            row.get("description"),
            effective_vibes,
            tags,
        )
        if self.context.categories and refined_category not in self.context.categories:
            return False, refined_category, effective_vibes, miles

        # Vibe filter
        if self.context.selected_vibes:
            if not any(vibe in effective_vibes for vibe in self.context.selected_vibes):
                return False, refined_category, effective_vibes, miles

        return True, refined_category, effective_vibes, miles

    def calculate_affinity(
        self,
        effective_vibes: list[str],
        user_weights: dict[str, float],
        starts_at: datetime,
    ) -> float:
        """Calculate affinity score with freshness bias."""
        affinity = sum(user_weights.get(vibe, 1.0) for vibe in effective_vibes)
        # Small freshness bias: earlier events win tie-breaks
        # Use a 30-day horizon from now as reference so events closer to now get higher bias
        horizon_seconds = 30 * 24 * 3600  # 30 days
        reference_ts = time.time() + horizon_seconds
        freshness_bias = max(0.0, reference_ts - starts_at.timestamp()) * 1e-12
        return affinity + freshness_bias

    def build_event_item(
        self,
        row: dict[str, Any],
        tags: list[str],
        effective_vibes: list[str],
        refined_category: str,
        miles: float | None,
        ticket_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Build the final event item dictionary."""
        starts_at = row["starts_at"]
        ends_at = row.get("ends_at")
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "category": refined_category,
            "venueName": row["venue_name"],
            "city": row["city"],
            "startsAt": starts_at.isoformat(),
            "endsAt": ends_at.isoformat() if ends_at else None,
            "bookingUrl": row["booking_url"],
            "imageUrl": row["image_url"],
            "priceLabel": row["price_label"],
            "isFree": bool(row["is_free"]),
            "radiusMiles": miles,
            "vibes": effective_vibes,
            "tags": tags,
            "venueRating": row.get("venue_rating"),
            "venueReviewCount": row.get("venue_review_count"),
            "ticketOffers": ticket_map.get(row["id"], []),
        }

    def filter_and_score(
        self,
        query_result: FeedQueryResult,
    ) -> list[tuple[float, datetime, dict[str, Any]]]:
        """
        Filter and score all events from query result.
        Returns list of (affinity_score, starts_at, event_item) tuples.
        """
        scored_items: list[tuple[float, datetime, dict[str, Any]]] = []

        for row in query_result.rows:
            tags = query_result.tag_map.get(row["id"], [])

            passes, refined_category, effective_vibes, miles = self.passes_filters(row, tags)
            if not passes:
                continue

            starts_at = row["starts_at"]
            affinity = self.calculate_affinity(
                effective_vibes,
                query_result.user_weights,
                starts_at,
            )

            item = self.build_event_item(
                row,
                tags,
                effective_vibes,
                refined_category,
                miles,
                query_result.ticket_map,
            )
            scored_items.append((affinity, starts_at, item))

        return scored_items
