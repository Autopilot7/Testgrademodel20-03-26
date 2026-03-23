# Setup and Benchmark Guide

This document explains how to set up and run the three alignment pipelines in this repository on Windows PowerShell:

1. MFA
2. WhisperX
3. NeMo Forced Aligner

It also includes the benchmark commands used by this project.

## Repository assumptions

- Repository root:
  `C:\Users\Surface1\Documents\Testgrademodel20-03-26`
- Project root for all commands below:
  `C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing`
- Canonical benchmark manifest:
  `testing/data/common_voice_vi/selected/benchmark_manifest.csv`
- All benchmark audio is expected to be:
  WAV, mono, 16kHz

Important:
- `scripts/benchmark_runner.py` benchmarks from a manifest CSV, not from a folder path directly.
- The benchmark CSV schema must not be changed.

## Common benchmark entrypoints

Open PowerShell and move to the project root:

```powershell
cd "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"
```

Single-sample smoke benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline PIPELINE_NAME `
  --manifest outputs/smoke/benchmark_manifest_single.csv `
  --output-csv outputs/tables/raw_benchmark_PIPELINE_single.csv
```

Full prepared Common Voice benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline PIPELINE_NAME `
  --manifest data/common_voice_vi/selected/benchmark_manifest.csv `
  --output-csv outputs/tables/raw_benchmark_PIPELINE.csv
```

Replace `PIPELINE_NAME` with one of:
- `mfa`
- `whisperx`
- `nemo`

## 1. MFA setup

MFA is used as a transcript-based aligner.

### 1.1 Create the environment

```powershell
$env:CONDA_NO_PLUGINS='true'
conda create --solver classic -y -n mfa-aligner -c conda-forge montreal-forced-aligner
conda activate mfa-aligner
```

### 1.2 Set the MFA working directory

```powershell
$root = "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"
$env:MFA_ROOT_DIR = "$root\outputs\mfa_root"
New-Item -ItemType Directory -Path $env:MFA_ROOT_DIR -Force | Out-Null
```

### 1.3 Download Vietnamese MFA models

```powershell
& "C:\Users\Surface1\Anaconda3\envs\mfa-aligner\Scripts\mfa.exe" model download dictionary vietnamese_cv --version v2.0.0
& "C:\Users\Surface1\Anaconda3\envs\mfa-aligner\Scripts\mfa.exe" model download acoustic vietnamese_cv --version v2.0.0
```

### 1.4 Set MFA environment variables

```powershell
$env:MFA_EXECUTABLE = "C:\Users\Surface1\Anaconda3\envs\mfa-aligner\Scripts\mfa.exe"
$env:MFA_DICTIONARY_PATH = "$root\outputs\mfa_root\pretrained_models\dictionary\vietnamese_cv.dict"
$env:MFA_ACOUSTIC_MODEL_PATH = "$root\outputs\mfa_root\pretrained_models\acoustic\vietnamese_cv.zip"
$env:PATH = "C:\Users\Surface1\Anaconda3\envs\mfa-aligner;C:\Users\Surface1\Anaconda3\envs\mfa-aligner\Library\bin;C:\Users\Surface1\Anaconda3\envs\mfa-aligner\Scripts;$env:PATH"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
```

### 1.5 MFA smoke test

```powershell
cd "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"

python -m pipelines.mfa.run_alignment `
  --audio-id common_voice_vi_25132172 `
  --audio data/common_voice_vi/processed/wav/common_voice_vi_25132172.wav `
  --transcript "Tại sao" `
  --output-dir outputs/mfa/common_voice_vi_25132172_smoke
```

Expected result:
- JSON output with `success: true`
- `artifact_path` pointing to a real `.TextGrid`

### 1.6 MFA benchmark commands

One-sample benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline mfa `
  --manifest outputs/smoke/benchmark_manifest_single.csv `
  --output-csv outputs/tables/raw_benchmark_mfa_single.csv
```

Full benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline mfa `
  --manifest data/common_voice_vi/selected/benchmark_manifest.csv `
  --output-csv outputs/tables/raw_benchmark_mfa.csv
```

## 2. WhisperX setup

WhisperX is used as the no-reference baseline.

### 2.1 Create the environment

```powershell
$env:CONDA_NO_PLUGINS='true'
conda create --solver classic -y -n whisperx-aligner python=3.11
conda activate whisperx-aligner
```

### 2.2 Install system FFmpeg

The working setup in this project uses the Chocolatey build of FFmpeg instead of the conda FFmpeg binary.

```powershell
choco install ffmpeg -y
```

### 2.3 Force PowerShell to prefer the system FFmpeg

```powershell
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notlike '*whisperx-aligner\Library\bin*' }) -join ';'
$env:PATH = "C:\ProgramData\chocolatey\bin;$env:PATH"
where.exe ffmpeg
where.exe ffprobe
ffmpeg -version
ffprobe -version
```

Expected result:
- `C:\ProgramData\chocolatey\bin\ffmpeg.exe` appears before any conda FFmpeg path
- `ffmpeg -version` prints version details

### 2.4 Install WhisperX

