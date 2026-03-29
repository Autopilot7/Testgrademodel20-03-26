# Phoneme Splitting & Comparison Tools — Usage Guide

Three scripts in `scripts/` for splitting audio by phoneme, reviewing clip quality, and comparing pronunciation.

**Prerequisites:**
- MFA has been run — `.TextGrid` files must exist under `outputs/mfa/{audio_id}/aligned/`
- The `mfa-aligner` conda environment is installed (see `docs/SETUP_AND_BENCHMARK_GUIDE.md`)

---

## Feature 1 — Split Audio by MFA Timestamps

**Script:** `scripts/split_phonemes.py`

Reads TextGrid files from MFA and slices the source WAV into individual phoneme clips.

### Quick start

```bash
conda activate mfa-aligner
cd "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"
python scripts/split_phonemes.py
```

No extra arguments needed — the script uses the default manifest and output directory.

### Optional arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--manifest` | `data/common_voice_vi/selected/benchmark_manifest.csv` | Input CSV manifest |
| `--mfa-output-dir` | `outputs/mfa` | Root directory containing MFA TextGrid files |
| `--output-dir` | `outputs/phoneme_splits` | Output directory for phoneme clips |
| `--min-duration-ms` | `20` | Skip clips shorter than N ms |

Example with custom arguments:
```bash
python scripts/split_phonemes.py \
  --manifest data/common_voice_vi/selected/benchmark_manifest.csv \
  --output-dir outputs/phoneme_splits \
  --min-duration-ms 30
```

### Output

```
outputs/phoneme_splits/
├── all_splits_manifest.csv              ← merged manifest for all 18 files
├── common_voice_vi_25132172/
│   ├── splits_manifest.csv              ← per-audio manifest
│   ├── 0001_t_U0331_80_140.wav          ← phoneme "t̪" from 80ms to 140ms
│   ├── 0002_a_U02D0_U02E8_U02E9_U02C0_140_170.wav   ← phoneme "aː˨˩ˀ"
│   ├── 0003_j_170_200.wav
│   ├── 0004_s_710_790.wav
│   ├── 0005_a_U02D0_U02E7_790_1030.wav
│   └── 0006_w_1030_1240.wav
└── common_voice_vi_24122210/
    └── ...
```

`splits_manifest.csv` columns: `audio_id`, `phoneme`, `index`, `xmin`, `xmax`, `duration_ms`, `wav_path`, `skipped`, `skip_reason`

**Notes:**
- Silence intervals (empty `text` in TextGrid) are skipped automatically
- Filenames use Unicode hex for IPA characters (e.g. `_U02D0` = `ː`) to avoid filesystem errors

---

## Feature 2 — Review Phoneme Clip Quality

**Script:** `scripts/verify_splits.py`

Generates a self-contained HTML file — open in any browser to listen to each clip and mark its quality.

**Run Feature 1 before Feature 2.**

### Quick start

```bash
python scripts/verify_splits.py
```

Open the generated HTML file in a browser (Chrome / Edge / Firefox):

```
outputs/phoneme_splits/review_20260329_123456.html
```

### Optional arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--splits-dir` | `outputs/phoneme_splits` | Directory produced by `split_phonemes.py` |
| `--manifest` | `outputs/phoneme_splits/all_splits_manifest.csv` | Merged splits manifest |
| `--benchmark-manifest` | `data/.../benchmark_manifest.csv` | Source for reference transcripts |
| `--output` | `splits_dir/review_<timestamp>.html` | Output HTML path |

### HTML interface

Each audio file is shown as a table. Each row is one phoneme:

| Column | Content |
|--------|---------|
| # | Clip index |
| Phoneme | IPA symbol (large font) |
| Start–End | Timestamp within the source file (ms) |
| Duration | Clip length (ms) |
| Audio | Inline play button |
| Verdict | Dropdown: `OK / Cropped / Noisy / Silent / Wrong` |
| Notes | Free-text note field |

**Check for the following issues:**
- **Cropped** — clip is cut too early or too late, missing part of the phoneme
- **Noisy** — background noise that may affect pitch graph comparison
- **Wrong** — phoneme label does not match what is heard

After reviewing, click **Export Verdicts as JSON** to save the results.

---

## Feature 3 — Pronunciation Comparison

**Script:** `scripts/compare_phonemes.py`

Compares two IPA phoneme sequences and computes per-phoneme accuracy scores.

### Quick start

