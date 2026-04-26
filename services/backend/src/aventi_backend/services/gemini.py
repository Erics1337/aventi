from datetime import datetime, timedelta, UTC
from typing import Any
import json
import re
import httpx
from urllib.parse import urlparse

from google import genai
from google.genai import types
from pydantic import BaseModel, HttpUrl

from aventi_backend.core.settings import get_settings
from aventi_backend.services.providers import DiscoveryCandidate, SearchGroundedScraper, VerificationProvider


def _extract_response_text(response: Any) -> str | None:
    raw_text = getattr(response, "text", None)
    if not isinstance(raw_text, str):
        return None
    text = raw_text.strip()
    if not text:
        return None

    match = re.search(r"```(?:json)?\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
        return cleaned or None

    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    cleaned = text.strip()
    return cleaned or None

class GeminiEventSchema(BaseModel):
    title: str
    venue: str
    address: str
    date: str
    startTime: str
    price: str
    description: str
    category: str
    bookingUrl: HttpUrl
    platform: str
    music: str | None = None
    age: str | None = None
    dressCode: str | None = None
    vibes: list[str] = []
    experiences: list[str] = []

class GeminiEventScraper(SearchGroundedScraper):
    def __init__(self, source_name: str | None = None) -> None:
        self.source_name = source_name or "gemini"
        settings = get_settings()
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY must be set in the environment to use GeminiEventScraper")
        self.client = genai.Client(api_key=settings.google_api_key)

    def _is_valid_event_url(self, url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False

            # Reject generic root domains often used as placeholders
            if parsed.path == '/' or len(parsed.path) < 3:
                return False

            # Reject obvious hallucination domains or non-event sites
            deny_list = ['example.com', 'wikipedia.org', 'google.com', 'bing.com', 'yahoo.com', 'facebook.com']
            if any(d in parsed.netloc for d in deny_list) and len(parsed.path) < 5:
                return False

            # Explicitly reject Facebook events URLs
            if 'facebook.com' in parsed.netloc and parsed.path.startswith('/events'):
                return False

            # Known platform validators
            if 'eventbrite' in parsed.netloc and '/e/' not in parsed.path:
                return False

            return True
        except Exception:
            return False

    def _is_generic_title(self, title: str, city: str) -> bool:
        t = title.lower()
        c = city.lower()
        if f"events in {c}" in t:
            return True
        if f"{c} events" in t:
            return True
        if f"{c} nightlife" in t:
            return True
        if t in {"nightlife", "live music", "concert"}:
            return True
        return False

    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]:
        now = datetime.now(tz=UTC)
        start_str = now.strftime("%Y-%m-%d")
        end_date = now + timedelta(days=14)
        end_str = end_date.strftime("%Y-%m-%d")

        prompt = f"""You are a helpful event research assistant. Please search the web for upcoming events in {city}.

Focus area: {angle}

Search for real, upcoming events happening between {start_str} and {end_str}.
Try searching sites like Eventbrite, Dice, Resident Advisor, Ticketmaster, AXS, and local venue websites for {city}.

Please find 10 to 15 specific events and return them as a JSON array. For each event, include:
- title: the event name
- venue: where it's held
- address: venue address in {city}
- date: in YYYY-MM-DD format
- startTime: in HH:MM format (24h)
- price: ticket price or "Free"
- description: a 1-2 sentence description
- category: e.g. "Nightlife", "Live Music", "Arts & Culture", "Food & Drink", "Comedy", "Sports"
- bookingUrl: the direct URL to the event page (not a homepage)
- platform: e.g. "Eventbrite", "Dice", "Ticketmaster", "Venue Website"
- music: genre if applicable, or null
- age: e.g. "21+", "All Ages", or null
- dressCode: e.g. "Casual", or null
- vibes: list of 1-3 mood tags like ["high-energy", "chill"]
- experiences: list of 1-3 experience tags like ["live-dj", "outdoor"]

Return ONLY the JSON array, no markdown formatting. Example format:
[{{"title": "Example Event", "venue": "Example Venue", "address": "123 Main St", "date": "2026-04-10", "startTime": "20:00", "price": "$25", "description": "A great event.", "category": "Live Music", "bookingUrl": "https://example.com/event/123", "platform": "Eventbrite", "music": "Jazz", "age": "21+", "dressCode": "Smart Casual", "vibes": ["chill", "intimate"], "experiences": ["live-band"]}}]
"""

        response = self.client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.4,
                response_mime_type="application/json",
            )
        )

        try:
            text = _extract_response_text(response)
            if text is None:
                print("Failed to decode JSON from Gemini: empty response text")
                return []
            raw_items = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON from Gemini: {e}")
            print(f"Raw response: {response.text}")
            return []

        candidates: list[DiscoveryCandidate] = []
        for item in raw_items:
            try:
                # Basic validation
                url_str = str(item.get("bookingUrl", ""))
                if not self._is_valid_event_url(url_str):
                    continue

                title = item.get("title", "")
                if self._is_generic_title(title, city):
                    continue

                date_str = item.get("date")
                time_str = item.get("startTime", "19:00")
                if not date_str or not time_str:
                    continue

                # Time parsing (simplified for v1 - keeping format mostly as-is, but making standard ISO)
                # Ensure time has HH:MM format
                if len(time_str.split(':')) == 1:
                   time_str = f"{time_str}:00"

                try:
                    iso_datetime_str = f"{date_str}T{time_str}:00Z"
                    starts_at = datetime.fromisoformat(iso_datetime_str.replace("Z", "+00:00"))
                except ValueError:
                    starts_at = now # Fallback

                music = item.get("music")
                age = item.get("age")
                dress = item.get("dressCode")
                metadata: dict[str, Any] = {}

                # Build experiences list
                experiences = item.get("experiences", [])
                if music:
                    experiences.append(f"Music: {music}")
                if age:
                    experiences.append(f"Age: {age}")
                if dress:
                    experiences.append(f"Dress Code: {dress}")

                if "platform" in item:
                    metadata["platform"] = item["platform"]

                candidates.append(
                    DiscoveryCandidate(
                        title=title.strip(),
                        booking_url=url_str.strip(),
                        city=city,
                        source=self.source_name,
                        description=item.get("description", "").strip() or None,
                        category=item.get("category", "Nightlife & Social").strip(),
                        venue_name=item.get("venue", "").strip() or None,
                        venue_address=item.get("address", "").strip() or None,
                        starts_at=starts_at,
                        price_label=item.get("price", "").strip() or None,
                        vibes=item.get("vibes", []),
                        tags=[angle.replace(" ", "-"), "ai-discovered"],
                        metadata=metadata,
                    )
                )
            except Exception as e:
                # Skip items that fail parsing
                print(f"Error parsing Gemini event: {e}")
                continue

        return candidates

    async def enrich_event(self, description: str, context: str = "") -> dict[str, Any]:
        """
        Extracts structured metadata (vibes, category, tags, dress code, age limit, etc.)
        from a raw event description.
        """
        if not description or len(description.strip()) < 20:
            return {}

        prompt = f"""
            Analyze the following event description and extract structured metadata.

            EVENT CONTEXT: {context}
            EVENT DESCRIPTION:
            {description}

            FORMAT REQUIREMENTS:
            Return exactly a JSON object. Do NOT wrap the JSON in markdown formatting blocks.

            Extract the following keys, returning null if the information is not present:
            {{
                "category": "string (e.g. 'Nightlife', 'Live Music', 'Food & Drink', 'Arts & Culture', 'Networking')",
                "vibes": ["string", ...], (e.g. 'high-energy', 'chill', 'romantic', 'professional', max 3)
                "tags": ["string", ...], (e.g. 'techno', 'wine-tasting', 'startup', max 5)
                "dressCode": "string", (e.g. 'casual', 'smart casual', 'formal')
                "ageRestriction": "string", (e.g. '21+', '18+', 'All Ages')
                "isFree": boolean,
                "priceLabel": "string" (e.g. '$10 - $20', 'Free Entry')
            }}
        """

        response = self.client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            )
        )

        try:
            text = _extract_response_text(response)
            if text is None:
                print("Failed to extract metadata: empty response text")
                return {}
            data = json.loads(text)
            return {k: v for k, v in data.items() if v is not None}
        except Exception as e:
            print(f"Failed to extract metadata: {e}")
            return {}

