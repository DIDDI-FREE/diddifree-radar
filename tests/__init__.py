import os
import tempfile
from pathlib import Path

# Tests must never touch a real database or require live OIDC.
_test_dir = Path(tempfile.mkdtemp(prefix="pilotage-tests-"))
os.environ.setdefault("PILOTAGE_DB_PATH", str(_test_dir / "pilotage-test.sqlite3"))
os.environ["PILOTAGE_DATABASE_URL"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["PILOTAGE_ALLOW_INSECURE_HEADERS"] = "1"
os.environ["PILOTAGE_ENV"] = "local"
os.environ["PILOTAGE_LOG_LEVEL"] = "SILENT"
