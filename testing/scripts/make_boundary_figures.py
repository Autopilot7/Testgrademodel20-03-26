"""
Usage: python3 -m scripts.make_boundary_figures
       [--boundary-csv outputs/tables/word_boundary_comparison.csv]
       [--backbone-csv outputs/tables/backbone_comparison.csv]
       [--output-dir outputs/figures]

Generates four PNG figures related to WhisperX word-level boundary quality
and multi-backbone latency/quality trade-offs.

Figures produced:
  fig_word_boundary_delta_hist.png
      Histogram of |start_delta| and |end_delta| (WhisperX vs MFA) per word.
      Normal clips and compressed-span clips are shown in separate panels.

  fig_word_boundary_scatter.png
      Scatter: MFA word start vs WhisperX word start, coloured by clip.
      Points on the diagonal = perfect alignment.

  fig_backbone_latency_ram.png
      Grouped bar chart: backbone vs total time (left axis) and peak RAM
      (right axis).  Measured bar (small) is solid; projected bars are hatched.
      A horizontal line marks the 4 GB Docker limit.

  fig_backbone_tradeoff.png
      Scatter: backbone param count (log x) vs latency (left panel) and
      projected word-boundary MAE start (right panel).  Annotations label
      each backbone.  Demonstrates the latency/quality trade-off.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker

ROOT = Path(__file__).resolve().parents[1]


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Figure 1: Boundary delta histogram
# ---------------------------------------------------------------------------

def fig_boundary_delta_hist(rows: list[dict], out_path: Path) -> None:
    normal = [r for r in rows if str(r.get("compressed_wx", "")).lower() == "false"]
    compressed = [r for r in rows if str(r.get("compressed_wx", "")).lower() == "true"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    fig.suptitle(
        "WhisperX (small) Word Boundary Error vs MFA Reference\n"
        "(negative = WhisperX earlier than MFA)",
        fontsize=12,
    )

    def _plot(ax, group, metric_key, title, color):
        vals = [_safe_float(r.get(metric_key)) for r in group]
        vals = [v for v in vals if v is not None]
        if not vals:
            ax.set_visible(False)
            return
        ax.hist(vals, bins=30, color=color, edgecolor="white", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=1.2, linestyle="--", label="0 s (perfect)")
        ax.axvline(sum(vals) / len(vals), color="red", linewidth=1.0, linestyle=":",
                   label=f"mean={sum(vals)/len(vals):+.2f}s")
        ax.set_xlabel("Delta (seconds)", fontsize=9)
        ax.set_ylabel("Word count", fontsize=9)
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=8)
        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f"))

    _plot(axes[0][0], normal, "start_delta_sec",
          f"Normal clips — start delta\n(n={len(normal)} words)", "#4c72b0")
    _plot(axes[0][1], normal, "end_delta_sec",
          f"Normal clips — end delta\n(n={len(normal)} words)", "#4c72b0")
    _plot(axes[1][0], compressed, "start_delta_sec",
          f"Compressed-span clips — start delta\n(n={len(compressed)} words)", "#dd8452")
    _plot(axes[1][1], compressed, "end_delta_sec",
          f"Compressed-span clips — end delta\n(n={len(compressed)} words)", "#dd8452")

    fig.text(
        0.5, 0.01,
        "Compressed-span clips: WhisperX produced a very short timestamp window\n"
        "(< 20% of audio duration) suggesting the phoneme aligner failed on these clips.",
        ha="center", fontsize=8, color="#555",
    )
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Figure 2: MFA start vs WhisperX start scatter
# ---------------------------------------------------------------------------

def fig_boundary_scatter(rows: list[dict], out_path: Path) -> None:
    audio_ids = sorted({r["audio_id"] for r in rows})
    cmap = plt.get_cmap("tab20")
    color_map = {aid: cmap(i / max(len(audio_ids), 1)) for i, aid in enumerate(audio_ids)}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(
        "WhisperX (small) vs MFA: Word Boundary Scatter\n"
        "(diagonal = perfect alignment)",
        fontsize=12,
    )

    for ax, start_key, label in [
        (axes[0], ("mfa_start", "wx_start"), "Word start time"),
        (axes[1], ("mfa_end", "wx_end"), "Word end time"),
    ]:
        ref_key, hyp_key = start_key
        xs = [_safe_float(r.get(ref_key)) for r in rows]
        ys = [_safe_float(r.get(hyp_key)) for r in rows]
        colors = [color_map[r["audio_id"]] for r in rows]
        valid = [(x, y, c) for x, y, c in zip(xs, ys, colors)
                 if x is not None and y is not None]
        if valid:
            vx, vy, vc = zip(*valid)
            ax.scatter(vx, vy, c=vc, s=18, alpha=0.75, linewidths=0)
        # diagonal
        all_vals = [v for pair in valid for v in (pair[0], pair[1])]
        if all_vals:
            lo, hi = min(all_vals), max(all_vals)
            ax.plot([lo, hi], [lo, hi], "k--", linewidth=1, label="Perfect alignment")
        ax.set_xlabel("MFA reference (seconds)", fontsize=9)
        ax.set_ylabel("WhisperX (seconds)", fontsize=9)
        ax.set_title(label, fontsize=10)
        ax.legend(fontsize=8)

    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Figure 3: Backbone latency + RAM grouped bar
# ---------------------------------------------------------------------------

def fig_backbone_latency_ram(backbone_rows: list[dict], out_path: Path) -> None:
    backbones = [r["backbone"] for r in backbone_rows]
    latencies = [_safe_float(r.get("total_time_mean_sec")) for r in backbone_rows]
    rams = [_safe_float(r.get("peak_ram_mb_mean")) for r in backbone_rows]
    sources = [r.get("source", "projected") for r in backbone_rows]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()

    x = range(len(backbones))
    bar_w = 0.35

    lat_bars = ax1.bar(
        [i - bar_w / 2 for i in x], latencies, bar_w,
        color=["#4c72b0" if s == "measured" else "#aec6e8" for s in sources],
        hatch=["" if s == "measured" else "////" for s in sources],
        edgecolor="gray", linewidth=0.7,
        label="Total time / clip (s)",
    )
    ram_bars = ax2.bar(
        [i + bar_w / 2 for i in x], rams, bar_w,
        color=["#dd8452" if s == "measured" else "#f5c59a" for s in sources],
        hatch=["" if s == "measured" else "////" for s in sources],
        edgecolor="gray", linewidth=0.7,
        label="Peak RAM (MB)",
    )

    ax2.axhline(4096, color="red", linewidth=1.5, linestyle="--", label="4 GB Docker limit")

    ax1.set_xticks(list(x))
    ax1.set_xticklabels(backbones, fontsize=10)
    ax1.set_ylabel("Total inference time per clip (s)", fontsize=10)
    ax2.set_ylabel("Peak RAM (MB)", fontsize=10)
    ax1.set_title(
        "WhisperX Backbone: Latency and RAM\n"
        "(solid = measured, hatched = projected from small)",
        fontsize=11,
    )

    solid_patch = mpatches.Patch(facecolor="#4c72b0", label="Latency — measured")
    proj_patch = mpatches.Patch(facecolor="#aec6e8", hatch="////", edgecolor="gray",
                                 label="Latency — projected")
    ram_patch = mpatches.Patch(facecolor="#dd8452", label="RAM — measured")
    ram_proj = mpatches.Patch(facecolor="#f5c59a", hatch="////", edgecolor="gray",
                               label="RAM — projected")
    limit_line = mpatches.Patch(color="red", label="4 GB Docker limit")
    ax2.legend(handles=[solid_patch, proj_patch, ram_patch, ram_proj, limit_line],
               loc="upper left", fontsize=8)

    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Figure 4: Backbone trade-off scatter
# ---------------------------------------------------------------------------

def fig_backbone_tradeoff(backbone_rows: list[dict], out_path: Path) -> None:
    backbones = [r["backbone"] for r in backbone_rows]
    params = [_safe_float(r.get("param_count_M")) for r in backbone_rows]
    latencies = [_safe_float(r.get("total_time_mean_sec")) for r in backbone_rows]
    maes = [_safe_float(r.get("approx_word_boundary_mae_start_sec")) for r in backbone_rows]
    sources = [r.get("source", "projected") for r in backbone_rows]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(
        "WhisperX Backbone: Latency and Alignment Quality Trade-off\n"
        "(solid markers = measured; hollow = projected)",
        fontsize=12,
    )

    for ax, y_vals, ylabel, title in [
        (axes[0], latencies, "Total time per clip (s)", "Inference latency"),
        (axes[1], maes,
         "Word boundary MAE — start (s)", "Alignment quality (lower = better)"),
    ]:
        for b, p, y, s in zip(backbones, params, y_vals, sources):
            if p is None or y is None:
                continue
            marker = "o" if s == "measured" else "D"
            fill = "full" if s == "measured" else "none"
            ax.plot(p, y, marker=marker, fillstyle=fill,
                    markersize=10, color="#4c72b0", markeredgecolor="#4c72b0",
                    linewidth=0)
            ax.annotate(b, (p, y), textcoords="offset points",
                        xytext=(6, 4), fontsize=9)

        ax.set_xscale("log")
        ax.set_xlabel("Parameter count (M)", fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
        ax.xaxis.set_minor_formatter(ticker.NullFormatter())
        ax.tick_params(axis="x", which="minor", bottom=False)

    measured_marker = plt.Line2D([0], [0], marker="o", color="w",
                                  markerfacecolor="#4c72b0", markersize=9,
                                  label="Measured")
    proj_marker = plt.Line2D([0], [0], marker="D", color="#4c72b0",
                              markerfacecolor="none", markersize=9,
                              label="Projected")
    axes[1].legend(handles=[measured_marker, proj_marker], fontsize=9)

    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate boundary quality and backbone figures")
    parser.add_argument(
        "--boundary-csv",
        default=str(ROOT / "outputs" / "tables" / "word_boundary_comparison.csv"),
    )
    parser.add_argument(
        "--backbone-csv",
        default=str(ROOT / "outputs" / "tables" / "backbone_comparison.csv"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "outputs" / "figures"),
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    boundary_path = Path(args.boundary_csv)
    backbone_path = Path(args.backbone_csv)

    if not boundary_path.exists():
        print(f"ERROR: {boundary_path} not found. Run word_boundary_analysis first.")
        return 1
    if not backbone_path.exists():
        print(f"ERROR: {backbone_path} not found. Run whisperx_backbone_benchmark first.")
        return 1

    boundary_rows = load_csv(boundary_path)
    backbone_rows = load_csv(backbone_path)

    print("\nGenerating figures ...")
    fig_boundary_delta_hist(boundary_rows, out_dir / "fig_word_boundary_delta_hist.png")
    fig_boundary_scatter(boundary_rows, out_dir / "fig_word_boundary_scatter.png")
    fig_backbone_latency_ram(backbone_rows, out_dir / "fig_backbone_latency_ram.png")
    fig_backbone_tradeoff(backbone_rows, out_dir / "fig_backbone_tradeoff.png")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