class GeminiVerifier(VerificationProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY must be set in the environment to use GeminiVerifier")
        self.client = genai.Client(api_key=settings.google_api_key)

    async def verify_booking_url(self, url: str) -> bool | None:
        if not url or len(url) < 5:
            return False

        prompt = f"""
            You are an AI tasked with verifying if an event booking/ticketing URL is currently active and valid.

            URL to check: {url}

            Use Google Search to find information about this specific URL or event.
            Determine if:
            1. The event is real.
            2. The event has NOT been cancelled.
            3. The booking page is still active and accepting registrations/ticket sales (or at least still advertising an upcoming date).

            FORMAT REQUIREMENTS:
            Return exactly a JSON object. Do NOT wrap the JSON in markdown formatting blocks.

            {{
                "isValid": boolean,
                "reason": "string explaining why"
            }}
        """
        try:
            response = self.client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=0.1,
                    response_mime_type="application/json",
                )
            )
            text = _extract_response_text(response)
            if text is None:
                print("Failed to verify URL via Gemini: empty response text")
                return None
            data = json.loads(text)
            verdict = data.get("isValid")
            if isinstance(verdict, bool):
                return verdict
            print("Failed to verify URL via Gemini: missing boolean `isValid`")
            return None
        except Exception as e:
            print(f"Failed to verify URL via Gemini: {e}")
            return None

