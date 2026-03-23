"""Usage: python scripts/make_figures.py
Reads outputs/tables/summary_benchmark.csv and raw CSVs,
writes PNG figures to outputs/figures/.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

ROOT_DIR = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT_DIR / "outputs" / "tables"
FIGURES_DIR = ROOT_DIR / "outputs" / "figures"

PIPELINE_COLORS = {"mfa": "#2196F3", "nemo": "#FF9800", "whisperx": "#4CAF50"}
PIPELINE_LABELS = {"mfa": "MFA", "nemo": "NeMo FA", "whisperx": "WhisperX"}


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _safe_float(value: str | None) -> float | None:
    if not value or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bar_chart(
    ax,
    labels: list[str],
    values: list[float | None],
    colors: list[str],
    ylabel: str,
    title: str,
    na_text: str = "N/A",
) -> None:
    x = range(len(labels))
    bars = ax.bar(
        x,
        [v if v is not None else 0 for v in values],
        color=colors,
        edgecolor="white",
        linewidth=1.2,
        width=0.55,
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    for bar, val in zip(bars, values):
        if val is None:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + ax.get_ylim()[1] * 0.01,
                na_text,
                ha="center",
                va="bottom",
                fontsize=9,
                color="#999999",
            )
        else:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + ax.get_ylim()[1] * 0.01,
                f"{val:.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )


def figure_ram_comparison(summary_rows: list[dict]) -> None:
    pipelines = [r["pipeline"] for r in summary_rows]
    labels = [PIPELINE_LABELS.get(p, p) for p in pipelines]
    colors = [PIPELINE_COLORS.get(p, "#888888") for p in pipelines]

    idle_vals = [_safe_float(r.get("idle_ram_mean_mb")) for r in summary_rows]
    peak_vals = [_safe_float(r.get("peak_ram_mean_mb")) for r in summary_rows]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    fig.suptitle("RAM Usage Comparison (mean across 18 samples)", fontsize=13, fontweight="bold")
    _bar_chart(axes[0], labels, idle_vals, colors, "RAM (MB)", "Idle RAM after startup")
    _bar_chart(axes[1], labels, peak_vals, colors, "RAM (MB)", "Peak RAM during alignment")
    fig.tight_layout()
    out = FIGURES_DIR / "fig_ram_comparison.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out.name}")


def figure_latency_comparison(summary_rows: list[dict]) -> None:
    pipelines = [r["pipeline"] for r in summary_rows]
    labels = [PIPELINE_LABELS.get(p, p) for p in pipelines]
    colors = [PIPELINE_COLORS.get(p, "#888888") for p in pipelines]

    load_vals = [_safe_float(r.get("load_time_mean_sec")) for r in summary_rows]
    tpw_vals = [_safe_float(r.get("time_per_word_mean_sec")) for r in summary_rows]
    total_vals = [_safe_float(r.get("total_time_mean_sec")) for r in summary_rows]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
    fig.suptitle("Latency Comparison (mean across 18 samples)", fontsize=13, fontweight="bold")
    _bar_chart(axes[0], labels, load_vals, colors, "Seconds", "Load / Total time per call")
    _bar_chart(axes[1], labels, tpw_vals, colors, "Seconds", "Time per word (mean)")
    _bar_chart(axes[2], labels, total_vals, colors, "Seconds", "Total inference time (mean)")
    fig.tight_layout()
    out = FIGURES_DIR / "fig_latency_comparison.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out.name}")


def figure_success_rate(summary_rows: list[dict]) -> None:
    pipelines = [r["pipeline"] for r in summary_rows]
    labels = [PIPELINE_LABELS.get(p, p) for p in pipelines]
    colors = [PIPELINE_COLORS.get(p, "#888888") for p in pipelines]

    success_vals = [_safe_float(r.get("success_rate_pct")) for r in summary_rows]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.set_title("Success Rate per Pipeline (18 samples)", fontsize=12, fontweight="bold", pad=10)
    x = range(len(labels))
    bars = ax.bar(
        x,
        [v if v is not None else 0 for v in success_vals],
        color=colors,
        edgecolor="white",
        linewidth=1.2,
        width=0.45,
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel("Success rate (%)", fontsize=10)
    ax.set_ylim(0, 115)
    ax.axhline(100, color="#cccccc", linestyle="--", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    for bar, val, pip in zip(bars, success_vals, pipelines):
        n_s = next((r.get("n_success", "") for r in summary_rows if r["pipeline"] == pip), "")
        n_t = next((r.get("n_samples", "") for r in summary_rows if r["pipeline"] == pip), "")
        lbl = f"{val:.0f}%\n({n_s}/{n_t})" if val is not None else "N/A"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            lbl,
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    out = FIGURES_DIR / "fig_success_rate.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out.name}")


def figure_tpw_scatter(raw_rows_by_pipeline: dict[str, list[dict]]) -> None:
    """Scatter: audio_duration_sec vs time_per_word_sec per pipeline."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_title(
        "Time per Word vs Audio Duration (successful runs only)",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    patches = []
    for pipeline, rows in raw_rows_by_pipeline.items():
        successful = [
            r for r in rows if str(r.get("success", "")).strip().lower() == "true"
        ]
        xs = [_safe_float(r.get("audio_duration_sec")) for r in successful]
        ys = [_safe_float(r.get("time_per_word_sec")) for r in successful]
        pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        if pairs:
            px, py = zip(*pairs)
            color = PIPELINE_COLORS.get(pipeline, "#888888")
            ax.scatter(px, py, color=color, alpha=0.75, s=55, label=PIPELINE_LABELS.get(pipeline, pipeline))
            patches.append(mpatches.Patch(color=color, label=PIPELINE_LABELS.get(pipeline, pipeline)))
    ax.set_xlabel("Audio duration (s)", fontsize=10)
    ax.set_ylabel("Time per word (s)", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.xaxis.grid(True, linestyle="--", alpha=0.4)
    if patches:
        ax.legend(handles=patches, fontsize=10)
    fig.tight_layout()
    out = FIGURES_DIR / "fig_tpw_scatter.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out.name}")


