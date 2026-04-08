from datetime import datetime, UTC
from typing import Any
import json
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
            deny_list = ['example.com', 'wikipedia.org', 'google.com', 'bing.com', 'yahoo.com', 'facebook.com/events']
            if any(d in parsed.netloc for d in deny_list) and len(parsed.path) < 5:
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
        
        prompt = f"""
            Task: Massive broad search for ALL real, confirmed events in {city} for dates starting {start_str}.
            Include EVERY category: Nightlife, Concerts, Arts, Food, Sports, Workshops, Family, etc.
            
            AGENT FOCUS: {angle}
            
            STRICT RULES:
            - Google Search grounded ONLY. You must search the live web.
            - Direct direct direct booking URLs only.
            - Focus on HIGH VOLUME: Return as many unique, verified events as possible.
            - Returns ONLY events with VALID, ACTIVE booking/ticket/info URLs.
            - Do NOT invent events. Do NOT return generic "Nightlife in {city}" placeholders.
            - The 'bookingUrl' MUST be a deep link to the specific event page, NOT a homepage (e.g. 'eventbrite.com' is banned).
            
            FORMAT REQUIREMENTS:
            Return exactly a JSON array of objects. Do NOT wrap the JSON in markdown formatting blocks (like ```json ... ```). Just return the raw JSON array.
            
            Each object must strictly match this structure:
            {{
                "title": "string",
                "venue": "string",
                "address": "string",
                "date": "YYYY-MM-DD",
                "startTime": "HH:MM",
                "price": "string",
                "description": "string",
                "category": "string",
                "bookingUrl": "string (valid URL)",
                "platform": "string",
                "music": "string or null",
                "age": "string or null",
                "dressCode": "string or null",
                "vibes": ["string", ...],
                "experiences": ["string", ...]
            }}
        """
        
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.2, # Lower temperature for less hallucination
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
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
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
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=0.1,
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
