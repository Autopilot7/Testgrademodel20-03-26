"""Usage: python -m pipelines.mfa.run_alignment --audio-id sample-01 --audio sample.wav --transcript "xin chao" --output-dir outputs/mfa/sample-01."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

from pipelines.common import build_parser, emit_result


def build_mfa_parser():
    parser = build_parser("MFA", transcript_optional=False)
    parser.add_argument(
        "--dictionary",
        default=os.environ.get("MFA_DICTIONARY_PATH", ""),
        help="Path to the MFA pronunciation dictionary. Defaults to MFA_DICTIONARY_PATH.",
    )
    parser.add_argument(
        "--acoustic-model",
        default=os.environ.get("MFA_ACOUSTIC_MODEL_PATH", ""),
        help="Path to the MFA acoustic model. Defaults to MFA_ACOUSTIC_MODEL_PATH.",
    )
    parser.add_argument(
        "--mfa-executable",
        default=os.environ.get("MFA_EXECUTABLE", "mfa"),
        help="MFA CLI executable or full path. Defaults to MFA_EXECUTABLE or `mfa`.",
    )
    parser.add_argument(
        "--mfa-root-dir",
        default=os.environ.get("MFA_ROOT_DIR", ""),
        help="Writable MFA root directory. Defaults to MFA_ROOT_DIR.",
    )
    parser.add_argument(
        "--num-jobs",
        type=int,
        default=1,
        help="Number of MFA jobs to use. Defaults to 1 for deterministic smoke runs.",
    )
    return parser


def sanitize_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)
    return cleaned.strip("_") or "sample"


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


def prepare_corpus(audio_id: str, audio_path: Path, transcript: str, output_dir: Path) -> tuple[Path, Path, str]:
    utterance_stem = sanitize_stem(audio_id or audio_path.stem)
    work_dir = output_dir / "work"
    corpus_dir = work_dir / "corpus"
    aligned_dir = output_dir / "aligned"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    if aligned_dir.exists():
        shutil.rmtree(aligned_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    aligned_dir.mkdir(parents=True, exist_ok=True)

    corpus_audio_path = corpus_dir / f"{utterance_stem}.wav"
    corpus_lab_path = corpus_dir / f"{utterance_stem}.lab"
    shutil.copy2(audio_path, corpus_audio_path)
    corpus_lab_path.write_text(transcript.strip(), encoding="utf-8")
    return corpus_dir, aligned_dir, utterance_stem


def collect_tree_rss_mb(process: "psutil.Process") -> float:
    rss_bytes = 0
    processes = [process, *process.children(recursive=True)]
    for current_process in processes:
        try:
            rss_bytes += current_process.memory_info().rss
        except psutil.Error:
            continue
    return rss_bytes / (1024 * 1024)


def build_mfa_environment(mfa_executable: str, mfa_root_dir: str) -> dict[str, str]:
    env = os.environ.copy()
    if mfa_root_dir:
        env["MFA_ROOT_DIR"] = str(Path(mfa_root_dir).resolve())
    executable_path = Path(mfa_executable)
    if executable_path.exists():
        env_root = executable_path.parent.parent
        path_prefixes = [
            str(env_root),
            str(env_root / "Library" / "bin"),
            str(env_root / "Scripts"),
        ]
        existing_path = env.get("PATH", "")
        env["PATH"] = ";".join(path_prefixes + [existing_path]) if existing_path else ";".join(path_prefixes)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_mfa_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> tuple[int, str, str, float | None, float | None]:
    idle_ram_mb: float | None = None
    peak_ram_mb: float | None = None
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_handle, tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        errors="replace",
    ) as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            env=env,
        )

        stop_event = threading.Event()

        def monitor_memory() -> None:
            nonlocal idle_ram_mb, peak_ram_mb
            if psutil is None:
                return
            try:
                parent = psutil.Process(process.pid)
            except psutil.Error:
                return
            first_sample = True
            while not stop_event.is_set():
                try:
                    rss_mb = collect_tree_rss_mb(parent)
                except psutil.Error:
                    break
                if first_sample and rss_mb > 0:
                    time.sleep(0.5)
                    try:
                        rss_mb = collect_tree_rss_mb(parent)
                    except psutil.Error:
                        break
                    idle_ram_mb = rss_mb
                    first_sample = False
                peak_ram_mb = rss_mb if peak_ram_mb is None else max(peak_ram_mb, rss_mb)
                if process.poll() is not None:
                    break
                time.sleep(0.1)

        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()
        process.wait()
        stop_event.set()
        monitor_thread.join(timeout=2)

        stdout_handle.seek(0)
        stderr_handle.seek(0)
        stdout = stdout_handle.read()
        stderr = stderr_handle.read()
    return process.returncode, stdout, stderr, idle_ram_mb, peak_ram_mb


def find_textgrid(aligned_dir: Path, utterance_stem: str) -> Path | None:
    preferred = aligned_dir / f"{utterance_stem}.TextGrid"
    if preferred.exists():
        return preferred
    matches = sorted(aligned_dir.rglob("*.TextGrid"))
    return matches[0] if matches else None


def resolve_resource(path_value: str, label: str) -> tuple[Path | None, str | None]:
    if not path_value:
        return None, f"Missing {label}. Set the CLI flag or the matching environment variable."
    path = Path(path_value)
    if not path.exists():
        return None, f"{label} does not exist: {path}"
    return path, None


def compact_notes(*parts: str) -> str:
    return " | ".join(part.strip() for part in parts if part and part.strip())


def main() -> int:
    parser = build_mfa_parser()
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    output_dir = args.output_dir.resolve()
    validation_error = validate_audio(audio_path)
    if validation_error:
        emit_result(
            pipeline="mfa",
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

    mfa_executable = shutil.which(args.mfa_executable) or args.mfa_executable
    if not shutil.which(args.mfa_executable) and not Path(args.mfa_executable).exists():
        emit_result(
            pipeline="mfa",
            audio_id=args.audio_id,
            output_dir=output_dir,
            artifact_path=None,
            success=False,
            notes=f"MFA executable not found: {args.mfa_executable}",
            load_time_sec=None,
            idle_ram_mb=None,
            peak_ram_mb=None,
            command=None,
            returncode=None,
        )
        return 1

    dictionary_path, dictionary_error = resolve_resource(args.dictionary, "MFA dictionary")
    acoustic_model_path, acoustic_model_error = resolve_resource(
        args.acoustic_model, "MFA acoustic model"
    )
    if dictionary_error or acoustic_model_error:
        emit_result(
            pipeline="mfa",
            audio_id=args.audio_id,
            output_dir=output_dir,
            artifact_path=None,
            success=False,
            notes=compact_notes(dictionary_error or "", acoustic_model_error or ""),
            load_time_sec=None,
            idle_ram_mb=None,
            peak_ram_mb=None,
            command=None,
            returncode=None,
        )
        return 1

    corpus_dir, aligned_dir, utterance_stem = prepare_corpus(
        audio_id=args.audio_id,
        audio_path=audio_path,
        transcript=args.transcript,
        output_dir=output_dir,
    )
    command = [
        str(mfa_executable),
        "align",
        str(corpus_dir),
        str(dictionary_path),
        str(acoustic_model_path),
        str(aligned_dir),
        "--single_speaker",
        "-j",
        str(args.num_jobs),
        "--clean",
    ]
    command_display = subprocess.list2cmdline(command)
    mfa_env = build_mfa_environment(
        mfa_executable=str(mfa_executable),
        mfa_root_dir=args.mfa_root_dir,
    )
    load_started = time.perf_counter()
    returncode, stdout, stderr, idle_ram_mb, peak_ram_mb = run_mfa_command(
        command,
        cwd=output_dir,
        env=mfa_env,
    )
    load_elapsed = time.perf_counter() - load_started

    artifact_path = find_textgrid(aligned_dir, utterance_stem)
    success = returncode == 0 and artifact_path is not None
    notes = compact_notes(
        "" if success else "MFA alignment did not produce a TextGrid artifact.",
        stderr,
        stdout,
    )
    emit_result(
        pipeline="mfa",
        audio_id=args.audio_id,
        output_dir=output_dir,
        artifact_path=str(artifact_path) if artifact_path else None,
        success=success,
        notes=notes,
        load_time_sec=load_elapsed,
        idle_ram_mb=idle_ram_mb,
        peak_ram_mb=peak_ram_mb,
        command=command_display,
        returncode=returncode,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