```bash
python scripts/compare_phonemes.py \
  --reference "t̪ aː˨˩ˀ j s aː˧ w" \
  --hypothesis "k aː˨˩ˀ j s aː˧ w"
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--reference` | Reference phoneme sequence (from MFA on the native recording), space-separated |
| `--hypothesis` | User phoneme sequence (from MFA on the user's recording), space-separated |
| `--ignore-tones` | Strip tone diacritics before comparison (lenient mode) |
| `--json-only` | Print JSON to stdout only, suppress the alignment table on stderr |

### Getting the phoneme sequence from a TextGrid

Open `outputs/mfa/{audio_id}/aligned/{audio_id}.TextGrid` and read the `"phones"` tier:

```
intervals [2]:  xmin=0.08  xmax=0.14  text="t̪"
intervals [3]:  xmin=0.14  xmax=0.17  text="aː˨˩ˀ"
intervals [4]:  xmin=0.17  xmax=0.20  text="j"
```

→ Input string: `"t̪ aː˨˩ˀ j"` (skip intervals where `text = ""`)

### Output

**stderr** — Alignment table with component scores:
```
REF: t̪          | aː˨˩ˀ     | j         | s         | aː˧       | w
HYP: k           | aː˨˩ˀ     | j         | s         | aː˧       | w
     SUBST        | OK         | OK         | OK         | OK         | OK

Overall accuracy : 83.33%  (correct=5 subst=1 ins=0 del=0)
Component scores : Consonant 75.0% (3/4)  |  Vowel 100.0% (2/2)  |  Tone 100.0% (2/2)
Weighted final   : 92.5%  (consonant*0.3 + vowel*0.3 + tone*0.4)
```

**stdout** — JSON (for integration with other pipeline tools):
```json
{
  "reference": ["t̪", "aː˨˩ˀ", "j", "s", "aː˧", "w"],
  "hypothesis": ["k", "aː˨˩ˀ", "j", "s", "aː˧", "w"],
  "alignment": [
    {"ref": "t̪",     "hyp": "k",      "verdict": "substitution", "score": 0.0},
    {"ref": "aː˨˩ˀ", "hyp": "aː˨˩ˀ", "verdict": "correct",      "score": 1.0},
    ...
  ],
  "correct": 5,
  "substitutions": 1,
  "insertions": 0,
  "deletions": 0,
  "total_ref": 6,
  "total_hyp": 6,
  "accuracy_pct": 83.33,
  "component_scores": {
    "consonant_pct": 75.0,
    "consonant_correct": 3,
    "consonant_total": 4,
    "vowel_pct": 100.0,
    "vowel_correct": 2,
    "vowel_total": 2,
    "tone_pct": 100.0,
    "tone_correct": 2,
    "tone_total": 2,
    "final_pct": 92.5,
    "weights": {"consonant": 0.3, "vowel": 0.3, "tone": 0.4}
  }
}
```

### Vietnamese Component Score

The script breaks the score into 3 components of a Vietnamese syllable:

| Component | How to identify from MFA symbol | Example |
|-----------|--------------------------------|---------|
| **Consonant** | No tone diacritics, no `ː` | `t̪`, `s`, `k`, `w`, `j` |
| **Vowel** | Contains `ː` or tone diacritics — compared without tone | `aː˨˩ˀ` vs `aː˧` → vowel correct |
| **Tone** | The tone diacritics portion of the vowel symbol | `˨˩ˀ` vs `˧` → tone wrong |

**Formula:**
```
Final = Consonant × 0.3 + Vowel × 0.3 + Tone × 0.4
```
Tone carries the highest weight (0.4) because it is the primary meaning-distinguishing feature in Vietnamese.

**Comparison of the two metrics:**

| Scenario | `accuracy_pct` | `final_pct` |
|----------|---------------|------------|
| Wrong initial consonant, correct tone | 83.33% | 92.5% (penalised less) |
| Correct consonant, wrong tone | 66.67% | 60.0% (penalised more) |

`final_pct` is more appropriate for grading Vietnamese pronunciation because it reflects the actual severity of each error type.

**Error types:**

| Verdict | Meaning | Example |
|---------|---------|---------|
| `correct` | Phoneme matches | `t̪` → `t̪` |
| `substitution` | Wrong phoneme produced | `t̪` → `k` |
| `deletion` | Phoneme missing from hypothesis | `t̪` → _(absent)_ |
| `insertion` | Extra phoneme in hypothesis | _(absent)_ → `t̪` |

**Example with `--ignore-tones`:**
```bash
python scripts/compare_phonemes.py \
  --reference "aː˨˩ˀ" \
  --hypothesis "aː˧"
# Without flag: substitution  (tones differ)
# With --ignore-tones: correct (same vowel base aː)
```

---

## Full run order

```bash
# 1. Split audio (requires mfa-aligner env)
conda activate mfa-aligner
python scripts/split_phonemes.py

# 2. Review clip quality (any Python)
python scripts/verify_splits.py
# → open the generated HTML file in a browser

# 3. Compare pronunciation (any Python)
python scripts/compare_phonemes.py \
  --reference "..." \
  --hypothesis "..."
```

Feature 3 is standalone — Features 1 and 2 do not need to be run first.
