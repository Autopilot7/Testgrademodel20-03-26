"""Usage: python scripts/split_phonemes.py [--manifest ...] [--mfa-output-dir ...] [--output-dir ...]

Parses MFA TextGrid files and splits WAV audio into individual phoneme clips.
Outputs one WAV file per phoneme interval plus a splits_manifest.csv per audio_id.
"""

from __future__ import annotations

import argparse
import csv
import sys
import wave
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT_DIR / "data" / "common_voice_vi" / "selected" / "benchmark_manifest.csv"
DEFAULT_MFA_OUTPUT_DIR = ROOT_DIR / "outputs" / "mfa"
DEFAULT_SPLITS_OUTPUT_DIR = ROOT_DIR / "outputs" / "phoneme_splits"

SPLITS_MANIFEST_FIELDS = [
    "audio_id",
    "phoneme",
    "index",
    "xmin",
    "xmax",
    "duration_ms",
    "wav_path",
    "skipped",
    "skip_reason",
]


def log_progress(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split WAV files into phoneme clips using MFA TextGrid timestamps."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="CSV manifest with columns: audio_id, audio_path, ...",
    )
    parser.add_argument(
        "--mfa-output-dir",
        type=Path,
        default=DEFAULT_MFA_OUTPUT_DIR,
        help="Root directory of MFA outputs (contains {audio_id}/aligned/{audio_id}.TextGrid).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_SPLITS_OUTPUT_DIR,
        help="Root directory for phoneme split outputs.",
    )
    parser.add_argument(
        "--min-duration-ms",
        type=float,
        default=20.0,
        help="Minimum phoneme duration in milliseconds to include (default: 20).",
    )
    return parser.parse_args()


def load_manifest_rows(manifest_path: Path) -> list[dict[str, str]]:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"Manifest is empty: {manifest_path}")
    return rows


def parse_textgrid_phones(textgrid_path: Path) -> list[tuple[str, float, float]]:
    """Parse the 'phones' tier from a Praat TextGrid file.

    Returns list of (phoneme_text, xmin_sec, xmax_sec) for ALL intervals,
    including silence (empty string). Caller decides what to skip.
    """
    text = textgrid_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    in_phones_tier = False
    results: list[tuple[str, float, float]] = []
    xmin: float | None = None
    xmax: float | None = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect entering/exiting the phones tier
        if line == 'name = "phones"':
            in_phones_tier = True
            i += 1
            continue
        # Next item block means we've left the phones tier
        if in_phones_tier and line.startswith("item ["):
            break

        if not in_phones_tier:
            i += 1
            continue

        # Parse interval fields
        if line.startswith("xmin ="):
            xmin = float(line.split("=", 1)[1].strip())
        elif line.startswith("xmax ="):
            xmax = float(line.split("=", 1)[1].strip())
        elif line.startswith("text ="):
            # text = "..." — extract value between first and last quote
            raw = line.split("=", 1)[1].strip()
            if raw.startswith('"') and raw.endswith('"'):
                phoneme = raw[1:-1]
            else:
                phoneme = raw.strip('"')
            if xmin is not None and xmax is not None:
                results.append((phoneme, xmin, xmax))
            xmin = None
            xmax = None

        i += 1

    return results


def sanitize_phoneme_filename(symbol: str) -> str:
    """Convert an IPA symbol to a safe ASCII filename component.

    ASCII letters/digits pass through; everything else becomes _Uxxxx.
    e.g. 't̪' -> 't_U0331', 'aː˧' -> 'a_U02D0_U02E7'
    """
    parts: list[str] = []
    for ch in symbol:
        if ch.isascii() and (ch.isalnum() or ch in "-_"):
            parts.append(ch)
        else:
            parts.append(f"_U{ord(ch):04X}")
    return "".join(parts) if parts else "empty"


def split_wav_segment(
    src_wav: Path,
    dest_wav: Path,
    xmin: float,
    xmax: float,
) -> None:
    """Extract a time-bounded WAV segment using only stdlib wave."""
    with wave.open(str(src_wav), "rb") as src:
        sample_rate = src.getframerate()
        n_channels = src.getnchannels()
        sampwidth = src.getsampwidth()

        start_frame = int(round(xmin * sample_rate))
        end_frame = int(round(xmax * sample_rate))
        n_frames = end_frame - start_frame

        src.setpos(start_frame)
        frames = src.readframes(n_frames)

    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest_wav), "wb") as dst:
        dst.setnchannels(n_channels)
        dst.setsampwidth(sampwidth)
        dst.setframerate(sample_rate)
        dst.writeframes(frames)


