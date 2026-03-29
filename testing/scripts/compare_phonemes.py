"""Usage: python scripts/compare_phonemes.py --reference "t̪ aː˨˩ˀ j" --hypothesis "k aː˨˩ˀ j"

Compares two phoneme sequences (reference vs. user recording) using Needleman-Wunsch
global alignment and outputs per-phoneme accuracy scores.

Input format: space-separated IPA phoneme symbols.
  e.g. "t̪ aː˨˩ˀ j s aː˧ w"

Output: JSON with per-phoneme verdicts (correct / substitution / insertion / deletion),
overall accuracy percentage, and Vietnamese component scores (consonant / vowel / tone).

Vietnamese Component Score (Scheme 2):
  Each aligned phoneme pair is classified as consonant or vowel.
  Vowel symbols in MFA contain tone diacritics (˧˨˩˥˦ˀ) or long-vowel marker (ː).
  Three sub-scores are computed:
    - consonant_pct  : accuracy of consonant phonemes
    - vowel_pct      : accuracy of vowel identity (ignoring tone)
    - tone_pct       : accuracy of tone (only on vowel positions)
  Final weighted score: 0.3 × consonant + 0.3 × vowel + 0.4 × tone
  (tone is weighted highest because it is the primary distinguishing feature in Vietnamese)

Tone diacritics (Chao tone letters U+02E5-U+02E9 and glottal U+02C0) are included
by default. Use --ignore-tones to strip them before comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata

# Chao tone letters U+02E5–U+02E9 and glottal stop diacritic U+02C0
_TONE_CHARS = set("\u02e5\u02e6\u02e7\u02e8\u02e9\u02c0")

# Long vowel marker ː (U+02D0) — present in all MFA Vietnamese vowel symbols
_LONG_VOWEL = "\u02d0"


def strip_tone_diacritics(phoneme: str) -> str:
    """Remove Chao tone letters and glottal diacritic from an IPA symbol."""
    return "".join(ch for ch in phoneme if ch not in _TONE_CHARS)


def is_vowel(phoneme: str) -> bool:
    """Return True if this MFA phoneme symbol is a vowel (carries tone information).

    In MFA Vietnamese, vowels always contain either:
    - Chao tone letters (˧˨˩˥˦ˀ), or
    - the long-vowel marker ː (even for short vowels in some transcriptions)
    Consonants (t̪, s, k, ɓ, w, j, …) contain neither.
    """
    return any(ch in _TONE_CHARS or ch == _LONG_VOWEL for ch in phoneme)


def extract_tone(phoneme: str) -> str:
    """Extract only the tone diacritics from a vowel symbol.

    e.g. "aː˨˩ˀ" → "˨˩ˀ",  "aː˧" → "˧",  "t̪" → ""
    """
    return "".join(ch for ch in phoneme if ch in _TONE_CHARS)


def extract_vowel_base(phoneme: str) -> str:
    """Strip tone diacritics, keeping vowel letter(s) and ː.

    e.g. "aː˨˩ˀ" → "aː",  "ɔ˧˥" → "ɔ",  "ie˧" → "ie"
    """
    return "".join(ch for ch in phoneme if ch not in _TONE_CHARS)


def compute_component_scores(alignment: list[dict]) -> dict:
    """Compute Vietnamese component scores from an alignment list.

    Classifies each aligned pair as consonant or vowel position, then scores:
      - consonant_pct : % of consonant positions that are correct
      - vowel_pct     : % of vowel positions where vowel base (no tone) is correct
      - tone_pct      : % of vowel positions where tone is correct
      - final_pct     : 0.3 × consonant + 0.3 × vowel + 0.4 × tone

    Insertion/deletion positions count as errors in the appropriate category.
    """
    c_correct = c_total = 0
    v_correct = v_total = 0
    t_correct = t_total = 0

    for entry in alignment:
        ref = entry["ref"]
        hyp = entry["hyp"]

        # Determine the category from whichever side is present
        anchor = ref if ref is not None else hyp
        if anchor is None:
            continue

        if is_vowel(anchor):
            v_total += 1
            t_total += 1
            if ref is not None and hyp is not None:
                if extract_vowel_base(ref) == extract_vowel_base(hyp):
                    v_correct += 1
                if extract_tone(ref) == extract_tone(hyp):
                    t_correct += 1
            # deletion or insertion → both vowel and tone are wrong (0 added)
        else:
            c_total += 1
            if entry["verdict"] == "correct":
                c_correct += 1

    def pct(num: int, den: int) -> float:
        return round(num / den * 100, 2) if den > 0 else None

    c_pct = pct(c_correct, c_total)
    v_pct = pct(v_correct, v_total)
    t_pct = pct(t_correct, t_total)

    # Weighted final score — skip any missing component
    weights = []
    weighted_sum = 0.0
    for score, w in [(c_pct, 0.3), (v_pct, 0.3), (t_pct, 0.4)]:
        if score is not None:
            weighted_sum += score * w
            weights.append(w)
    final_pct = round(weighted_sum / sum(weights), 2) if weights else None

    return {
        "consonant_pct": c_pct,
        "consonant_correct": c_correct,
        "consonant_total": c_total,
        "vowel_pct": v_pct,
        "vowel_correct": v_correct,
        "vowel_total": v_total,
        "tone_pct": t_pct,
        "tone_correct": t_correct,
        "tone_total": t_total,
        "final_pct": final_pct,
        "weights": {"consonant": 0.3, "vowel": 0.3, "tone": 0.4},
    }


def needleman_wunsch(
    seq_a: list[str],
    seq_b: list[str],
    match_score: int = 1,
    mismatch_score: int = -1,
    gap_penalty: int = -1,
) -> list[tuple[str | None, str | None]]:
    """Global pairwise alignment via Needleman-Wunsch.

    Returns a list of (a_elem, b_elem) pairs where None indicates a gap.
    """
    n, m = len(seq_a), len(seq_b)

    # Build scoring matrix
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i * gap_penalty
    for j in range(m + 1):
        dp[0][j] = j * gap_penalty

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                diag = dp[i - 1][j - 1] + match_score
            else:
                diag = dp[i - 1][j - 1] + mismatch_score
            up = dp[i - 1][j] + gap_penalty
            left = dp[i][j - 1] + gap_penalty
            dp[i][j] = max(diag, up, left)

    # Traceback
    pairs: list[tuple[str | None, str | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            if seq_a[i - 1] == seq_b[j - 1]:
                score_diag = dp[i - 1][j - 1] + match_score
            else:
                score_diag = dp[i - 1][j - 1] + mismatch_score
            if dp[i][j] == score_diag:
                pairs.append((seq_a[i - 1], seq_b[j - 1]))
                i -= 1
                j -= 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + gap_penalty:
            pairs.append((seq_a[i - 1], None))
            i -= 1
        else:
            pairs.append((None, seq_b[j - 1]))
            j -= 1

    pairs.reverse()
    return pairs


def score_alignment(
    pairs: list[tuple[str | None, str | None]],
    ref_len: int,
    hyp_len: int,
) -> dict:
    """Compute per-phoneme verdicts and aggregate accuracy from NW alignment pairs."""
    alignment: list[dict] = []
    correct = 0
    substitutions = 0
    insertions = 0
    deletions = 0

    for ref_ph, hyp_ph in pairs:
        if ref_ph is not None and hyp_ph is not None:
            if ref_ph == hyp_ph:
                verdict = "correct"
                score = 1.0
                correct += 1
            else:
                verdict = "substitution"
                score = 0.0
                substitutions += 1
        elif ref_ph is None:
            verdict = "insertion"
            score = 0.0
            insertions += 1
        else:
            verdict = "deletion"
            score = 0.0
            deletions += 1

        alignment.append({
            "ref": ref_ph,
            "hyp": hyp_ph,
            "verdict": verdict,
            "score": score,
        })

    denom = max(ref_len, hyp_len)
    accuracy_pct = round(correct / denom * 100, 2) if denom > 0 else 0.0

    return {
        "alignment": alignment,
        "correct": correct,
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "total_ref": ref_len,
        "total_hyp": hyp_len,
        "accuracy_pct": accuracy_pct,
    }


def format_alignment_table(result: dict) -> str:
    """Render a 3-row text table (REF / HYP / verdict) for human-readable output."""
    alignment = result["alignment"]
    col_width = 10

    ref_cells: list[str] = []
    hyp_cells: list[str] = []
    verdict_cells: list[str] = []

    for entry in alignment:
        ref_str = entry["ref"] if entry["ref"] is not None else "–"
        hyp_str = entry["hyp"] if entry["hyp"] is not None else "–"

        # Visual width: IPA chars with combining marks are narrow, pad generously
        w = max(col_width, len(ref_str) + 2, len(hyp_str) + 2)

        verdict_map = {
            "correct": "OK",
            "substitution": "SUBST",
            "insertion": "INS",
            "deletion": "DEL",
        }
        v_str = verdict_map.get(entry["verdict"], entry["verdict"])

        ref_cells.append(ref_str.ljust(w))
        hyp_cells.append(hyp_str.ljust(w))
        verdict_cells.append(v_str.ljust(w))

    sep = " | "
    lines = [
        "REF: " + sep.join(ref_cells),
        "HYP: " + sep.join(hyp_cells),
        "     " + sep.join(verdict_cells),
        f"\nOverall accuracy : {result['accuracy_pct']}%"
        f"  (correct={result['correct']} subst={result['substitutions']}"
        f" ins={result['insertions']} del={result['deletions']})",
    ]

    cs = result.get("component_scores")
    if cs:
        def fmt(v):
            return f"{v:.1f}%" if v is not None else "n/a"
        lines.append(
            f"Component scores : "
            f"Consonant {fmt(cs['consonant_pct'])} ({cs['consonant_correct']}/{cs['consonant_total']})  |  "
            f"Vowel {fmt(cs['vowel_pct'])} ({cs['vowel_correct']}/{cs['vowel_total']})  |  "
            f"Tone {fmt(cs['tone_pct'])} ({cs['tone_correct']}/{cs['tone_total']})"
        )
        lines.append(
            f"Weighted final   : {fmt(cs['final_pct'])}"
            f"  (consonant*0.3 + vowel*0.3 + tone*0.4)"
        )

    return "\n".join(lines)


def parse_phoneme_sequence(text: str) -> list[str]:
    """Split a space-separated phoneme string into a list. Returns [] for empty input."""
    text = text.strip()
    if not text:
        return []
    return text.split()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two phoneme sequences and compute accuracy scores."
    )
    parser.add_argument(
        "--reference",
        type=str,
        default=None,
        help='Reference phoneme sequence, space-separated. e.g. "t̪ aː˨˩ˀ j s aː˧ w"',
    )
    parser.add_argument(
        "--hypothesis",
        type=str,
        default=None,
        help='Hypothesis (user) phoneme sequence, space-separated.',
    )
    parser.add_argument(
        "--ignore-tones",
        action="store_true",
        help="Strip tone diacritics (Chao tone letters) before comparison.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only print JSON output, suppress the alignment table on stderr.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Get sequences — prompt interactively if not provided
    if args.reference is None:
        print("Enter reference phonemes (space-separated): ", end="", file=sys.stderr, flush=True)
        args.reference = input()
    if args.hypothesis is None:
        print("Enter hypothesis phonemes (space-separated): ", end="", file=sys.stderr, flush=True)
        args.hypothesis = input()

    ref_seq = parse_phoneme_sequence(args.reference)
    hyp_seq = parse_phoneme_sequence(args.hypothesis)

    if not ref_seq:
        print("ERROR: reference sequence is empty.", file=sys.stderr)
        return 1
    if not hyp_seq:
        print("ERROR: hypothesis sequence is empty.", file=sys.stderr)
        return 1

    # Optionally strip tones before alignment
    ref_cmp = [strip_tone_diacritics(p) for p in ref_seq] if args.ignore_tones else ref_seq
    hyp_cmp = [strip_tone_diacritics(p) for p in hyp_seq] if args.ignore_tones else hyp_seq

    pairs = needleman_wunsch(ref_cmp, hyp_cmp)
    result = score_alignment(pairs, len(ref_seq), len(hyp_seq))

    # Restore original symbols in alignment output (before tone stripping)
    if args.ignore_tones:
        ref_iter = iter(ref_seq)
        hyp_iter = iter(hyp_seq)
        for entry in result["alignment"]:
            if entry["ref"] is not None:
                entry["ref"] = next(ref_iter)
            if entry["hyp"] is not None:
                entry["hyp"] = next(hyp_iter)

    result["reference"] = ref_seq
    result["hypothesis"] = hyp_seq
    result["ignore_tones"] = args.ignore_tones
    result["component_scores"] = compute_component_scores(result["alignment"])

    # Reorder for readability
    output = {
        "reference": result["reference"],
        "hypothesis": result["hypothesis"],
        "alignment": result["alignment"],
        "correct": result["correct"],
        "substitutions": result["substitutions"],
        "insertions": result["insertions"],
        "deletions": result["deletions"],
        "total_ref": result["total_ref"],
        "total_hyp": result["total_hyp"],
        "accuracy_pct": result["accuracy_pct"],
        "component_scores": result["component_scores"],
        "ignore_tones": result["ignore_tones"],
    }

    if not args.json_only:
        print(format_alignment_table(result), file=sys.stderr)

    # ensure_ascii=True so JSON output is safe on any Windows console encoding
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
