from aventi_backend.services.market_descriptors import MarketDescriptor
from aventi_backend.services.market_scan_planning import MarketScanPlanner


def _planner() -> MarketScanPlanner:
    return MarketScanPlanner(
        discovery_angles=("Chill", "Energetic"),
        page_budget_by_tier={"hot": 3, "warm": 1, "bootstrap": 1},
        scan_windows=(
            {"label": "short_term", "angle": "events", "startDays": 0, "durationDays": 7},
            {"label": "long_term", "angle": "events", "startDays": 14, "durationDays": 45},
        ),
    )


def test_weekly_scans_use_heat_tier_page_budget() -> None:
    market = MarketDescriptor(
        key="denver|co|us",
        city="Denver",
        state="CO",
        country="US",
        heat_tier="hot",
    )

    plans = _planner().weekly_scans(market)

    assert [plan.source_name for plan in plans] == [
        "weekly-short_term:denver",
        "weekly-long_term:denver",
    ]
    assert [plan.source_data["pages"] for plan in plans] == [3, 3]
    assert [plan.extra_payload["scanType"] for plan in plans] == ["short_term", "long_term"]


def test_targeted_scan_includes_filter_signature_in_source_and_worker_payloads() -> None:
    plan = _planner().targeted_scan(
        filters={"date": "week"},
        latitude=39.7,
        longitude=-104.9,
        filter_signature="sig-1",
    )

    assert plan.angle == "targeted discovery"
    assert plan.source_type == "serpapi"
    assert plan.source_data["filterSignature"] == "sig-1"
    assert plan.extra_payload["filterSignature"] == "sig-1"


def test_bootstrap_and_warmup_plans_keep_expected_sources() -> None:
    market = MarketDescriptor(key="austin|tx|us", city="Austin", state="TX", country="US")

    bootstrap = _planner().bootstrap_short_scan(market)
    warmups = _planner().warmup_discovery_scans()

    assert bootstrap.source_name == "bootstrap-short:austin"
    assert bootstrap.extra_payload == {"scanType": "bootstrap", "heatTier": "bootstrap"}
    assert [(plan.angle, plan.source_name) for plan in warmups] == [
        ("Chill", "serpapi"),
        ("Energetic", "serpapi"),
    ]
