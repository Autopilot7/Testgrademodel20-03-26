# Hướng dẫn sử dụng: Phoneme Splitting & Comparison Tools

Ba script mới nằm trong `scripts/` phục vụ cho việc tách audio theo âm vị, kiểm tra chất lượng, và so sánh phát âm.

**Yêu cầu trước khi chạy:**
- MFA đã chạy xong — các file `.TextGrid` phải tồn tại trong `outputs/mfa/{audio_id}/aligned/`
- Môi trường conda `mfa-aligner` đã được cài đặt (xem `docs/SETUP_AND_BENCHMARK_GUIDE.md`)

---

## Tính năng 1 — Tách audio theo timestamp MFA

**Script:** `scripts/split_phonemes.py`

Đọc các file TextGrid từ MFA và cắt file WAV gốc thành từng clip âm vị riêng biệt.

### Chạy nhanh

```bash
conda activate mfa-aligner
cd "C:\Users\Surface1\Documents\Testgrademodel20-03-26\testing"
python scripts/split_phonemes.py
```

Không cần thêm tham số — script tự dùng manifest mặc định và thư mục output mặc định.

### Tham số tuỳ chọn

| Tham số | Mặc định | Mô tả |
|---------|----------|-------|
| `--manifest` | `data/common_voice_vi/selected/benchmark_manifest.csv` | Manifest CSV đầu vào |
| `--mfa-output-dir` | `outputs/mfa` | Thư mục chứa TextGrid của MFA |
| `--output-dir` | `outputs/phoneme_splits` | Thư mục lưu clip âm vị |
| `--min-duration-ms` | `20` | Bỏ qua clip ngắn hơn N ms |

Ví dụ chạy với tham số tuỳ chỉnh:
```bash
python scripts/split_phonemes.py \
  --manifest data/common_voice_vi/selected/benchmark_manifest.csv \
  --output-dir outputs/phoneme_splits \
  --min-duration-ms 30
```

### Output

```
outputs/phoneme_splits/
├── all_splits_manifest.csv              ← manifest tổng hợp toàn bộ 18 file
├── common_voice_vi_25132172/
│   ├── splits_manifest.csv              ← manifest riêng cho audio này
│   ├── 0001_t_U0331_80_140.wav          ← âm "t̪" từ 80ms đến 140ms
│   ├── 0002_a_U02D0_U02E8_U02E9_U02C0_140_170.wav   ← âm "aː˨˩ˀ"
│   ├── 0003_j_170_200.wav
│   ├── 0004_s_710_790.wav
│   ├── 0005_a_U02D0_U02E7_790_1030.wav
│   └── 0006_w_1030_1240.wav
└── common_voice_vi_24122210/
    └── ...
```

`splits_manifest.csv` có các cột: `audio_id`, `phoneme`, `index`, `xmin`, `xmax`, `duration_ms`, `wav_path`, `skipped`, `skip_reason`

**Lưu ý:**
- Khoảng lặng (silence) trong TextGrid được bỏ qua tự động
- Tên file dùng ký hiệu Unicode hex cho ký tự IPA (ví dụ `_U02D0` = `ː`) để tránh lỗi filesystem

---

## Tính năng 2 — Kiểm tra chất lượng clip âm vị

**Script:** `scripts/verify_splits.py`

Tạo một file HTML tự chứa (standalone) — mở bằng trình duyệt, nghe từng clip và đánh dấu chất lượng.

**Chạy Tính năng 1 trước khi dùng Tính năng 2.**

### Chạy nhanh

```bash
python scripts/verify_splits.py
```

Mở file HTML được tạo ra trong trình duyệt (Chrome/Edge/Firefox):

```
outputs/phoneme_splits/review_20260329_123456.html
```

### Tham số tuỳ chọn

| Tham số | Mặc định | Mô tả |
|---------|----------|-------|
| `--splits-dir` | `outputs/phoneme_splits` | Thư mục chứa kết quả split |
| `--manifest` | `outputs/phoneme_splits/all_splits_manifest.csv` | Manifest tổng hợp |
| `--benchmark-manifest` | `data/.../benchmark_manifest.csv` | Để lấy transcript gốc hiển thị |
| `--output` | `splits_dir/review_<timestamp>.html` | Tên file HTML output |

### Giao diện HTML

Mỗi audio được hiển thị thành một bảng. Mỗi hàng là một âm vị:

| Cột | Nội dung |
|-----|---------|
| # | Số thứ tự clip |
| Phoneme | Ký hiệu IPA (hiển thị font lớn) |
| Start–End | Thời gian trong file gốc (ms) |
| Duration | Độ dài clip (ms) |
| Audio | Nút play trực tiếp |
| Verdict | Dropdown: `OK / Cropped / Noisy / Silent / Wrong` |
| Notes | Ô ghi chú tự do |

