# WhisperX Alignment Benchmarking

Benchmark suite for three Vietnamese audio alignment pipelines — **MFA**, **NeMo Forced Aligner**, and **WhisperX** — evaluated on 18 Mozilla Common Voice Vietnamese clips under a 4 GB Docker memory constraint.

---

## Repository layout

```
testing/
  data/
    common_voice_vi/selected/benchmark_manifest.csv   18-clip manifest
  pipelines/
    mfa/run_alignment.py       MFA runner (HMM/GMM forced alignment)
    nemo/run_alignment.py      NeMo Forced Aligner runner (CTC neural)
    whisperx/run_alignment.py  WhisperX runner (Whisper ASR + wav2vec2 aligner)
    common.py                  Shared RAM monitoring + result emission
  scripts/
    benchmark_runner.py           Single-user benchmark orchestrator
    concurrency_benchmark.py      Concurrency benchmark (1/3/5 users)
    summarize_benchmark.py        Aggregate summary table
    word_boundary_analysis.py     WhisperX vs MFA word-level boundary delta
    whisperx_backbone_benchmark.py  Backbone latency/RAM/quality comparison table
    make_boundary_figures.py      Word boundary and backbone comparison figures
    make_figures.py               Original benchmark figures (RAM, latency, scalability)
    prepare_common_voice_benchmark.py  Dataset preparation
    export_report.py              report.md -> report.html
  outputs/
    tables/                  Raw and summary CSVs
    figures/                 PNG charts
    whisperx/                WhisperX JSON alignment outputs
    mfa/                     MFA TextGrid outputs
    nemo/                    NeMo CTM / ASS outputs
  docs/
    EVAL_PROTOCOL.md
    SETUP_AND_BENCHMARK_GUIDE.md
  report/
    report.md                Full benchmark report
    report.html              HTML export
```

---

## Quick results summary

| Pipeline | Success | Peak RAM | Time/word | Fits 4 GB | Scales to 5 users |
|---|---|---|---|---|---|
| MFA | 16/18 (89%) | **311 MB** | 3.20 s | Yes | Yes |
| NeMo FA | 18/18 (100%) | **5,279 MB** | 6.64 s | **No** | No |
| WhisperX | 18/18 (100%) | **1,067 MB** | 6.78 s | Yes | Yes |

Full results, scenario analysis, and recommendations are in `testing/report/report.md`.

---

## WhisperX backbone comparison (small measured; medium/large/large-v2 projected)

| Backbone | Params | Peak RAM | Total time | Fits 4 GB |
|---|---|---|---|---|
| small | 39 M | ~1.1 GB | ~47 s | Yes |
| medium | 307 M | ~3.0 GB | ~96 s | Yes |
| large | 1,550 M | ~5.5 GB | ~188 s | **No** |
| large-v2 | 1,550 M | ~5.8 GB | ~207 s | **No** |

Key finding: latency scales ~4× from small to large; RAM crosses the 4 GB limit between medium and large. Under a 4 GB constraint, `medium` is the largest viable backbone. See `testing/outputs/tables/backbone_comparison.csv` and `testing/outputs/figures/fig_backbone_latency_ram.png`.

---

## Word-level boundary quality (WhisperX small vs MFA reference)

Alignment delta computed by `scripts/word_boundary_analysis.py` over 16 clips where both MFA TextGrid and WhisperX JSON outputs exist (62 matched word pairs, normal clips only).

| Metric | Mean abs error | Within 100 ms |
|---|---|---|
| Start boundary | ~1.37 s | ~13% |
| End boundary | ~1.55 s | ~2% |

The large absolute errors are partly structural: MFA word intervals include trailing silence (Viterbi boundary), while WhisperX uses phonetically tighter edges. WhisperX timestamps are consistently earlier (negative signed delta), which is consistent with this explanation.

WhisperX `small` also produced severely **compressed timestamp spans** on 10/18 Vietnamese clips (span < 20% of audio duration), indicating the phoneme aligner partially failed. Larger Whisper backbones reduce ASR errors, which reduces compressed-span failures, but the word-level alignment quality is ultimately governed by the wav2vec2 phoneme model, not the ASR backbone size.

See `testing/outputs/tables/word_boundary_comparison.csv` and `testing/outputs/figures/fig_word_boundary_delta_hist.png`.

---

## Audio dataset

This repository does **not** include audio files. The benchmark was run against 18 WAV files (mono, 16 kHz) from Mozilla Common Voice Vietnamese. To reproduce:

1. Download Common Voice Vietnamese from [commonvoice.mozilla.org](https://commonvoice.mozilla.org).
2. Run `python3 -m scripts.prepare_common_voice_benchmark` to produce the processed WAV files and manifest.

Paths assume the audio is placed at `testing/data/common_voice_vi/processed/wav/`.

---

## Running the analysis scripts

All commands run from the `testing/` directory:

```bash
# Word-level boundary analysis (WhisperX vs MFA)
python3 -m scripts.word_boundary_analysis

# Backbone comparison table (small measured + projections)
python3 -m scripts.whisperx_backbone_benchmark

# Generate all boundary and backbone figures
python3 -m scripts.make_boundary_figures

# Original benchmark figures (RAM, latency, scalability)
python3 -m scripts.make_figures

# Export report to HTML
python3 -m scripts.export_report
```

Dependencies: `numpy`, `pandas`, `matplotlib`. See `testing/docs/SETUP_AND_BENCHMARK_GUIDE.md` for full environment setup.