def figure_scalability(concurrency_rows_by_pipeline: dict[str, list[dict]]) -> None:
    """Line chart: concurrency level vs mean latency and success rate."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle("Scalability: Concurrency Level vs Performance", fontsize=13, fontweight="bold")

    axes[0].set_title("Mean total time per request", fontsize=11)
    axes[1].set_title("Success rate", fontsize=11)
    axes[2].set_title("Estimated total peak RAM (N × mean peak)", fontsize=11)

    has_data = False
    for pipeline, rows in concurrency_rows_by_pipeline.items():
        if not rows:
            continue
        has_data = True
        levels = sorted({
            int(r.get("concurrency_level") or 1)
            for r in rows
            if str(r.get("concurrency_level", "")).strip().isdigit()
        })
        color = PIPELINE_COLORS.get(pipeline, "#888888")
        label = PIPELINE_LABELS.get(pipeline, pipeline)

        mean_times, success_rates, est_rams = [], [], []
        for lvl in levels:
            lvl_rows = [r for r in rows if int(r.get("concurrency_level", 1)) == lvl]
            times = [v for r in lvl_rows if (v := _safe_float(r.get("total_time_sec"))) is not None]
            peaks = [v for r in lvl_rows if (v := _safe_float(r.get("peak_ram_mb"))) is not None]
            n_success = sum(1 for r in lvl_rows if str(r.get("success", "")).strip().lower() == "true")
            mean_times.append(sum(times) / len(times) if times else None)
            success_rates.append(n_success / len(lvl_rows) * 100 if lvl_rows else None)
            est_rams.append(sum(peaks) if peaks else None)

        valid_times = [(l, v) for l, v in zip(levels, mean_times) if v is not None]
        valid_suc = [(l, v) for l, v in zip(levels, success_rates) if v is not None]
        valid_rams = [(l, v) for l, v in zip(levels, est_rams) if v is not None]

        for ax, pairs, ylabel in zip(
            axes,
            [valid_times, valid_suc, valid_rams],
            ["Seconds", "Success rate (%)", "RAM (MB)"],
        ):
            if pairs:
                xs, ys = zip(*pairs)
                ax.plot(xs, ys, marker="o", color=color, label=label, linewidth=2, markersize=6)
                ax.set_ylabel(ylabel, fontsize=9)
                ax.set_xlabel("Concurrent users", fontsize=9)
                ax.set_xticks(levels)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.yaxis.grid(True, linestyle="--", alpha=0.4)

    if has_data:
        for ax in axes:
            ax.legend(fontsize=9)
        fig.tight_layout()
        out = FIGURES_DIR / "fig_scalability_comparison.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved {out.name}")
    else:
        plt.close(fig)
        print("  Skipped fig_scalability_comparison.png (no concurrency data found)")


def main() -> int:
    if not HAS_MPL:
        print("ERROR: matplotlib is not installed. Run: pip install matplotlib", file=sys.stderr)
        return 1

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows = _read_csv(TABLES_DIR / "summary_benchmark.csv")
    if not summary_rows:
        print("ERROR: summary_benchmark.csv not found. Run summarize_benchmark.py first.", file=sys.stderr)
        return 1

    raw_rows: dict[str, list[dict]] = {
        "mfa": _read_csv(TABLES_DIR / "raw_benchmark_mfa.csv"),
        "nemo": _read_csv(TABLES_DIR / "raw_benchmark_nemo.csv"),
        "whisperx": _read_csv(TABLES_DIR / "raw_benchmark_whisperx.csv"),
    }

    concurrency_rows: dict[str, list[dict]] = {
        "mfa": _read_csv(TABLES_DIR / "raw_concurrency_mfa.csv"),
        "nemo": _read_csv(TABLES_DIR / "raw_concurrency_nemo.csv"),
        "whisperx": _read_csv(TABLES_DIR / "raw_concurrency_whisperx.csv"),
    }

    print("Generating figures...")
    figure_ram_comparison(summary_rows)
    figure_latency_comparison(summary_rows)
    figure_success_rate(summary_rows)
    figure_tpw_scatter(raw_rows)
    figure_scalability(concurrency_rows)
    print(f"All figures saved to {FIGURES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
