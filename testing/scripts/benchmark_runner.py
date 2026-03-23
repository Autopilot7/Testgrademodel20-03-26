"""Usage: python scripts/benchmark_runner.py --pipeline mfa --manifest benchmark_manifest.csv."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_TABLES_DIR = ROOT_DIR / "outputs" / "tables"
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


def log_progress(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one benchmark pass for a selected pipeline against a CSV manifest."
    )
    parser.add_argument(
        "--pipeline",
        required=True,
        choices=sorted(PIPELINE_MODULE_BY_NAME),
        help="Pipeline to benchmark.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="CSV manifest path. Expected columns: audio_id,audio_path,transcript_ref,audio_duration_sec,num_words.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=OUTPUT_TABLES_DIR / "raw_benchmark.csv",
        help="Where to append benchmark rows.",
    )
    parser.add_argument(
        "--concurrency-level",
        type=int,
        default=1,
        help="Recorded concurrency level for this run.",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used to invoke pipeline scripts.",
    )
    return parser.parse_args()


def load_manifest_rows(manifest_path: Path) -> list[dict[str, str]]:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Manifest is empty: {manifest_path}")
    return rows


def normalize_float(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"{float(value):.6f}"


def normalize_int(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(int(value))


def build_command(
    python_executable: str,
    pipeline: str,
    row: dict[str, str],
    output_dir: Path,
) -> list[str]:
    command = [
        python_executable,
        "-m",
        PIPELINE_MODULE_BY_NAME[pipeline],
        "--audio-id",
        row.get("audio_id", ""),
        "--audio",
        row.get("audio_path", ""),
        "--output-dir",
        str(output_dir),
    ]
    transcript = row.get("transcript_ref", "").strip()
    if transcript:
        command.extend(["--transcript", transcript])
    return command


def run_pipeline(
    python_executable: str,
    pipeline: str,
    row: dict[str, str],
    row_index: int,
    total_rows: int,
) -> dict[str, Any]:
    output_dir = ROOT_DIR / "outputs" / pipeline / row.get("audio_id", "unknown")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_command(python_executable, pipeline, row, output_dir)
    audio_id = row.get("audio_id", "")
    log_progress(
        f"[{row_index}/{total_rows}] Starting pipeline={pipeline} audio_id={audio_id}"
    )
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

    num_words = row.get("num_words", "")
    try:
        time_per_word_sec = total_time_sec / int(num_words) if int(num_words) > 0 else ""
    except ValueError:
        time_per_word_sec = ""

    combined_notes = " | ".join(
        part for part in [payload.get("notes", ""), *notes] if part
    )
    benchmark_row = {
        "pipeline": pipeline,
        "audio_id": audio_id,
        "audio_duration_sec": normalize_float(row.get("audio_duration_sec", "")),
        "num_words": normalize_int(num_words),
        "load_time_sec": normalize_float(payload.get("load_time_sec")),
        "idle_ram_mb": normalize_float(payload.get("idle_ram_mb")),
        "peak_ram_mb": normalize_float(payload.get("peak_ram_mb")),
        "total_time_sec": normalize_float(total_time_sec),
        "time_per_word_sec": normalize_float(time_per_word_sec),
        "concurrency_level": str(row.get("concurrency_level") or ""),
        "success": str(bool(payload.get("success", result.returncode == 0))),
        "notes": combined_notes,
    }
    log_progress(
        f"[{row_index}/{total_rows}] Finished pipeline={pipeline} "
        f"audio_id={audio_id} success={benchmark_row['success']} "
        f"total_time_sec={benchmark_row['total_time_sec'] or 'n/a'}"
    )
    return benchmark_row


def write_rows(output_csv: Path, rows: list[dict[str, Any]]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_csv.exists()
    with output_csv.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    manifest_rows = load_manifest_rows(args.manifest)
    log_progress(
        f"Loaded {len(manifest_rows)} manifest rows from {args.manifest} for pipeline={args.pipeline}"
    )
    benchmark_rows: list[dict[str, Any]] = []
    for index, row in enumerate(manifest_rows, start=1):
        benchmark_row = run_pipeline(
            python_executable=args.python_executable,
            pipeline=args.pipeline,
            row=row,
            row_index=index,
            total_rows=len(manifest_rows),
        )
        benchmark_row["concurrency_level"] = str(args.concurrency_level)
        benchmark_rows.append(benchmark_row)

    write_rows(args.output_csv, benchmark_rows)
    log_progress(f"Wrote {len(benchmark_rows)} benchmark rows to {args.output_csv}")
    print(
        json.dumps(
            {
                "pipeline": args.pipeline,
                "rows_written": len(benchmark_rows),
                "output_csv": str(args.output_csv),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
