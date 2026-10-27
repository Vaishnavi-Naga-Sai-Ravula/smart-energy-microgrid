"""Create a self-contained AppSail source tree without touching source assets."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "PROBLEM_STATEMENT.md",
    "train_telemetry.csv",
    "sample_test_input.csv",
    "predict.py",
    "test_eval.py",
    "requirements.txt",
    "Procfile",
    "scripts/smoke_test.py",
    "README.md",
    "docs/submission-checklist.md",
]
DIRECTORIES = ["backend", "frontend"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="appsail_build", help="New, non-existing deployment staging directory")
    args = parser.parse_args()
    destination = (ROOT / args.output).resolve()
    if destination.parent != ROOT.resolve():
        raise SystemExit("Choose a new direct child directory inside this project.")
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing path: {destination}")
    destination.mkdir(parents=True)
    for filename in FILES:
        source = ROOT / filename
        if not source.is_file():
            raise SystemExit(f"Required project file is missing: {source}")
        (destination / filename).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / filename)
    for dirname in DIRECTORIES:
        shutil.copytree(ROOT / dirname, destination / dirname, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"AppSail source staged at: {destination}")
    print("No QuickML secrets are copied; add them only to AppSail environment settings.")


if __name__ == "__main__":
    main()
