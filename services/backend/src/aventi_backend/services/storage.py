"""Supabase Storage service for uploading and managing event images."""
from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import get_settings


class SupabaseStorageService:
    """Service for uploading images to Supabase Storage."""

    def __init__(self, supabase_secret_key: str | None = None) -> None:
        settings = get_settings()
        self.base_url = settings.supabase_url.rstrip("/") if settings.supabase_url else None
        self.service_key = supabase_secret_key or settings.supabase_secret_key
        self.bucket_name = "event-images"

    def _auth_headers(self, *, content_type: str | None = None) -> dict[str, str]:
        """Build Supabase API auth headers for both legacy JWT and new sb_secret keys."""
        if not self.service_key:
            return {}

        headers = {"apikey": self.service_key}
        if not self.service_key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.service_key}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def upload_image_from_url(
        self,
        image_url: str,
        event_id: str,
        content_type: str = "image/jpeg",
        api_key: str | None = None,
    ) -> str | None:
        """
        Download an image from URL and upload to Supabase Storage.
        Returns the public URL of the stored image.
        """
        if not self.base_url or not self.service_key:
            return None

        try:
            # Pollinations can be slow to render a fresh image, so give it a
            # couple of chances before letting the queue retry the job.
            image_data: bytes | None = None
            headers = {"Authorization": api_key} if api_key else {}
            async with httpx.AsyncClient(timeout=60.0) as client:
                for attempt in range(2):
                    try:
                        response = await client.get(image_url, headers=headers)
                        response.raise_for_status()
                        image_data = response.content
                        break
                    except (httpx.HTTPError, httpx.TimeoutException):
                        if attempt == 1:
                            raise
                        await asyncio.sleep(2)
            if image_data is None:
                raise RuntimeError("Pollinations image download returned no data")

            # Generate a unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{event_id}_{timestamp}.jpg"

            # Upload to Supabase Storage
            upload_url = f"{self.base_url}/storage/v1/object/{self.bucket_name}/{filename}"

            async with httpx.AsyncClient(timeout=60.0) as client:
                upload_response = await client.post(
                    upload_url,
                    headers=self._auth_headers(content_type=content_type) | {
                        "x-upsert": "true",  # Overwrite if exists
                    },
                    content=image_data,
                )
                upload_response.raise_for_status()

            # Return the public URL
            public_url = f"{self.base_url}/storage/v1/object/public/{self.bucket_name}/{filename}"
            return public_url

        except Exception as e:
            if isinstance(e, httpx.HTTPStatusError):
                print(f"Failed to upload image to Supabase Storage: {e.response.text}")
            else:
                print(f"Failed to upload image to Supabase Storage: {type(e).__name__}: {e!r}")
            return None

    async def ensure_bucket_exists(self) -> bool:
        """Ensure the event-images bucket exists in Supabase Storage."""
        if not self.base_url or not self.service_key:
            return False

        try:
            # Check if bucket exists
            buckets_url = f"{self.base_url}/storage/v1/bucket"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    buckets_url,
                    headers=self._auth_headers(),
                )

                if response.status_code == 200:
                    buckets = response.json()
                    bucket_names = [b.get("name") for b in buckets]
                    if self.bucket_name in bucket_names:
                        return True

            # Create bucket if it doesn't exist
            create_url = f"{self.base_url}/storage/v1/bucket"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    create_url,
                    headers=self._auth_headers(content_type="application/json"),
                    json={
                        "id": self.bucket_name,
                        "name": self.bucket_name,
                        "public": True,  # Allow public access
                    },
                )

                if response.status_code in (200, 201):
                    return True
                else:
                    print(f"Failed to create bucket: {response.text}")
                    return False

        except Exception as e:
            print(f"Failed to ensure bucket exists: {e}")
            return False


async def generate_and_store_event_image(
    event_id: str,
    event_title: str,
    event_city: str,
    vibes: list[str] | None,
    session: AsyncSession,
    auto_commit: bool = True,
) -> str | None:
    """
    Generate an image using Pollinations.ai and store it in Supabase Storage.
    Returns the Supabase Storage URL.

    Args:
        auto_commit: If True (default), commits the session after updating the event.
            Set to False if the caller is managing the transaction boundary.
    """
    from aventi_backend.services.gemini import PollinationsImageGenerator

    settings = get_settings()

    # Generate image via Pollinations
    generator = PollinationsImageGenerator(api_key=settings.pollinations_api_key)
    prompt = (
        f"A promotional poster for {event_title} in {event_city}, "
        f"vibes: {', '.join(vibes or [])}"
    )
    pollinations_url = await generator.generate_event_image(prompt)

    # Upload to Supabase Storage
    storage = SupabaseStorageService()
    await storage.ensure_bucket_exists()
    storage_url = await storage.upload_image_from_url(
        pollinations_url, event_id, api_key=generator.api_key
    )

    if storage_url:
        # Update the event with the Supabase Storage URL
        from sqlalchemy import text

        await session.execute(
            text("UPDATE events SET image_url = :image_url, updated_at = now() WHERE id = :id"),
            {"image_url": storage_url, "id": event_id},
        )
        if auto_commit:
            await session.commit()
        else:
            await session.flush()
        return storage_url

    # Fallback to Pollinations URL if storage upload fails
    return pollinations_url
