from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from aventi_backend.services.market_inventory import (
    MarketDescriptor,
    execute_market_scan,
)
from aventi_backend.services.market_inventory_state import MarketInventoryStateStore
from aventi_backend.services.providers import (
    MockScraper,
    ProviderConfig,
    ProviderConfigurationError,
    SerpApiEventScraper,
    build_market_scan_scraper,
)


class ProviderFactoryTests(TestCase):
    def test_serpapi_factory_accepts_injected_config(self) -> None:
        scraper = build_market_scan_scraper(
            {"sourceType": "serpapi", "sourceName": "scan"},
            provider_config=ProviderConfig(serpapi_api_key="serp-key"),
        )

        self.assertIsInstance(scraper, SerpApiEventScraper)
        self.assertEqual(scraper.api_key, "serp-key")

    def test_unknown_provider_falls_back_to_mock(self) -> None:
        scraper = build_market_scan_scraper({"sourceType": "unknown-provider"})

        self.assertIsInstance(scraper, MockScraper)


class SerpApiEventScraperTests(IsolatedAsyncioTestCase):
    async def test_missing_api_key_raises_typed_configuration_error(self) -> None:
        scraper = SerpApiEventScraper(api_key=None)

        with self.assertRaises(ProviderConfigurationError) as raised:
            await scraper.discover(city="Denver", angle="events")

        self.assertEqual(str(raised.exception), "SERPAPI_API_KEY is not configured")


class ExecuteMarketScanProviderConfigTests(IsolatedAsyncioTestCase):
    async def test_missing_serpapi_config_returns_skipped_scan(self) -> None:
        market = MarketDescriptor(key="denver|co|us", city="Denver", state="CO", country="US")
        settings = SimpleNamespace(serpapi_api_key=None, enable_verification=True)

        with (
            patch(
                "aventi_backend.services.market_scan_execution.get_settings",
                return_value=settings,
            ),
            patch.object(
                MarketInventoryStateStore,
                "refresh_market_inventory_state",
                new=AsyncMock(return_value=0),
            ),
        ):
            result = await execute_market_scan(
                object(),  # type: ignore[arg-type]
                market=market,
                angle="events",
                source_name="serpapi",
                source_type="serpapi",
            )

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "provider_configuration")
        self.assertEqual(result["scanMeta"]["providerError"], "SERPAPI_API_KEY is not configured")
        self.assertEqual(result["ingest"]["discovered"], 0)
