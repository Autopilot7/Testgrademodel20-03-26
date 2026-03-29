"""Usage: python scripts/verify_splits.py [--splits-dir ...] [--output ...]

Generates a standalone HTML review page from phoneme split WAV clips.
Each clip has an inline audio player plus a verdict dropdown (OK / Cropped / Noisy / Silent / Wrong).
Open the output HTML file in any browser — no server required.
"""

from __future__ import annotations

import argparse
import base64
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SPLITS_DIR = ROOT_DIR / "outputs" / "phoneme_splits"

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phoneme Split Review</title>
<style>
  body {{ font-family: sans-serif; font-size: 14px; margin: 20px; background: #fafafa; }}
  h1 {{ font-size: 1.4em; margin-bottom: 4px; }}
  h2 {{ font-size: 1.1em; margin-top: 24px; margin-bottom: 6px;
        background: #e8eaf6; padding: 6px 10px; border-radius: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 12px; background: #fff; }}
  th {{ background: #3f51b5; color: #fff; padding: 6px 8px; text-align: left; font-size: 0.85em; }}
  td {{ border: 1px solid #ddd; padding: 5px 8px; vertical-align: middle; }}
  td.phoneme {{ font-size: 1.6em; font-family: "Noto Sans", "Segoe UI", sans-serif;
                text-align: center; width: 60px; }}
  td.ts {{ font-size: 0.8em; color: #555; white-space: nowrap; }}
  audio {{ height: 28px; }}
  select.verdict {{ padding: 2px 4px; }}
  input.notes {{ width: 160px; padding: 2px 4px; border: 1px solid #bbb; border-radius: 3px; }}
  .skipped {{ color: #aaa; font-style: italic; font-size: 0.85em; }}
  #export-btn {{ margin-top: 20px; padding: 8px 18px; background: #3f51b5; color: #fff;
                  border: none; border-radius: 4px; cursor: pointer; font-size: 1em; }}
  #export-btn:hover {{ background: #283593; }}
  #export-area {{ margin-top: 10px; width: 100%; height: 120px; font-family: monospace;
                   font-size: 0.8em; display: none; }}
  .summary {{ font-size: 0.85em; color: #444; margin-bottom: 4px; }}
</style>
</head>
<body>
<h1>Phoneme Split Review</h1>
<p class="summary">Generated: {generated_at} &nbsp;|&nbsp; Total clips: {total_clips} across {total_audio_ids} audio files</p>

{groups_html}

<button id="export-btn" onclick="exportVerdicts()">Export Verdicts as JSON</button>
<textarea id="export-area" readonly></textarea>

<script>
function exportVerdicts() {{
  const rows = document.querySelectorAll('tr[data-row-id]');
  const verdicts = [];
  rows.forEach(tr => {{
    const id = tr.getAttribute('data-row-id');
    const verdict = tr.querySelector('select.verdict').value;
    const notes = tr.querySelector('input.notes').value;
    verdicts.push({{ id: id, verdict: verdict, notes: notes }});
  }});
  const area = document.getElementById('export-area');
  area.value = JSON.stringify(verdicts, null, 2);
  area.style.display = 'block';
  area.select();
  try {{ document.execCommand('copy'); }} catch(e) {{}}
}}
</script>
</body>
</html>
"""

GROUP_TEMPLATE = """\
<h2>{audio_id} — &ldquo;{transcript}&rdquo; &nbsp;<span style="font-weight:normal;font-size:0.85em;color:#555">{n_clips} clips</span></h2>
<table>
<thead><tr>
  <th>#</th><th>Phoneme</th><th>Start–End (ms)</th><th>Duration</th><th>Audio</th><th>Verdict</th><th>Notes</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
"""

ROW_TEMPLATE = """\
<tr data-row-id="{row_id}">
  <td class="ts">{index}</td>
  <td class="phoneme">{phoneme}</td>
  <td class="ts">{start_ms}–{end_ms}&nbsp;ms</td>
  <td class="ts">{duration_ms}&nbsp;ms</td>
  <td><audio controls preload="none" src="{data_uri}"></audio></td>
  <td><select class="verdict" name="verdict_{row_id}">
    <option value="ok">OK</option>
    <option value="cropped">Cropped</option>
    <option value="noisy">Noisy</option>
    <option value="silent">Silent</option>
    <option value="wrong">Wrong</option>
  </select></td>
  <td><input class="notes" type="text" name="notes_{row_id}" placeholder="optional notes"></td>
</tr>
"""

SKIPPED_ROW_TEMPLATE = """\
<tr>
  <td class="ts"></td>
  <td class="ts skipped" colspan="6">skipped: {phoneme!r} ({skip_reason})</td>
</tr>
"""


def log_progress(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTML review page for phoneme split audio clips."
    )
    parser.add_argument(
        "--splits-dir",
        type=Path,
        default=DEFAULT_SPLITS_DIR,
        help="Root directory produced by split_phonemes.py.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output HTML path (default: splits_dir/review_<timestamp>.html).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_SPLITS_DIR / "all_splits_manifest.csv",
        help="Merged splits manifest CSV (default: splits_dir/all_splits_manifest.csv).",
    )
    parser.add_argument(
        "--benchmark-manifest",
        type=Path,
        default=ROOT_DIR / "data" / "common_voice_vi" / "selected" / "benchmark_manifest.csv",
        help="Original benchmark manifest for transcript lookup.",
    )
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def encode_wav_to_data_uri(wav_path: Path) -> str:
    data = wav_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:audio/wav;base64,{b64}"


def build_groups_html(
    splits_rows: list[dict[str, str]],
    transcript_by_id: dict[str, str],
) -> tuple[str, int, int]:
    """Build HTML for all audio groups. Returns (html, total_clips, total_audio_ids)."""
    # Group rows by audio_id
    groups: dict[str, list[dict]] = {}
    for row in splits_rows:
        aid = row["audio_id"]
        groups.setdefault(aid, []).append(row)

    groups_html_parts: list[str] = []
    total_clips = 0

    for audio_id, rows in groups.items():
        transcript = transcript_by_id.get(audio_id, "")
        n_clips = sum(1 for r in rows if r.get("skipped") == "False")
        rows_html_parts: list[str] = []

        for row in rows:
            if row.get("skipped") == "True":
                # Show silence as compact skipped row only for non-silence phonemes
                if row.get("phoneme"):
                    rows_html_parts.append(SKIPPED_ROW_TEMPLATE.format(
                        phoneme=row.get("phoneme", ""),
                        skip_reason=row.get("skip_reason", ""),
                    ))
                continue

            wav_path = Path(row["wav_path"])
            if not wav_path.exists():
                log_progress(f"  WARNING: wav not found: {wav_path}")
                continue

            data_uri = encode_wav_to_data_uri(wav_path)
            duration_ms = row.get("duration_ms", "?")
            try:
                start_ms = int(round(float(row["xmin"]) * 1000))
                end_ms = int(round(float(row["xmax"]) * 1000))
            except (ValueError, KeyError):
                start_ms = "?"
                end_ms = "?"

            row_id = f"{audio_id}_{row['index']}"
            rows_html_parts.append(ROW_TEMPLATE.format(
                row_id=row_id,
                index=row.get("index", ""),
                phoneme=row.get("phoneme", ""),
                start_ms=start_ms,
                end_ms=end_ms,
                duration_ms=duration_ms,
                data_uri=data_uri,
            ))
            total_clips += 1

        group_html = GROUP_TEMPLATE.format(
            audio_id=audio_id,
            transcript=transcript,
            n_clips=n_clips,
            rows_html="\n".join(rows_html_parts),
        )
        groups_html_parts.append(group_html)

    return "\n".join(groups_html_parts), total_clips, len(groups)


def main() -> int:
    args = parse_args()

    if not args.manifest.exists():
        log_progress(f"ERROR: splits manifest not found: {args.manifest}")
        log_progress("Run split_phonemes.py first.")
        return 1

    splits_rows = load_csv(args.manifest)
    log_progress(f"Loaded {len(splits_rows)} rows from {args.manifest}")

    # Load transcript lookup
    transcript_by_id: dict[str, str] = {}
    if args.benchmark_manifest.exists():
        for row in load_csv(args.benchmark_manifest):
            transcript_by_id[row["audio_id"]] = row.get("transcript_ref", "")

    groups_html, total_clips, total_audio_ids = build_groups_html(splits_rows, transcript_by_id)
    log_progress(f"Encoding {total_clips} clips across {total_audio_ids} audio files...")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.format(
        generated_at=generated_at,
        total_clips=total_clips,
        total_audio_ids=total_audio_ids,
        groups_html=groups_html,
    )

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = args.splits_dir / f"review_{ts}.html"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    log_progress(f"Review HTML written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
