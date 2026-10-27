"""Build a Python 3.12 Linux AppSail ZIP on Windows, macOS, or Linux.

The host Python runs pip and ZIP creation only. Bundled Linux libraries are not
imported on Windows. No Docker, WSL, or local Python 3.12 installation is needed.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from stage_catalyst import DIRECTORIES, FILES, ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="gridsense-appsail-python312.zip")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}. Choose another --output filename.")
    if not output.parent.is_dir():
        raise SystemExit("The output directory must already exist.")
    with tempfile.TemporaryDirectory(prefix="gridsense-appsail-") as temporary:
        stage = Path(temporary)
        for name in [*FILES, "requirements-appsail-python312.txt"]:
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        for name in DIRECTORIES:
            shutil.copytree(ROOT / name, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print("Downloading pinned Python 3.12 Linux x86_64 dependencies...", flush=True)
        subprocess.run([
            sys.executable, "-m", "pip", "install", "--no-cache-dir", "--no-compile",
            "--only-binary=:all:", "--platform", "manylinux2014_x86_64",
            "--python-version", "312", "--implementation", "cp", "--abi", "cp312",
            "--target", str(stage / ".app_deps"), "-r", str(ROOT / "requirements-appsail-python312.txt"),
        ], check=True)
        archive = stage / "upload.zip"
        print("Creating ZIP, including the .app_deps directory...", flush=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for file in sorted(stage.rglob("*")):
                if file == archive or not file.is_file() or "__pycache__" in file.parts or file.suffix == ".pyc":
                    continue
                zipped.write(file, file.relative_to(stage))
        with zipfile.ZipFile(archive) as zipped:
            required = {"backend/server.py", "frontend/index.html", ".app_deps/numpy/__init__.py", ".app_deps/sklearn/__init__.py"}
            if not required.issubset(zipped.namelist()) or zipped.testzip() is not None:
                raise SystemExit("Archive verification failed; no output was saved.")
        # Exclusive creation preserves a file another process might have created.
        with archive.open("rb") as source, output.open("xb") as target:
            shutil.copyfileobj(source, target)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"READY: {output}")
    print(f"Size: {output.stat().st_size / 1024**2:.1f} MiB; SHA256: {digest}")
    print("Upload this ZIP unchanged. Select Python 3.12 in AppSail.")
    print("Startup: sh -c 'PYTHONPATH=.app_deps python3 -u -m backend.server'")
    print("Actual AppSail deployment and live QuickML inference still require verification.")


if __name__ == "__main__":
    main()
