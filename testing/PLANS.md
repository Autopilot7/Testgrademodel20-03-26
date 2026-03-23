# PLANS.md

## Objective
Complete the weekly work packet:
- investigate 3 alternative Vietnamese phoneme/alignment techniques
- evaluate RAM, time per word, and scalability on a 4GB Docker instance
- produce a written report with code snippets and graphs
- deadline: 24 March, 4:30pm

## Candidate techniques
1. MFA (transcript-based)
2. NeMo Forced Aligner (transcript-based)
3. WhisperX (no reference transcript)

## Benchmark protocol
### Dataset
- use benchmark_manifest.csv
- audio must be WAV, mono, 16kHz
- keep short / medium / long distribution

### Metrics
- model load time
- idle RAM after loading
- peak RAM during inference
- total inference time
- time per word
- concurrency at 1, 3, 5 simultaneous users
- success/failure/OOM count

## Deliverables
1. raw benchmark csv
2. summary table csv
3. figures:
   - RAM comparison
   - latency comparison
   - scalability comparison
4. report draft

## Execution order
1. make all 3 pipelines runnable
2. run single-user benchmarks
3. run concurrency benchmarks
4. summarize results
5. write report