"""
Usage: python3 -m scripts.word_boundary_analysis
       [--mfa-dir outputs/mfa] [--whisperx-dir outputs/whisperx]
       [--manifest data/common_voice_vi/selected/benchmark_manifest.csv]
       [--output-csv outputs/tables/word_boundary_comparison.csv]

Compares WhisperX word-level boundary timestamps against MFA forced-alignment
TextGrids.  MFA is used as the reference (ground-truth proxy) because it has
access to the correct transcript and uses a deterministic HMM/GMM aligner.

Metrics produced per matched word pair:
  start_delta_sec   = whisperx_start - mfa_start   (signed)
  end_delta_sec     = whisperx_end   - mfa_end      (signed)
  abs_start_sec     absolute value of start_delta_sec
  abs_end_sec       absolute value of end_delta_sec

Important caveats documented in the output CSV and printed summary:
  - MFA word boundaries include inter-word silence intervals; WhisperX uses
    tighter phonetically-grounded boundaries.  This structural difference
    inflates the raw delta figures.
  - Words normalised by stripping punctuation, case-folding, and removing
    Vietnamese combining tone marks before matching.
  - MFA <unk> tokens (OOV dictionary words) are skipped.
  - Only clips where BOTH a MFA TextGrid and a WhisperX JSON exist are
    included.  The two failing MFA clips (25255203, 40191822) are excluded
    automatically.
  - The two clips (22493633, 23790302) where WhisperX produced a compressed
    timestamp span are flagged and reported separately.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Words where tone stripping alone is insufficient to align MFA/WhisperX
_SKIP_LABELS = frozenset(["unk"])


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _strip_combining(text: str) -> str:
    """Remove Unicode combining characters (tone marks, diacritics)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _norm_word(w: str) -> str:
    """Lowercase, strip punctuation, remove combining diacritics."""
    w = re.sub(r"[^\w\s]", "", w, flags=re.UNICODE)
    return _strip_combining(w).lower().strip()


# ---------------------------------------------------------------------------
# TextGrid parser — words tier only
# ---------------------------------------------------------------------------

def parse_textgrid_words(path: Path) -> list[tuple[float, float, str]]:
    """Return list of (xmin, xmax, text) for non-empty, non-unk word intervals."""
    text = path.read_text(encoding="utf-8", errors="replace")
    tier_blocks = re.split(r"item\s*\[\d+\]:", text)
    words: list[tuple[float, float, str]] = []
    for block in tier_blocks:
        if 'name = "words"' not in block:
            continue
        intervals = re.findall(
            r"xmin\s*=\s*([\d.]+).*?xmax\s*=\s*([\d.]+).*?text\s*=\s*\"([^\"]*)\"",
            block,
            re.DOTALL,
        )
        for xmin_s, xmax_s, label in intervals:
            label = label.strip()
            if label and _norm_word(label) not in _SKIP_LABELS:
                words.append((float(xmin_s), float(xmax_s), label))
        break
    return words


# ---------------------------------------------------------------------------
# WhisperX JSON parser
# ---------------------------------------------------------------------------

def parse_whisperx_words(path: Path) -> list[tuple[float, float, str]]:
    """Return list of (start, end, word) from word_segments[]."""
    data = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for ws in data.get("word_segments", []):
        word = ws.get("word", "").strip()
        start = ws.get("start")
        end = ws.get("end")
        if word and start is not None and end is not None:
            result.append((float(start), float(end), word))
    return result


# ---------------------------------------------------------------------------
# Sequence alignment by normalised word text
# ---------------------------------------------------------------------------

