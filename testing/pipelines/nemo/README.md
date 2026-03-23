# NeMo Pipeline

Minimal organization:
- `run_alignment.py`: transcript-based runner entrypoint used by `scripts/benchmark_runner.py`

Sample command:
```bash
python pipelines/nemo/run_alignment.py --audio-id sample-01 --audio data/sample.wav --transcript "xin chao" --output-dir outputs/nemo/sample-01
```
