"""Usage: python -m pipelines.whisperx.run_alignment --audio-id sample-01 --audio sample.wav --output-dir outputs/whisperx/sample-01."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import wave
from pathlib import Path

from pipelines.common import build_parser, emit_result, run_with_ram_monitoring


def build_whisperx_parser():
    parser = build_parser("WhisperX", transcript_optional=True)
    parser.add_argument(
        "--whisperx-executable",
        default=os.environ.get("WHISPERX_EXECUTABLE", "whisperx"),
        help="WhisperX CLI executable. Defaults to WHISPERX_EXECUTABLE or `whisperx`.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("WHISPERX_MODEL", "small"),
        help="WhisperX ASR model to use.",
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("WHISPERX_LANGUAGE", "vi"),
        help="Language code for WhisperX transcription.",
    )
    parser.add_argument(
        "--device",
        default=os.environ.get("WHISPERX_DEVICE", "cpu"),
        help="Inference device for WhisperX.",
    )
    parser.add_argument(
        "--compute-type",
        default=os.environ.get("WHISPERX_COMPUTE_TYPE", "int8"),
        help="Compute type for WhisperX.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("WHISPERX_BATCH_SIZE", "1")),
        help="Batch size for WhisperX.",
    )
    return parser


def validate_audio(audio_path: Path) -> str | None:
    if not audio_path.exists():
        return f"Audio file does not exist: {audio_path}"
    if audio_path.suffix.lower() != ".wav":
        return "Input audio must be a WAV file."
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
    except wave.Error as exc:
        return f"Could not read WAV metadata: {exc}"
    if channels != 1:
        return f"Input audio must be mono; found {channels} channels."
    if sample_rate != 16000:
        return f"Input audio must be 16kHz; found {sample_rate}Hz."
    return None


def resolve_whisperx_command(executable_value: str) -> tuple[list[str] | None, str | None]:
    resolved = shutil.which(executable_value)
    if resolved:
        return [resolved], None
    path_candidate = Path(executable_value)
    if path_candidate.exists():
        return [str(path_candidate)], None
    if importlib.util.find_spec("whisperx"):
        return [sys.executable, "-m", "whisperx"], None
    return None, (
        "WhisperX is not installed. "
        "Set WHISPERX_EXECUTABLE to a valid CLI path or install the whisperx package."
    )


def find_output_artifact(output_dir: Path) -> Path | None:
    json_matches = sorted(output_dir.glob("*.json"))
    if json_matches:
        return json_matches[0]
    other_matches = sorted(output_dir.glob("*"))
    return other_matches[0] if other_matches else None


def compact_notes(*parts: str) -> str:
    return " | ".join(part.strip() for part in parts if part and part.strip())


def main() -> int:
    parser = build_whisperx_parser()
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    output_dir = args.output_dir.resolve()
    validation_error = validate_audio(audio_path)
    if validation_error:
        emit_result(
            pipeline="whisperx",
            audio_id=args.audio_id,
            output_dir=output_dir,
            artifact_path=None,
            success=False,
            notes=validation_error,
            load_time_sec=None,
            idle_ram_mb=None,
            peak_ram_mb=None,
            command=None,
            returncode=None,
        )
        return 1

    whisperx_command, whisperx_error = resolve_whisperx_command(args.whisperx_executable)
    if whisperx_error:
        dependency_state = {
            "torch_installed": bool(importlib.util.find_spec("torch")),
            "whisperx_installed": bool(importlib.util.find_spec("whisperx")),
        }
        emit_result(
            pipeline="whisperx",
            audio_id=args.audio_id,
            output_dir=output_dir,
            artifact_path=None,
            success=False,
            notes=f"{whisperx_error} Dependency state: {dependency_state}",
            load_time_sec=None,
            idle_ram_mb=None,
            peak_ram_mb=None,
            command=None,
            returncode=None,
        )
        return 1

    import subprocess

    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        *whisperx_command,
        str(audio_path),
        "--model",
        args.model,
        "--language",
        args.language,
        "--output_dir",
        str(output_dir),
        "--output_format",
        "json",
        "--device",
        args.device,
        "--compute_type",
        args.compute_type,
        "--batch_size",
        str(args.batch_size),
    ]
    command_display = subprocess.list2cmdline(command)
    import time
    started = time.perf_counter()
    returncode, stdout, stderr, idle_ram_mb, peak_ram_mb = run_with_ram_monitoring(
        command,
        cwd=output_dir,
        extra_env={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    elapsed = time.perf_counter() - started
    artifact_path = find_output_artifact(output_dir)
    success = returncode == 0 and artifact_path is not None
    notes = compact_notes(
        "" if success else "WhisperX did not produce an output artifact.",
        stderr,
        stdout if not success else "",
    )
    emit_result(
        pipeline="whisperx",
        audio_id=args.audio_id,
        output_dir=output_dir,
        artifact_path=str(artifact_path) if artifact_path else None,
        success=success,
        notes=notes,
        load_time_sec=elapsed,
        idle_ram_mb=idle_ram_mb,
        peak_ram_mb=peak_ram_mb,
        command=command_display,
        returncode=returncode,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
