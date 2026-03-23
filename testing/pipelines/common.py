from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


def build_parser(pipeline_name: str, transcript_optional: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Run the {pipeline_name} alignment pipeline."
    )
    parser.add_argument("--audio-id", required=True, help="Unique audio sample identifier.")
    parser.add_argument("--audio", required=True, help="Path to WAV mono 16kHz audio.")
    parser.add_argument(
        "--transcript",
        required=not transcript_optional,
        default="",
        help="Reference transcript. Optional only for unguided pipelines.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where runtime outputs should be written.",
    )
    return parser


def _collect_tree_rss_mb(process: "psutil.Process") -> float:
    rss_bytes = 0
    for proc in [process, *process.children(recursive=True)]:
        try:
            rss_bytes += proc.memory_info().rss
        except psutil.Error:
            continue
    return rss_bytes / (1024 * 1024)


def run_with_ram_monitoring(
    command: list[str],
    *,
    cwd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str, str, float | None, float | None]:
    """Run command in a subprocess and monitor its RSS memory.

    Returns (returncode, stdout, stderr, idle_ram_mb, peak_ram_mb).
    idle_ram_mb is the first RAM sample taken ~0.5 s after process start.
    peak_ram_mb is the maximum RSS observed during the entire run.
    Both are None when psutil is unavailable.
    """
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update(extra_env)

    idle_ram_mb: float | None = None
    peak_ram_mb: float | None = None

    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out_f,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err_f,
    ):
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=out_f,
            stderr=err_f,
            text=True,
            env=env,
        )

        stop_event = threading.Event()

        def _monitor() -> None:
            nonlocal idle_ram_mb, peak_ram_mb
            if psutil is None:
                return
            try:
                parent = psutil.Process(proc.pid)
            except psutil.Error:
                return
            first_sample = True
            while not stop_event.is_set():
                try:
                    rss_mb = _collect_tree_rss_mb(parent)
                except psutil.Error:
                    break
                if first_sample and rss_mb > 0:
                    time.sleep(0.5)
                    try:
                        rss_mb = _collect_tree_rss_mb(parent)
                    except psutil.Error:
                        break
                    idle_ram_mb = rss_mb
                    first_sample = False
                peak_ram_mb = rss_mb if peak_ram_mb is None else max(peak_ram_mb, rss_mb)
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

        monitor_thread = threading.Thread(target=_monitor, daemon=True)
        monitor_thread.start()
        proc.wait()
        stop_event.set()
        monitor_thread.join(timeout=2)

        out_f.seek(0)
        err_f.seek(0)
        return proc.returncode, out_f.read(), err_f.read(), idle_ram_mb, peak_ram_mb


def emit_result(
    *,
    pipeline: str,
    audio_id: str,
    output_dir: Path,
    success: bool,
    notes: str,
    load_time_sec: float | None = None,
    idle_ram_mb: float | None = None,
    peak_ram_mb: float | None = None,
    artifact_path: str | None = None,
    command: str | None = None,
    returncode: int | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "pipeline": pipeline,
        "audio_id": audio_id,
        "output_dir": str(output_dir),
        "artifact_path": artifact_path,
        "success": success,
        "notes": notes,
        "load_time_sec": load_time_sec,
        "idle_ram_mb": idle_ram_mb,
        "peak_ram_mb": peak_ram_mb,
        "command": command,
        "returncode": returncode,
    }
    print(json.dumps(result))
