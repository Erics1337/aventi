"""
CLI Script: manual_ingest
Command: aventi-manual-ingest

This script is used to manually import event payloads into the Aventi database from
local files (JSON, NDJSON/JSONL, or CSV). It normalizes the file data mapping and
optionally queues up background verification jobs to validate the imported events.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any

from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.verification import VerificationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aventi-manual-ingest",
        description="Import event payloads from JSON/NDJSON/CSV into Aventi (Supabase Postgres).",
    )
    parser.add_argument("file", help="Path to JSON, NDJSON/JSONL, or CSV file containing event rows")
    parser.add_argument("--city", required=True, help="Default city used for normalization and ingest run")
    parser.add_argument("--source-name", required=True, help="Ingest source identifier (e.g. manual:atx:venue-list)")
    parser.add_argument(
        "--format",
        choices=["auto", "json", "ndjson", "csv"],
        default="auto",
        help="Input format (default: infer from file extension)",
    )
    parser.add_argument(
        "--enqueue-verification",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to enqueue VERIFY_EVENT jobs after ingest (default: true)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    input_path = Path(args.file).expanduser().resolve()
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    events = load_events_from_file(input_path, fmt=args.format)
    if not events:
        print(f"No events found in {input_path}", file=sys.stderr)
        return 2

    try:
        async with open_db_session() as session:
            ingest_summary = await ManualIngestService(session).ingest_manual(
                source_name=args.source_name,
                city=args.city,
                events=events,
            )
            verification_jobs_enqueued = 0
            settings = get_settings()
            if settings.enable_verification and args.enqueue_verification and ingest_summary.event_ids:
                verification_jobs_enqueued = await VerificationService(session).enqueue_verification_jobs(
                    limit=len(ingest_summary.event_ids),
                    event_ids=ingest_summary.event_ids,
                )
    except Exception as exc:  # noqa: BLE001
        print(f"Manual ingest failed: {exc}", file=sys.stderr)
        return 1

    result = ingest_summary.as_dict()
    result["verificationJobsEnqueued"] = verification_jobs_enqueued
    result["inputFile"] = str(input_path)
    print(json.dumps(result, indent=2))
    return 0


def load_events_from_file(path: Path, *, fmt: str = "auto") -> list[dict[str, Any]]:
    selected = _resolve_format(path, fmt)
    if selected == "json":
        return _load_json(path)
    if selected == "ndjson":
        return _load_ndjson(path)
    if selected == "csv":
        return _load_csv(path)
    raise ValueError(f"Unsupported format: {selected}")


def _resolve_format(path: Path, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".ndjson", ".jsonl"}:
        return "ndjson"
    return "json"


def _load_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("events"), list):
            return [row for row in payload["events"] if isinstance(row, dict)]
        return [payload]
    raise ValueError("JSON input must be an object, array, or object with `events` array")


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        if not isinstance(row, dict):
            raise ValueError("Each NDJSON line must be a JSON object")
        events.append(row)
    return events


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return [_normalize_csv_row(row) for row in reader if any((value or "").strip() for value in row.values())]


def _normalize_csv_row(row: dict[str, str | None]) -> dict[str, Any]:
    event: dict[str, Any] = {}
    venue: dict[str, Any] = {}

    for raw_key, raw_value in row.items():
        if raw_key is None:
            continue
        key = raw_key.strip()
        if not key:
            continue
        value = (raw_value or "").strip()
        if value == "":
            continue

        if key in {"vibes", "tags"}:
            event[key] = _parse_list(value)
            continue
        if key in {"isFree", "is_free"}:
            event["isFree"] = _parse_bool(value)
            continue
        if key in {"metadata"}:
            event["metadata"] = _parse_json_object(value)
            continue
        if key in {"venueMetadata", "venue_metadata"}:
            event["venueMetadata"] = _parse_json_object(value)
            continue
        if key.startswith("venue.") or key.startswith("venue_"):
            venue_key = key.split(".", 1)[1] if "." in key else key.removeprefix("venue_")
            venue[_csv_venue_key(venue_key)] = _coerce_scalar_for_key(venue_key, value)
            continue

        event[_csv_event_key(key)] = _coerce_scalar_for_key(key, value)

    if venue:
        event["venue"] = venue
    return event


def _csv_event_key(key: str) -> str:
    mappings = {
        "booking_url": "bookingUrl",
        "starts_at": "startsAt",
        "ends_at": "endsAt",
        "image_url": "imageUrl",
        "price_label": "priceLabel",
        "dress_code": "dressCode",
        "crowd_age": "crowdAge",
        "music_genre": "musicGenre",
        "source_event_key": "sourceEventKey",
    }
    return mappings.get(key, key)


def _csv_venue_key(key: str) -> str:
    mappings = {
        "booking_domain": "bookingDomain",
    }
    return mappings.get(key, key)


def _coerce_scalar_for_key(key: str, value: str) -> Any:
    if key in {"latitude", "longitude", "venueLatitude", "venueLongitude"}:
        try:
            return float(value)
        except ValueError:
            return value
    if key in {"metadata", "venueMetadata", "metadata_json"}:
        return _parse_json_object(value)
    return value


def _parse_list(value: str) -> list[str]:
    delimiter = "|" if "|" in value else ","
    return [part.strip() for part in value.split(delimiter) if part.strip()]


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}


def _parse_json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object for metadata field, got: {type(parsed).__name__}")
    return parsed


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()