def process_audio_id(
    audio_id: str,
    audio_path: Path,
    textgrid_path: Path,
    output_dir: Path,
    min_duration_ms: float = 20.0,
) -> list[dict]:
    """Split one audio file into phoneme clips. Returns manifest rows."""
    intervals = parse_textgrid_phones(textgrid_path)
    rows: list[dict] = []
    phoneme_index = 0  # counts only non-silence, non-skipped

    for _i, (phoneme, xmin, xmax) in enumerate(intervals):
        duration_ms = (xmax - xmin) * 1000.0

        # Skip silence
        if phoneme == "":
            rows.append({
                "audio_id": audio_id,
                "phoneme": "",
                "index": "",
                "xmin": f"{xmin:.4f}",
                "xmax": f"{xmax:.4f}",
                "duration_ms": f"{duration_ms:.1f}",
                "wav_path": "",
                "skipped": "True",
                "skip_reason": "silence",
            })
            continue

        # Skip too-short segments
        if duration_ms < min_duration_ms:
            rows.append({
                "audio_id": audio_id,
                "phoneme": phoneme,
                "index": "",
                "xmin": f"{xmin:.4f}",
                "xmax": f"{xmax:.4f}",
                "duration_ms": f"{duration_ms:.1f}",
                "wav_path": "",
                "skipped": "True",
                "skip_reason": f"too_short_{duration_ms:.1f}ms",
            })
            continue

        phoneme_index += 1
        start_ms = int(round(xmin * 1000))
        end_ms = int(round(xmax * 1000))
        safe_name = sanitize_phoneme_filename(phoneme)
        wav_filename = f"{phoneme_index:04d}_{safe_name}_{start_ms}_{end_ms}.wav"
        wav_path = output_dir / audio_id / wav_filename

        try:
            split_wav_segment(audio_path, wav_path, xmin, xmax)
        except Exception as exc:
            rows.append({
                "audio_id": audio_id,
                "phoneme": phoneme,
                "index": str(phoneme_index),
                "xmin": f"{xmin:.4f}",
                "xmax": f"{xmax:.4f}",
                "duration_ms": f"{duration_ms:.1f}",
                "wav_path": "",
                "skipped": "True",
                "skip_reason": f"error: {exc}",
            })
            continue

        rows.append({
            "audio_id": audio_id,
            "phoneme": phoneme,
            "index": str(phoneme_index),
            "xmin": f"{xmin:.4f}",
            "xmax": f"{xmax:.4f}",
            "duration_ms": f"{duration_ms:.1f}",
            "wav_path": str(wav_path),
            "skipped": "False",
            "skip_reason": "",
        })

    return rows


def write_splits_manifest(output_path: Path, rows: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SPLITS_MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    manifest_rows = load_manifest_rows(args.manifest)
    log_progress(f"Loaded {len(manifest_rows)} rows from {args.manifest}")

    all_rows: list[dict] = []

    for i, row in enumerate(manifest_rows, start=1):
        audio_id = row["audio_id"]
        audio_path = Path(row["audio_path"])
        textgrid_path = args.mfa_output_dir / audio_id / "aligned" / f"{audio_id}.TextGrid"

        log_progress(f"[{i}/{len(manifest_rows)}] Processing {audio_id}")

        if not audio_path.exists():
            log_progress(f"  WARNING: audio not found: {audio_path}")
            continue
        if not textgrid_path.exists():
            log_progress(f"  WARNING: TextGrid not found: {textgrid_path}")
            continue

        rows = process_audio_id(
            audio_id=audio_id,
            audio_path=audio_path,
            textgrid_path=textgrid_path,
            output_dir=args.output_dir,
            min_duration_ms=args.min_duration_ms,
        )

        # Write per-audio manifest
        per_audio_manifest = args.output_dir / audio_id / "splits_manifest.csv"
        write_splits_manifest(per_audio_manifest, rows)

        n_kept = sum(1 for r in rows if r["skipped"] == "False")
        n_skipped = sum(1 for r in rows if r["skipped"] == "True")
        log_progress(f"  -> {n_kept} clips written, {n_skipped} skipped")

        all_rows.extend(rows)

    # Write merged manifest
    merged_manifest = args.output_dir / "all_splits_manifest.csv"
    write_splits_manifest(merged_manifest, all_rows)

    total_kept = sum(1 for r in all_rows if r["skipped"] == "False")
    total_skipped = sum(1 for r in all_rows if r["skipped"] == "True")
    log_progress(
        f"Done. Total clips: {total_kept} written, {total_skipped} skipped. "
        f"Merged manifest: {merged_manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