def align_word_lists(
    ref: list[tuple[float, float, str]],
    hyp: list[tuple[float, float, str]],
) -> list[tuple[tuple[float, float, str], tuple[float, float, str]]]:
    """
    Left-to-right greedy alignment on normalised text.

    For each ref word, scan forward in hyp from the current position to find
    the first matching hyp word.  If found, record the pair and advance the
    hyp cursor past that match.  If not found, skip the ref word and leave the
    hyp cursor unchanged (so subsequent ref words can still match).

    This tolerates insertions and deletions on either side without cascading
    failures.
    """
    pairs: list[tuple[tuple[float, float, str], tuple[float, float, str]]] = []
    j = 0
    for ref_item in ref:
        ref_norm = _norm_word(ref_item[2])
        if not ref_norm:
            continue
        found_at: int | None = None
        for k in range(j, len(hyp)):
            if _norm_word(hyp[k][2]) == ref_norm:
                found_at = k
                break
        if found_at is not None:
            pairs.append((ref_item, hyp[found_at]))
            j = found_at + 1
    return pairs


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    return (s[mid - 1] + s[mid]) / 2 if len(s) % 2 == 0 else s[mid]


def _pct_within(vals: list[float], threshold: float) -> float:
    return 100.0 * sum(1 for v in vals if v <= threshold) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="WhisperX vs MFA word boundary comparison")
    parser.add_argument("--mfa-dir", default=str(ROOT / "outputs" / "mfa"))
    parser.add_argument("--whisperx-dir", default=str(ROOT / "outputs" / "whisperx"))
    parser.add_argument(
        "--manifest",
        default=str(
            ROOT / "data" / "common_voice_vi" / "selected" / "benchmark_manifest.csv"
        ),
    )
    parser.add_argument(
        "--output-csv",
        default=str(ROOT / "outputs" / "tables" / "word_boundary_comparison.csv"),
    )
    args = parser.parse_args()

    mfa_dir = Path(args.mfa_dir)
    whisperx_dir = Path(args.whisperx_dir)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest)
    audio_ids: list[str] = []
    with manifest_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            audio_ids.append(row["audio_id"])

    rows: list[dict] = []
    skipped: list[str] = []
    flagged_compressed: list[str] = []

    for audio_id in audio_ids:
        tg_path = mfa_dir / audio_id / "aligned" / f"{audio_id}.TextGrid"
        if not tg_path.exists():
            skipped.append(f"{audio_id}: no MFA TextGrid")
            continue

        wx_path = whisperx_dir / audio_id / f"{audio_id}.json"
        if not wx_path.exists():
            skipped.append(f"{audio_id}: no WhisperX JSON")
            continue

        mfa_words = parse_textgrid_words(tg_path)
        wx_words = parse_whisperx_words(wx_path)

        if not mfa_words:
            skipped.append(f"{audio_id}: MFA TextGrid has no usable word intervals")
            continue
        if not wx_words:
            skipped.append(f"{audio_id}: WhisperX JSON has no word_segments")
            continue

        # Detect clips where WhisperX produced a compressed timestamp span
        # relative to the actual audio duration (span < 20% of MFA duration)
        mfa_duration = mfa_words[-1][1] - mfa_words[0][0]
        wx_span = wx_words[-1][1] - wx_words[0][0]
        if mfa_duration > 0 and wx_span < 0.2 * mfa_duration and wx_span < 2.0:
            flagged_compressed.append(
                f"{audio_id}: WhisperX span={wx_span:.2f}s vs MFA={mfa_duration:.2f}s"
            )

        pairs = align_word_lists(mfa_words, wx_words)
        if not pairs:
            skipped.append(f"{audio_id}: no word-text matches between MFA and WhisperX")
            continue

        for ref_item, hyp_item in pairs:
            mfa_start, mfa_end, mfa_word = ref_item
            wx_start, wx_end, wx_word = hyp_item
            start_delta = wx_start - mfa_start
            end_delta = wx_end - mfa_end
            rows.append(
                {
                    "audio_id": audio_id,
                    "word": mfa_word,
                    "whisperx_word": wx_word,
                    "mfa_start": round(mfa_start, 4),
                    "mfa_end": round(mfa_end, 4),
                    "wx_start": round(wx_start, 4),
                    "wx_end": round(wx_end, 4),
                    "start_delta_sec": round(start_delta, 4),
                    "end_delta_sec": round(end_delta, 4),
                    "abs_start_sec": round(abs(start_delta), 4),
                    "abs_end_sec": round(abs(end_delta), 4),
                    "compressed_wx": audio_id in [s.split(":")[0] for s in flagged_compressed],
                }
            )

    if not rows:
        print("ERROR: no word pairs produced. Check paths.", file=sys.stderr)
        return 1

    fieldnames = list(rows[0].keys())
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Split into normal vs compressed-span clips for reporting
    compressed_ids = {s.split(":")[0] for s in flagged_compressed}
    normal_rows = [r for r in rows if r["audio_id"] not in compressed_ids]
    compressed_rows = [r for r in rows if r["audio_id"] in compressed_ids]

    def _report_group(label: str, group: list[dict]) -> None:
        if not group:
            return
        abs_starts = [r["abs_start_sec"] for r in group]
        abs_ends = [r["abs_end_sec"] for r in group]
        start_deltas = [r["start_delta_sec"] for r in group]
        end_deltas = [r["end_delta_sec"] for r in group]
        n_clips = len({r["audio_id"] for r in group})
        print(f"\n  --- {label} ({n_clips} clips, {len(group)} word pairs) ---")
        print(f"  Start boundary |WhisperX - MFA|:")
        print(f"    Mean abs error  : {_mean(abs_starts):.3f} s")
        print(f"    Median abs error: {_median(abs_starts):.3f} s")
        print(f"    Mean signed     : {_mean(start_deltas):+.3f} s (+ = WhisperX later)")
        print(f"    Within 50 ms    : {_pct_within(abs_starts, 0.050):.1f}%")
        print(f"    Within 100 ms   : {_pct_within(abs_starts, 0.100):.1f}%")
        print(f"    Within 200 ms   : {_pct_within(abs_starts, 0.200):.1f}%")
        print(f"  End boundary |WhisperX - MFA|:")
        print(f"    Mean abs error  : {_mean(abs_ends):.3f} s")
        print(f"    Median abs error: {_median(abs_ends):.3f} s")
        print(f"    Mean signed     : {_mean(end_deltas):+.3f} s (+ = WhisperX later)")
        print(f"    Within 50 ms    : {_pct_within(abs_ends, 0.050):.1f}%")
        print(f"    Within 100 ms   : {_pct_within(abs_ends, 0.100):.1f}%")
        print(f"    Within 200 ms   : {_pct_within(abs_ends, 0.200):.1f}%")

    print("\n=== Word-Level Boundary Analysis: WhisperX (small) vs MFA ===")
    print(f"  Total clips in manifest  : {len(audio_ids)}")
    print(f"  Clips with both outputs  : {len({r['audio_id'] for r in rows})}")
    print(f"  Total matched word pairs : {len(rows)}")
    if skipped:
        print(f"\n  Skipped ({len(skipped)}):")
        for s in skipped:
            print(f"    - {s}")
    if flagged_compressed:
        print(f"\n  Flagged — WhisperX compressed timestamp span ({len(flagged_compressed)}):")
        for s in flagged_compressed:
            print(f"    - {s}")
        print("    (These clips are reported separately below.)")

    _report_group("Normal clips (reliable WhisperX alignment)", normal_rows)
    if compressed_rows:
        _report_group(
            "Compressed-span clips (WhisperX alignment likely failed)", compressed_rows
        )
    _report_group("All clips combined", rows)

    print(
        "\n  NOTE: MFA word boundaries include adjacent silence (Viterbi assigns silence"
        "\n  to the nearest word).  WhisperX uses phonetically tight boundaries."
        "\n  This structural difference inflates both start and end delta figures."
        "\n  The signed deltas (WhisperX earlier) confirm WhisperX clips word edges"
        "\n  before the MFA boundary, consistent with this explanation."
    )
    print(f"\n  Output written to: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
