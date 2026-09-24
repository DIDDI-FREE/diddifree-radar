"""One-shot historical backfill of daily summaries for all enabled modules.

Usage (inside the collector/api container):
    python scripts/backfill.py --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.collector.collector import backfill_module
from app.core.db import init_db
from app.sources.catalog import enabled_modules


async def main(days: int) -> None:
    init_db()
    for module in enabled_modules():
        result = await backfill_module(module, days=days)
        print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(main(args.days))
