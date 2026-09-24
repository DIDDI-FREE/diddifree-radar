from __future__ import annotations

import json
import os
import sys
import time


def log_json(payload: dict) -> None:
    level = os.getenv("PILOTAGE_LOG_LEVEL", "INFO").upper()
    if level == "SILENT":
        return
    print(json.dumps({"app": "pilotage", **payload}, default=str), file=sys.stdout, flush=True)


class Stopwatch:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