```powershell
python -m pip install --upgrade pip
python -m pip install whisperx
```

### 2.5 Set the executable path

```powershell
$env:WHISPERX_EXECUTABLE = "C:\Users\Surface1\Anaconda3\envs\whisperx-aligner\Scripts\whisperx.exe"
```

### 2.6 WhisperX smoke test

```powershell
cd "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"

python -m pipelines.whisperx.run_alignment `
  --audio-id common_voice_vi_25132172 `
  --audio data/common_voice_vi/processed/wav/common_voice_vi_25132172.wav `
  --output-dir outputs/whisperx/common_voice_vi_25132172_smoke
```

Expected result:
- JSON output with `success: true`
- `artifact_path` pointing to a real `.json` file
- `command` and `returncode` recorded

Current note:
- The run may still print `torchcodec` warnings on Windows.
- Those warnings are currently non-blocking if WhisperX still returns `success: true`.

### 2.7 WhisperX benchmark commands

One-sample benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline whisperx `
  --manifest outputs/smoke/benchmark_manifest_single.csv `
  --output-csv outputs/tables/raw_benchmark_whisperx_single.csv
```

Full benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline whisperx `
  --manifest data/common_voice_vi/selected/benchmark_manifest.csv `
  --output-csv outputs/tables/raw_benchmark_whisperx.csv
```

## 3. NeMo Forced Aligner setup

NeMo is used as the second transcript-based aligner.

### 3.1 Create the environment

The current machine required disabling conda plugins and forcing the classic solver.

```powershell
$env:CONDA_NO_PLUGINS='true'
conda create --solver classic -y -n nemo-aligner python=3.10
conda activate nemo-aligner
```

### 3.2 Install NeMo ASR dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install "nemo_toolkit[asr]"
```

Verification:

```powershell
python -c "import nemo; import hydra; import omegaconf; print('nemo_ok=', nemo.__file__); print('hydra_ok=', hydra.__file__); print('omegaconf_ok=', omegaconf.__file__)"
```

### 3.3 Download the NeMo repository for the aligner script

```powershell
$root = "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"
$tools = Join-Path $root "tools"
$repo = Join-Path $tools "NeMo"

New-Item -ItemType Directory -Path $tools -Force | Out-Null
git clone https://github.com/NVIDIA/NeMo.git $repo
Get-Item "$repo\tools\nemo_forced_aligner\align.py"
```

### 3.4 Set the aligner script path

```powershell
$env:NEMO_ALIGN_SCRIPT = "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing\tools\NeMo\tools\nemo_forced_aligner\align.py"
```

### 3.5 Choose a model

This repository currently has no local `.nemo` or `.ckpt` model bundled with it.

The simplest path is to use a pretrained model name:

```powershell
$env:NEMO_PRETRAINED_NAME = "nvidia/parakeet-ctc-0.6b-Vietnamese"
```

Alternative:
- If you already have a local Vietnamese NeMo CTC model, use:

```powershell
$env:NEMO_MODEL_PATH = "FULL_PATH_TO_YOUR_MODEL.nemo"
```

Important:
- Set either `NEMO_PRETRAINED_NAME` or `NEMO_MODEL_PATH`
- Do not set both at the same time
- The pretrained Vietnamese model may be large and may take time to download on first use

### 3.6 NeMo smoke test

```powershell
cd "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"

python -m pipelines.nemo.run_alignment `
  --audio-id common_voice_vi_25132172 `
  --audio data/common_voice_vi/processed/wav/common_voice_vi_25132172.wav `
  --transcript "Tại sao" `
  --output-dir outputs/nemo/common_voice_vi_25132172_smoke
```

Expected result:
- JSON output with `success: true`
- `artifact_path` pointing to a NeMo output artifact such as a CTM or output manifest
- `command` and `returncode` recorded

If it fails:
- verify `NEMO_ALIGN_SCRIPT`
- verify exactly one of `NEMO_PRETRAINED_NAME` or `NEMO_MODEL_PATH`
- check whether the selected model is actually compatible with forced alignment

### 3.7 NeMo benchmark commands

One-sample benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline nemo `
  --manifest outputs/smoke/benchmark_manifest_single.csv `
  --output-csv outputs/tables/raw_benchmark_nemo_single.csv
```

Full benchmark:

```powershell
python -m scripts.benchmark_runner `
  --pipeline nemo `
  --manifest data/common_voice_vi/selected/benchmark_manifest.csv `
  --output-csv outputs/tables/raw_benchmark_nemo.csv
```

## Output locations

Per-pipeline smoke outputs:
- `testing/outputs/mfa/`
- `testing/outputs/whisperx/`
- `testing/outputs/nemo/`

Benchmark tables:
- `testing/outputs/tables/`

Prepared dataset and canonical manifest:
- `testing/data/common_voice_vi/selected/benchmark_manifest.csv`

## Recommended execution order

1. MFA smoke test
2. MFA benchmark
3. WhisperX smoke test
4. WhisperX benchmark
5. NeMo smoke test
6. NeMo benchmark

This order matches the project plan:
- make each pipeline runnable first
- verify with smoke tests
- then run benchmarks
