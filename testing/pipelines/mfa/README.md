# MFA Pipeline

Minimal organization:
- `run_alignment.py`: transcript-based runner entrypoint used by `scripts/benchmark_runner.py`

Sample command:
```bash
python -m pipelines.mfa.run_alignment --audio-id sample-01 --audio data/sample.wav --transcript "xin chao" --output-dir outputs/mfa/sample-01 --dictionary path/to/vietnamese.dict --acoustic-model path/to/vietnamese_model.zip
```

Environment fallback:
- `MFA_ROOT_DIR`
- `MFA_EXECUTABLE`
- `MFA_DICTIONARY_PATH`
- `MFA_ACOUSTIC_MODEL_PATH`

Benchmarking in this repository:
- Use the prepared dataset under `testing/data/common_voice_vi/`
- `scripts/benchmark_runner.py` benchmarks from a manifest CSV, not from a folder path directly
- The canonical manifest for the prepared Common Voice subset is:
  `testing/data/common_voice_vi/selected/benchmark_manifest.csv`

Example benchmark command:
```bash
python -m scripts.benchmark_runner --pipeline mfa --manifest data/common_voice_vi/selected/benchmark_manifest.csv --output-csv outputs/tables/raw_benchmark_mfa.csv
```
