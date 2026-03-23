"""Usage: python scripts/prepare_common_voice_benchmark.py."""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_CANDIDATES = [
    REPO_ROOT / "data" / "common_voice_vi" / "raw",
    REPO_ROOT / "data" / "commom_voice_vi" / "raw",
]
SELECTED_ROOT = REPO_ROOT / "data" / "common_voice_vi" / "selected"
PROCESSED_WAV_ROOT = REPO_ROOT / "data" / "common_voice_vi" / "processed" / "wav"
MANIFEST_PATH = SELECTED_ROOT / "benchmark_manifest.csv"
VALIDATED_FIELDS = ("path", "sentence")
MANIFEST_FIELDS = (
    "audio_id",
    "audio_path",
    "transcript_ref",
    "audio_duration_sec",
    "num_words",
)
BUCKET_SPECS = (
    ("short", lambda duration: duration < 4.0),
    ("medium", lambda duration: 4.0 <= duration <= 8.0),
    ("long", lambda duration: duration > 8.0),
)
SAMPLES_PER_BUCKET = 6
VLC_CANDIDATES = [
    "vlc",
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
]


def resolve_raw_root() -> Path:
    for candidate in DEFAULT_RAW_CANDIDATES:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in DEFAULT_RAW_CANDIDATES)
    raise FileNotFoundError(f"Could not locate Common Voice raw directory. Searched: {searched}")


def resolve_vlc_executable() -> str:
    for candidate in VLC_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        path_candidate = Path(candidate)
        if path_candidate.exists():
            return str(path_candidate)
    raise FileNotFoundError("Could not locate VLC executable for MP3 to WAV conversion.")


def load_transcripts(validated_path: Path) -> dict[str, str]:
    transcripts: dict[str, str] = {}
    with validated_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for field in VALIDATED_FIELDS:
            if field not in reader.fieldnames:
                raise ValueError(f"validated.tsv is missing required field: {field}")
        for row in reader:
            clip_name = row["path"].strip()
            sentence = row["sentence"].strip()
            if clip_name and sentence:
                transcripts[clip_name] = sentence
    return transcripts


def load_candidates(raw_root: Path) -> list[dict[str, object]]:
    transcripts = load_transcripts(raw_root / "validated.tsv")
    clips_root = raw_root / "clips"
    candidates: list[dict[str, object]] = []
    with (raw_root / "clip_durations.tsv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = {"clip", "duration[ms]"}
        if not expected.issubset(set(reader.fieldnames or [])):
            raise ValueError("clip_durations.tsv is missing required fields.")
        for row in reader:
            clip_name = row["clip"].strip()
            if clip_name not in transcripts:
                continue
            clip_path = clips_root / clip_name
            if not clip_path.exists():
                continue
            duration_sec = float(row["duration[ms]"]) / 1000.0
            transcript = transcripts[clip_name]
            candidates.append(
                {
                    "audio_id": Path(clip_name).stem,
                    "clip_name": clip_name,
                    "clip_path": clip_path,
                    "transcript_ref": transcript,
                    "audio_duration_sec": duration_sec,
                    "num_words": len(transcript.split()),
                }
            )
    return candidates


def choose_evenly_spaced(items: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    if len(items) < count:
        raise ValueError(f"Not enough items to select {count} samples.")
    if len(items) == count:
        return list(items)
    last_index = len(items) - 1
    selected: list[dict[str, object]] = []
    seen_indexes: set[int] = set()
    for i in range(count):
        index = round(i * last_index / (count - 1))
        while index in seen_indexes and index < last_index:
            index += 1
        while index in seen_indexes and index > 0:
            index -= 1
        seen_indexes.add(index)
        selected.append(items[index])
    return selected


def select_benchmark_subset(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for bucket_name, predicate in BUCKET_SPECS:
        bucket_items = [item for item in candidates if predicate(float(item["audio_duration_sec"]))]
        bucket_items.sort(key=lambda item: (float(item["audio_duration_sec"]), str(item["audio_id"])))
        if len(bucket_items) < SAMPLES_PER_BUCKET:
            raise ValueError(
                f"Bucket `{bucket_name}` has only {len(bucket_items)} items; need {SAMPLES_PER_BUCKET}."
            )
        chosen = choose_evenly_spaced(bucket_items, SAMPLES_PER_BUCKET)
        for item in chosen:
            item = dict(item)
            item["bucket"] = bucket_name
            selected.append(item)
    selected.sort(key=lambda item: (["short", "medium", "long"].index(str(item["bucket"])), float(item["audio_duration_sec"])))
    return selected


def convert_clip(vlc_executable: str, source_mp3: Path, target_wav: Path) -> None:
    target_wav.parent.mkdir(parents=True, exist_ok=True)
    if target_wav.exists():
        target_wav.unlink()
    temp_dir = target_wav.parent
    command = [
        vlc_executable,
        "-I",
        "dummy",
        str(source_mp3),
        "--sout",
        (
            f"#transcode{{acodec=s16l,channels=1,samplerate=16000}}:"
            f"std{{access=file,mux=wav,dst={target_wav}}}"
        ),
        "vlc://quit",
    ]
    result = subprocess.run(
        command,
        cwd=temp_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not target_wav.exists():
        raise RuntimeError(
            "VLC conversion failed for "
            f"{source_mp3.name}: returncode={result.returncode}, stderr={result.stderr.strip()}"
        )


def write_manifest(rows: list[dict[str, object]]) -> None:
    SELECTED_ROOT.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "audio_id": row["audio_id"],
                    "audio_path": row["audio_path"],
                    "transcript_ref": row["transcript_ref"],
                    "audio_duration_sec": f"{float(row['audio_duration_sec']):.3f}",
                    "num_words": row["num_words"],
                }
            )


def main() -> int:
    raw_root = resolve_raw_root()
    vlc_executable = resolve_vlc_executable()
    candidates = load_candidates(raw_root)
    selected = select_benchmark_subset(candidates)

    manifest_rows: list[dict[str, object]] = []
    for item in selected:
        target_wav = PROCESSED_WAV_ROOT / f"{item['audio_id']}.wav"
        convert_clip(vlc_executable, Path(item["clip_path"]), target_wav)
        manifest_rows.append(
            {
                "audio_id": item["audio_id"],
                "audio_path": str(Path("data/common_voice_vi/processed/wav") / f"{item['audio_id']}.wav"),
                "transcript_ref": item["transcript_ref"],
                "audio_duration_sec": item["audio_duration_sec"],
                "num_words": item["num_words"],
            }
        )

    write_manifest(manifest_rows)
    print(f"Wrote {len(manifest_rows)} rows to {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
