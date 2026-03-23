"""Usage: python -m pipelines.nemo.run_alignment --audio-id sample-01 --audio sample.wav --transcript "xin chao" --output-dir outputs/nemo/sample-01."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

from pipelines.common import build_parser, emit_result, run_with_ram_monitoring


def build_nemo_parser():
    parser = build_parser("NeMo Forced Aligner", transcript_optional=False)
    parser.add_argument(
        "--nemo-align-script",
        default=os.environ.get("NEMO_ALIGN_SCRIPT", ""),
        help="Path to NeMo Forced Aligner align.py script. Defaults to NEMO_ALIGN_SCRIPT.",
    )
    parser.add_argument(
        "--nemo-python-executable",
        default=os.environ.get("NEMO_PYTHON_EXECUTABLE", sys.executable),
        help="Python executable used to run the NeMo aligner script.",
    )
    parser.add_argument(
        "--pretrained-name",
        default=os.environ.get("NEMO_PRETRAINED_NAME", ""),
        help="Pretrained NeMo CTC ASR model name for forced alignment.",
    )
    parser.add_argument(
        "--model-path",
        default=os.environ.get("NEMO_MODEL_PATH", ""),
        help="Path to a local NeMo CTC ASR model.",
    )
    parser.add_argument(
        "--device",
        default=os.environ.get("NEMO_DEVICE", "cpu"),
        help="Device passed to NeMo Forced Aligner.",
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


def compact_notes(*parts: str) -> str:
    return " | ".join(part.strip() for part in parts if part and part.strip())


def build_dependency_state() -> dict[str, bool]:
    modules = ["nemo", "torch", "hydra", "omegaconf"]
    return {f"{name}_installed": bool(importlib.util.find_spec(name)) for name in modules}


def resolve_preflight_blocker(args) -> str | None:
    if not args.nemo_align_script:
        return "Missing NeMo align script. Set NEMO_ALIGN_SCRIPT to tools/nemo_forced_aligner/align.py."
    align_script = Path(args.nemo_align_script)
    if not align_script.exists():
        return f"NeMo align script does not exist: {align_script}"
    if not (args.pretrained_name or args.model_path):
        return "Missing NeMo model selection. Set NEMO_PRETRAINED_NAME or NEMO_MODEL_PATH."
    if args.pretrained_name and args.model_path:
        return "Specify either NEMO_PRETRAINED_NAME or NEMO_MODEL_PATH, not both."
    if args.model_path and not Path(args.model_path).exists():
        return f"NeMo model path does not exist: {args.model_path}"
    dependency_state = build_dependency_state()
    if not dependency_state["nemo_installed"]:
        return f"NeMo package is not installed. Dependency state: {dependency_state}"
    if not dependency_state["hydra_installed"] or not dependency_state["omegaconf_installed"]:
        return f"NeMo alignment dependencies are incomplete. Dependency state: {dependency_state}"
    return None


def write_alignment_manifest(audio_path: Path, transcript: str, output_dir: Path) -> Path:
    manifest_path = output_dir / "nemo_alignment_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "audio_filepath": str(audio_path.resolve()),
                    "text": transcript.strip(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return manifest_path


def build_nemo_command(args, manifest_path: Path, output_dir: Path) -> list[str]:
    command = [
        args.nemo_python_executable,
        str(Path(args.nemo_align_script).resolve()),
        f"manifest_filepath={manifest_path.resolve()}",
        f"output_dir={output_dir.resolve()}",
        f"transcribe_device={args.device}",
    ]
    if args.pretrained_name:
        command.append(f'pretrained_name="{args.pretrained_name}"')
    else:
        command.append(f"model_path={Path(args.model_path).resolve()}")
    return command


def find_output_artifact(output_dir: Path, audio_id: str) -> Path | None:
    expected_manifest = output_dir / "nemo_alignment_manifest_with_output_file_paths.json"
    if expected_manifest.exists():
        return expected_manifest
    word_ctm = output_dir / "ctm" / "words" / f"{audio_id}.ctm"
    if word_ctm.exists():
        return word_ctm
    ctm_matches = sorted(output_dir.rglob("*.ctm"))
    if ctm_matches:
        return ctm_matches[0]
    json_matches = sorted(output_dir.glob("*.json"))
    return json_matches[0] if json_matches else None


def main() -> int:
    parser = build_nemo_parser()
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    output_dir = args.output_dir.resolve()
    validation_error = validate_audio(audio_path)
    if validation_error:
        emit_result(
            pipeline="nemo",
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

    blocker = resolve_preflight_blocker(args)
    if blocker:
        emit_result(
            pipeline="nemo",
            audio_id=args.audio_id,
            output_dir=output_dir,
            artifact_path=None,
            success=False,
            notes=blocker,
            load_time_sec=None,
            idle_ram_mb=None,
            peak_ram_mb=None,
            command=None,
            returncode=None,
        )
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_alignment_manifest(audio_path, args.transcript, output_dir)
    command = build_nemo_command(args, manifest_path, output_dir)
    command_display = subprocess.list2cmdline(command)
    started = time.perf_counter()
    returncode, stdout, stderr, idle_ram_mb, peak_ram_mb = run_with_ram_monitoring(
        command,
        cwd=output_dir,
    )
    elapsed = time.perf_counter() - started
    artifact_path = find_output_artifact(output_dir, args.audio_id)
    success = returncode == 0 and artifact_path is not None
    notes = compact_notes(
        "" if success else "NeMo did not produce an alignment artifact.",
        stderr,
        stdout if not success else "",
    )
    emit_result(
        pipeline="nemo",
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
