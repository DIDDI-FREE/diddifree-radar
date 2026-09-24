"""Entry point for the Pilotage collection loop container."""

from __future__ import annotations

import asyncio

from app.collector.collector import run_forever
from app.core.db import init_db


def main() -> None:
    init_db()
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