class GeminiImageGenerator:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY must be set in the environment to use GeminiImageGenerator")
        self.client = genai.Client(api_key=settings.google_api_key)

    async def generate_event_image(self, prompt: str) -> str:
        """
        Generates an image using Google's Imagen model and returns a base64 data URI.
        """
        import base64
        try:
            result = self.client.models.generate_images(
                model='imagen-3.0-generate-001',
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    aspect_ratio="3:4"
                )
            )

            if not result.generated_images:
                return ""

            image_bytes = result.generated_images[0].image.image_bytes
            b64_encoded = base64.b64encode(image_bytes).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_encoded}"

        except Exception as e:
            print(f"Failed to generate image via Imagen: {e}")
            # Fallback to a mock image if the API key doesn't support Imagen yet
            return "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?auto=format&fit=crop&w=900&q=80"


class PollinationsImageGenerator:
    """
    AI image generation using Pollinations.ai (FLUX/SDXL models).
    Free tier: 100 requests/minute without API key.
    Paid tier: Higher limits with API key (passed via Authorization header).
    Returns direct image URLs instead of base64 data URIs.
    """

    BASE_URL = "https://image.pollinations.ai/prompt"

    def __init__(self, api_key: str | None = None) -> None:
        """
        Args:
            api_key: Optional Pollinations.ai API key for higher rate limits.
                    Falls back to free tier if not provided.
        """
        self.api_key = api_key

    async def generate_event_image(self, prompt: str) -> str:
        """
        Generates an image using Pollinations.ai and returns a direct image URL.
        Uses 3:4 aspect ratio (768x1024) optimized for mobile event cards.
        """
        import urllib.parse
        import hashlib

        # Clean and encode the prompt
        cleaned_prompt = prompt.strip()
        encoded_prompt = urllib.parse.quote(cleaned_prompt)

        # Generate a consistent seed from the prompt for caching/reproducibility
        seed = int(hashlib.md5(cleaned_prompt.encode()).hexdigest(), 16) % 100000

        # Build URL with 3:4 aspect ratio (portrait mode for event posters)
        # Width: 768, Height: 1024 gives nice vertical event card proportions
        params: dict[str, str] = {
            "width": "768",
            "height": "1024",
            "seed": str(seed),
            "nologo": "true",  # Clean images without watermarks
            "enhance": "true",  # Better quality
        }

        # Security: API key must NOT be in query string (would be logged/leaked).
        # Pollinations.ai supports Authorization header for authenticated requests.
        # The caller must fetch this URL with headers: {"Authorization": self.api_key}
        # or use the free tier (no key required, lower rate limits).
        # See: BASE_URL, params, image_url below.

        query_string = urllib.parse.urlencode(params)
        image_url = f"{self.BASE_URL}/{encoded_prompt}?{query_string}"

        return image_url
