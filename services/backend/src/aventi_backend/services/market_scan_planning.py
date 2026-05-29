from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aventi_backend.services.market_descriptors import MarketDescriptor


@dataclass(frozen=True, slots=True)
class MarketScanPlan:
    angle: str
    source_name: str
    source_type: str | None = None
    source_url: str | None = None
    source_data: Any = None
    extra_payload: dict[str, Any] | None = None


class MarketScanPlanner:
    def __init__(
        self,
        *,
        discovery_angles: tuple[str, ...],
        page_budget_by_tier: dict[str, int],
        scan_windows: tuple[dict[str, Any], ...],
    ) -> None:
        self.discovery_angles = discovery_angles
        self.page_budget_by_tier = page_budget_by_tier
        self.scan_windows = scan_windows

    def admin_short_scan(self, market: MarketDescriptor) -> MarketScanPlan:
        short_window = self.scan_windows[0]
        tier = market.heat_tier if market.heat_tier in self.page_budget_by_tier else "cold"
        pages = self.page_budget_by_tier.get(tier, 1)
        return MarketScanPlan(
            angle=str(short_window["angle"]),
            source_name=f"admin-short:{market.city.lower()}",
            source_type="serpapi",
            source_data={"dateWindow": dict(short_window), "pages": pages},
            extra_payload={"scanType": "admin", "heatTier": market.heat_tier},
        )

    def targeted_scan(
        self,
        *,
        filters: dict[str, Any],
        latitude: float,
        longitude: float,
        filter_signature: str,
    ) -> MarketScanPlan:
        return MarketScanPlan(
            angle="targeted discovery",
            source_name="serpapi-targeted",
            source_type="serpapi",
            source_data={
                "mode": "targeted",
                "filters": filters,
                "latitude": latitude,
                "longitude": longitude,
                "filterSignature": filter_signature,
            },
            extra_payload={
                "filters": filters,
                "latitude": latitude,
                "longitude": longitude,
                "filterSignature": filter_signature,
            },
        )

    def warmup_discovery_scans(self) -> list[MarketScanPlan]:
        return [
            MarketScanPlan(
                angle=angle,
                source_name="serpapi",
                source_type="serpapi",
            )
            for angle in self.discovery_angles
        ]

    def bootstrap_short_scan(self, market: MarketDescriptor) -> MarketScanPlan:
        short_window = self.scan_windows[0]
        return MarketScanPlan(
            angle=str(short_window["angle"]),
            source_name=f"bootstrap-short:{market.city.lower()}",
            source_type="serpapi",
            source_data={
                "dateWindow": dict(short_window),
                "pages": self.page_budget_by_tier["bootstrap"],
            },
            extra_payload={"scanType": "bootstrap", "heatTier": "bootstrap"},
        )

    def weekly_scans(self, market: MarketDescriptor) -> list[MarketScanPlan]:
        pages = self.page_budget_by_tier.get(market.heat_tier, 1)
        return [
            MarketScanPlan(
                angle=str(window["angle"]),
                source_name=f"weekly-{window['label']}:{market.city.lower()}",
                source_type="serpapi",
                source_data={"dateWindow": dict(window), "pages": pages},
                extra_payload={"scanType": window["label"], "heatTier": market.heat_tier},
            )
            for window in self.scan_windows
        ]
