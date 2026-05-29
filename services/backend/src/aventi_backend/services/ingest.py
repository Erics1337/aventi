from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.event_images import should_generate_main_image
from aventi_backend.services.event_intake import normalize_category, normalize_event_payload
from aventi_backend.services.ingest_persistence import EventBundlePersistence, IngestRunRepository


@dataclass(slots=True)
class ManualIngestSummary:
    source_id: str
    ingest_run_id: str
    source_name: str
    city: str
    discovered_count: int
    inserted_events: int
    updated_events: int
    inserted_occurrences: int
    event_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "sourceId": self.source_id,
            "ingestRunId": self.ingest_run_id,
            "source": self.source_name,
            "city": self.city,
            "discovered": self.discovered_count,
            "insertedEvents": self.inserted_events,
            "updatedEvents": self.updated_events,
            "insertedOccurrences": self.inserted_occurrences,
            "eventIds": self.event_ids,
        }


class ManualIngestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ingest_runs = IngestRunRepository(session)
        self.event_persistence = EventBundlePersistence(session)

    async def ingest_manual(
        self,
        source_name: str,
        city: str,
        events: list[dict[str, Any]],
        *,
        scan_meta: dict[str, Any] | None = None,
    ) -> ManualIngestSummary:
        if not events:
            raise ValueError("Manual ingest requires at least one event payload")

        source = await self.ingest_runs.ensure_ingest_source(source_name)
        ingest_run = await self.ingest_runs.create_ingest_run(
            source_id=source["id"],
            city=city,
            discovered_count=len(events),
        )
        await self.session.commit()

        inserted_events = 0
        updated_events = 0
        inserted_occurrences = 0
        near_duplicates_skipped = 0
        image_jobs_enqueued = 0
        image_job_event_ids: set[str] = set()
        event_ids: list[str] = []
        try:
            for raw_event in events:
                normalized = self._normalize_event_payload(raw_event, default_city=city)
                row_counts = await self.event_persistence.upsert_event_bundle(normalized)

                event_id = row_counts["event_id"]
                inserted_events += row_counts["inserted_event"]
                updated_events += row_counts["updated_event"]
                inserted_occurrences += row_counts["inserted_occurrence"]
                near_duplicates_skipped += row_counts.get("near_duplicate", 0)
                event_ids.append(event_id)

                event_state = await self.event_persistence.fetch_event_image_state(event_id)
                metadata = event_state.get("metadata") if isinstance(event_state, dict) else {}
                incoming_source_type = None
                if isinstance(normalized.get("metadata"), dict):
                    incoming_source_type = normalized["metadata"].get("sourceType")

                should_generate_image = should_generate_main_image(
                    event_state.get("image_url"),
                    metadata if isinstance(metadata, dict) else None,
                    incoming_source_type=incoming_source_type,
                )

                if should_generate_image and event_id not in image_job_event_ids:
                    from aventi_backend.services.jobs import JobQueueRepository, JobType

                    await JobQueueRepository(self.session).enqueue_job(
                        JobType.GENERATE_IMAGE,
                        {"eventId": event_id},
                    )
                    image_jobs_enqueued += 1
                    image_job_event_ids.add(event_id)

            final_metadata: dict[str, Any] = {
                "updatedEvents": updated_events,
                "insertedOccurrences": inserted_occurrences,
                "nearDuplicatesSkipped": near_duplicates_skipped,
                "imageJobsEnqueued": image_jobs_enqueued,
                "eventIds": event_ids,
            }
            if scan_meta:
                final_metadata.update(scan_meta)

            await self.ingest_runs.mark_done(
                ingest_run_id=ingest_run["id"],
                discovered_count=len(events),
                inserted_count=inserted_events,
                metadata=final_metadata,
            )
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001
            await self.session.rollback()
            await self.ingest_runs.mark_failed(
                ingest_run_id=ingest_run["id"],
                error_message=str(exc),
                discovered_count=len(events),
                inserted_count=inserted_events,
            )
            await self.session.commit()
            raise

        return ManualIngestSummary(
            source_id=source["id"],
            ingest_run_id=ingest_run["id"],
            source_name=source_name,
            city=city,
            discovered_count=len(events),
            inserted_events=inserted_events,
            updated_events=updated_events,
            inserted_occurrences=inserted_occurrences,
            event_ids=event_ids,
        )

    def _normalize_event_payload(self, raw: dict[str, Any], *, default_city: str) -> dict[str, Any]:
        return normalize_event_payload(raw, default_city=default_city)

    _normalize_category = staticmethod(normalize_category)
