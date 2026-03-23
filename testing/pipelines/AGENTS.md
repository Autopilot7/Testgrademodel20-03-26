# pipelines/AGENTS.md

## Pipeline implementation rules
- Keep one folder per technique: mfa, nemo, whisperx
- Expose a consistent runner interface for all pipelines
- Prefer scripts that can be called from benchmark_runner.py
- Log runtime and output paths for every run
- Do not mix report-writing logic into pipeline code

## Required conventions
- each pipeline must have:
  - run_alignment.py or equivalent
  - README.md
  - sample command