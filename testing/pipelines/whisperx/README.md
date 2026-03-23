# WhisperX Pipeline

Minimal organization:
- `run_alignment.py`: no-reference runner entrypoint used by `scripts/benchmark_runner.py`

Sample command:
```bash
python pipelines/whisperx/run_alignment.py --audio-id sample-01 --audio data/sample.wav --output-dir outputs/whisperx/sample-01
```