**Kiểm tra các vấn đề sau:**
- **Cropped** — clip bị cắt mất đầu hoặc cuối âm
- **Noisy** — có nhiễu ảnh hưởng đến so sánh pitch graph
- **Wrong** — sai âm vị so với nhãn IPA hiển thị

Sau khi nghe xong, bấm **Export Verdicts as JSON** để lưu kết quả đánh giá.

---

## Tính năng 3 — So sánh phát âm

**Script:** `scripts/compare_phonemes.py`

So sánh hai chuỗi âm vị IPA và tính điểm chính xác per phoneme.

### Chạy nhanh

```bash
python scripts/compare_phonemes.py \
  --reference "t̪ aː˨˩ˀ j s aː˧ w" \
  --hypothesis "k aː˨˩ˀ j s aː˧ w"
```

### Tham số

| Tham số | Mô tả |
|---------|-------|
| `--reference` | Chuỗi âm vị chuẩn (từ MFA của bản ghi gốc), cách nhau bằng dấu cách |
| `--hypothesis` | Chuỗi âm vị của người dùng (từ MFA của bản ghi âm người dùng) |
| `--ignore-tones` | Bỏ qua dấu thanh điệu khi so sánh (so sánh lỏng hơn) |
| `--json-only` | Chỉ in JSON ra stdout, không in bảng căn chỉnh |

### Lấy chuỗi âm vị từ TextGrid

Mở file TextGrid trong `outputs/mfa/{audio_id}/aligned/{audio_id}.TextGrid`, đọc tier `"phones"`:

```
intervals [2]:  xmin=0.08  xmax=0.14  text="t̪"
intervals [3]:  xmin=0.14  xmax=0.17  text="aː˨˩ˀ"
intervals [4]:  xmin=0.17  xmax=0.20  text="j"
```

→ Chuỗi input: `"t̪ aː˨˩ˀ j"` (bỏ các interval có `text = ""`)

### Output

**stderr** — Bảng căn chỉnh dễ đọc:
```
REF: t̪          | aː˨˩ˀ     | j         | s         | aː˧       | w
HYP: k           | aː˨˩ˀ     | j         | s         | aː˧       | w
     SUBST        | OK         | OK         | OK         | OK         | OK

Accuracy: 83.33%  (correct=5 subst=1 ins=0 del=0)
```

**stdout** — JSON (dùng để tích hợp với pipeline khác):
```json
{
  "reference": ["t̪", "aː˨˩ˀ", "j", "s", "aː˧", "w"],
  "hypothesis": ["k", "aː˨˩ˀ", "j", "s", "aː˧", "w"],
  "alignment": [
    {"ref": "t̪",     "hyp": "k",      "verdict": "substitution", "score": 0.0},
    {"ref": "aː˨˩ˀ", "hyp": "aː˨˩ˀ", "verdict": "correct",      "score": 1.0},
    {"ref": "j",      "hyp": "j",      "verdict": "correct",      "score": 1.0},
    {"ref": "s",      "hyp": "s",      "verdict": "correct",      "score": 1.0},
    {"ref": "aː˧",   "hyp": "aː˧",   "verdict": "correct",      "score": 1.0},
    {"ref": "w",      "hyp": "w",      "verdict": "correct",      "score": 1.0}
  ],
  "correct": 5,
  "substitutions": 1,
  "insertions": 0,
  "deletions": 0,
  "total_ref": 6,
  "total_hyp": 6,
  "accuracy_pct": 83.33
}
```

**Các loại lỗi:**

| Verdict | Ý nghĩa | Ví dụ |
|---------|---------|-------|
| `correct` | Đúng âm | `t̪` → `t̪` |
| `substitution` | Sai âm | `t̪` → `k` |
| `deletion` | Bỏ sót âm | `t̪` → _(không có)_ |
| `insertion` | Thêm âm thừa | _(không có)_ → `t̪` |

**Ví dụ với `--ignore-tones`:**
```bash
python scripts/compare_phonemes.py \
  --reference "aː˨˩ˀ" \
  --hypothesis "aː˧"
# Không ignore: substitution (khác thanh điệu)
# Với --ignore-tones: correct (cùng nguyên âm aː)
```

---

## Thứ tự chạy đầy đủ

```bash
# 1. Tách audio
conda activate mfa-aligner
python scripts/split_phonemes.py

# 2. Kiểm tra chất lượng (dùng Python bất kỳ)
python scripts/verify_splits.py
# → mở file HTML trong browser

# 3. So sánh phát âm (dùng Python bất kỳ)
python scripts/compare_phonemes.py \
  --reference "..." \
  --hypothesis "..."
```

Tính năng 3 độc lập, không cần chạy 1 và 2 trước.
