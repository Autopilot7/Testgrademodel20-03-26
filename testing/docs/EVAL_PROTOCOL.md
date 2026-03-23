# EVAL_PROTOCOL.md

## Fair-comparison rule
Compare all methods on:
- RAM
- load time
- inference time
- concurrency behavior

Quality comparison must be split by scenario:
- transcript-based methods compared together
- no-transcript method evaluated separately

## Data preprocessing
- convert all files to WAV mono 16kHz
- record duration in manifest
- keep transcript_ref empty for unguided cases

## Output schema
Every benchmark row must include:
- pipeline
- audio_id
- audio_duration_sec
- num_words
- load_time_sec
- idle_ram_mb
- peak_ram_mb
- total_time_sec
- time_per_word_sec
- concurrency_level
- success
- notes

Rule 1

Do not replace the CSV schema once created; only extend it compatibly.

Rule 2

Each pipeline runner must emit the same JSON keys, even when some metrics are unavailable. Use null instead of inventing values.

Rule 3

Implement one pipeline at a time and verify with a smoke test before touching the next pipeline.