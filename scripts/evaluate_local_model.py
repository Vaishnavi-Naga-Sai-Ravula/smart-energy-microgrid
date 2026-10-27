"""Print honest chronological holdout metrics for the local demo model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.model_service import _load_local_model


if __name__ == "__main__":
    _, evaluation = _load_local_model()
    print("LOCAL DEMONSTRATION MODEL ONLY — these are not QuickML metrics.")
    print(json.dumps(evaluation, indent=2))
