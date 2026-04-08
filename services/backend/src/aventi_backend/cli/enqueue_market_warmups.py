"""
CLI Script: enqueue_market_warmups
Command: aventi-enqueue-market-warmups

This script is used to queue up background 'warmup' jobs for recently requested
Aventi markets. It interacts with the MarketWarmupService to scan the database
and enqueue jobs so that market data is pre-calculated or cached for fast load times.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from aventi_backend.db.session import open_db_session
from aventi_backend.services.market_inventory import MarketWarmupService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aventi-enqueue-market-warmups",
        description="Queue market warmup jobs for recently requested Aventi markets.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of markets to inspect for warmups (default: 50).",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    async with open_db_session() as session:
        result = await MarketWarmupService(session).enqueue_scheduled_warmups(limit=args.limit)
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
