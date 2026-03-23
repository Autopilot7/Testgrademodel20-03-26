"""Usage: python scripts/concurrency_benchmark.py --pipeline mfa --manifest data/... --output-csv outputs/tables/raw_concurrency_mfa.csv

Runs a pipeline at concurrency levels 1, 3, 5 by launching N subprocesses
simultaneously.  Results follow the same CSV schema as benchmark_runner.py.
Each row records per-user metrics; concurrency_level records the batch size.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]

PIPELINE_MODULE_BY_NAME = {
    "mfa": "pipelines.mfa.run_alignment",
    "nemo": "pipelines.nemo.run_alignment",
    "whisperx": "pipelines.whisperx.run_alignment",
}

OUTPUT_FIELDS = [
    "pipeline",
    "audio_id",
    "audio_duration_sec",
    "num_words",
    "load_time_sec",
    "idle_ram_mb",
    "peak_ram_mb",
    "total_time_sec",
    "time_per_word_sec",
    "concurrency_level",
    "success",
    "notes",
]

DEFAULT_LEVELS = [1, 3, 5]


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run concurrency benchmarks (1, 3, 5 users) for a pipeline."
    )
    parser.add_argument("--pipeline", required=True, choices=sorted(PIPELINE_MODULE_BY_NAME))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT_DIR / "outputs" / "tables" / "raw_concurrency.csv",
    )
    parser.add_argument(
        "--levels",
        nargs="+",
        type=int,
        default=DEFAULT_LEVELS,
        help="Concurrency levels to test (default: 1 3 5).",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python interpreter used to run pipeline scripts.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def normalize_float(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return ""


def normalize_int(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return ""


def build_command(
    python_executable: str,
    pipeline: str,
    row: dict[str, str],
    output_dir: Path,
    extra_args: list[str] | None = None,
) -> list[str]:
    cmd = [
        python_executable,
        "-m",
        PIPELINE_MODULE_BY_NAME[pipeline],
        "--audio-id", row.get("audio_id", ""),
        "--audio", row.get("audio_path", ""),
        "--output-dir", str(output_dir),
    ]
    transcript = row.get("transcript_ref", "").strip()
    if transcript:
        cmd.extend(["--transcript", transcript])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def make_isolated_mfa_root(worker_index: int, concurrency_level: int) -> Path:
    """Create a per-worker MFA root dir so concurrent processes don't share model files."""
    base_root = Path(os.environ.get("MFA_ROOT_DIR", ""))
    isolated = ROOT_DIR / "outputs" / "mfa_root_concurrent" / f"c{concurrency_level}_w{worker_index}"
    isolated.mkdir(parents=True, exist_ok=True)
    if base_root.exists():
        pretrained_src = base_root / "pretrained_models"
        pretrained_dst = isolated / "pretrained_models"
        if pretrained_src.exists() and not pretrained_dst.exists():
            shutil.copytree(pretrained_src, pretrained_dst)
    return isolated


def run_one(
    python_executable: str,
    pipeline: str,
    row: dict[str, str],
    concurrency_level: int,
    worker_index: int = 0,
) -> dict[str, Any]:
    audio_id = row.get("audio_id", "unknown")
    output_dir = ROOT_DIR / "outputs" / pipeline / f"{audio_id}_c{concurrency_level}_w{worker_index}"
    output_dir.mkdir(parents=True, exist_ok=True)

    extra_args: list[str] = []
    if pipeline == "mfa" and concurrency_level > 1:
        isolated_root = make_isolated_mfa_root(worker_index, concurrency_level)
        extra_args = ["--mfa-root-dir", str(isolated_root)]

    command = build_command(python_executable, pipeline, row, output_dir, extra_args)

    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    total_time_sec = time.perf_counter() - started

    payload: dict[str, Any] = {}
    notes: list[str] = []
    if result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            notes.append("pipeline stdout was not valid JSON")
    if result.stderr.strip():
        notes.append(result.stderr.strip())
    if result.returncode != 0:
        notes.append(f"exit_code={result.returncode}")

    num_words_raw = row.get("num_words", "")
    try:
        num_words = int(num_words_raw)
        time_per_word = total_time_sec / num_words if num_words > 0 else ""
    except ValueError:
        time_per_word = ""

    combined_notes = " | ".join(
        p for p in [payload.get("notes", ""), *notes] if p
    )

    return {
        "pipeline": pipeline,
        "audio_id": audio_id,
        "audio_duration_sec": normalize_float(row.get("audio_duration_sec", "")),
        "num_words": normalize_int(num_words_raw),
        "load_time_sec": normalize_float(payload.get("load_time_sec")),
        "idle_ram_mb": normalize_float(payload.get("idle_ram_mb")),
        "peak_ram_mb": normalize_float(payload.get("peak_ram_mb")),
        "total_time_sec": normalize_float(total_time_sec),
        "time_per_word_sec": normalize_float(time_per_word),
        "concurrency_level": str(concurrency_level),
        "success": str(bool(payload.get("success", result.returncode == 0))),
        "notes": combined_notes,
    }


def run_batch(
    python_executable: str,
    pipeline: str,
    rows: list[dict[str, str]],
    concurrency_level: int,
) -> list[dict[str, Any]]:
    """Run len(rows) pipeline calls simultaneously and return per-user results."""
    log(f"Starting concurrency={concurrency_level} with {len(rows)} users simultaneously")
    batch_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(rows)) as executor:
        futures = [
            executor.submit(run_one, python_executable, pipeline, row, concurrency_level, idx)
            for idx, row in enumerate(rows)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    batch_elapsed = time.perf_counter() - batch_start
    n_success = sum(1 for r in results if r["success"] == "True")
    log(
        f"Finished concurrency={concurrency_level}: "
        f"success={n_success}/{len(rows)} "
        f"batch_wall_time={batch_elapsed:.2f}s"
    )
    return results


def write_rows(output_csv: Path, rows: list[dict[str, Any]]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_csv.exists()
    with output_csv.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    all_rows = load_manifest(args.manifest)
    log(f"Loaded {len(all_rows)} rows from {args.manifest}")

    total_written = 0

    for level in sorted(args.levels):
        if level > len(all_rows):
            log(f"WARNING: concurrency={level} requested but manifest has only {len(all_rows)} rows. Using all {len(all_rows)}.")
            selected = all_rows
        else:
            selected = all_rows[:level]

        batch_results = run_batch(
            python_executable=args.python_executable,
            pipeline=args.pipeline,
            rows=selected,
            concurrency_level=level,
        )
        write_rows(args.output_csv, batch_results)
        total_written += len(batch_results)
        log(f"Wrote {len(batch_results)} rows (concurrency={level}) to {args.output_csv}")

    log(f"Total {total_written} rows written to {args.output_csv}")
    print(json.dumps({
        "pipeline": args.pipeline,
        "levels_tested": sorted(args.levels),
        "rows_written": total_written,
        "output_csv": str(args.output_csv),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
