"""Usage: python scripts/summarize_benchmark.py
Reads raw_benchmark_mfa.csv, raw_benchmark_nemo.csv, raw_benchmark_whisperx.csv
and writes outputs/tables/summary_benchmark.csv.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import mean, median

ROOT_DIR = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT_DIR / "outputs" / "tables"

PIPELINE_FILES = {
    "mfa": TABLES_DIR / "raw_benchmark_mfa.csv",
    "nemo": TABLES_DIR / "raw_benchmark_nemo.csv",
    "whisperx": TABLES_DIR / "raw_benchmark_whisperx.csv",
}

OUTPUT_CSV = TABLES_DIR / "summary_benchmark.csv"

SUMMARY_FIELDS = [
    "pipeline",
    "n_samples",
    "n_success",
    "n_failure",
    "success_rate_pct",
    "load_time_mean_sec",
    "load_time_median_sec",
    "idle_ram_mean_mb",
    "peak_ram_mean_mb",
    "peak_ram_max_mb",
    "total_time_mean_sec",
    "total_time_median_sec",
    "time_per_word_mean_sec",
    "time_per_word_median_sec",
    "notes",
]


def _safe_float(value: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _fmt(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return ""
    return f"{value:.{decimals}f}"


def summarize_pipeline(pipeline: str, csv_path: Path) -> dict:
    if not csv_path.exists():
        return {
            "pipeline": pipeline,
            "n_samples": 0,
            "notes": f"File not found: {csv_path.name}",
            **{f: "" for f in SUMMARY_FIELDS if f not in ("pipeline", "n_samples", "notes")},
        }

    rows: list[dict] = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        return {
            "pipeline": pipeline,
            "n_samples": 0,
            "notes": "CSV is empty.",
            **{f: "" for f in SUMMARY_FIELDS if f not in ("pipeline", "n_samples", "notes")},
        }

    n_success = sum(1 for r in rows if str(r.get("success", "")).strip().lower() == "true")
    n_failure = len(rows) - n_success
    success_rate = n_success / len(rows) * 100

    def vals(field: str) -> list[float]:
        return [v for r in rows if (v := _safe_float(r.get(field))) is not None]

    load_times = vals("load_time_sec")
    idle_rams = vals("idle_ram_mb")
    peak_rams = vals("peak_ram_mb")
    total_times = vals("total_time_sec")
    tpw = vals("time_per_word_sec")

    return {
        "pipeline": pipeline,
        "n_samples": len(rows),
        "n_success": n_success,
        "n_failure": n_failure,
        "success_rate_pct": _fmt(success_rate, 1),
        "load_time_mean_sec": _fmt(mean(load_times) if load_times else None),
        "load_time_median_sec": _fmt(median(load_times) if load_times else None),
        "idle_ram_mean_mb": _fmt(mean(idle_rams) if idle_rams else None, 1),
        "peak_ram_mean_mb": _fmt(mean(peak_rams) if peak_rams else None, 1),
        "peak_ram_max_mb": _fmt(max(peak_rams) if peak_rams else None, 1),
        "total_time_mean_sec": _fmt(mean(total_times) if total_times else None),
        "total_time_median_sec": _fmt(median(total_times) if total_times else None),
        "time_per_word_mean_sec": _fmt(mean(tpw) if tpw else None),
        "time_per_word_median_sec": _fmt(median(tpw) if tpw else None),
        "notes": "",
    }


def main() -> int:
    summary_rows = [summarize_pipeline(p, f) for p, f in PIPELINE_FILES.items()]
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary written to {OUTPUT_CSV}", file=sys.stdout)
    for row in summary_rows:
        print(
            f"  {row['pipeline']:10s}  n={row['n_samples']}  "
            f"success={row.get('n_success','')}  "
            f"peak_ram={row['peak_ram_mean_mb'] or 'N/A'} MB  "
            f"tpw_mean={row['time_per_word_mean_sec'] or 'N/A'} s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
