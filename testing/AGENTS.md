# AGENTS.md

## Project goal
Build and benchmark 3 Vietnamese audio phoneme/alignment pipelines under a 4GB Docker memory constraint.

## Scenarios
1. Guided read-aloud assessment
   - reference transcript is available
   - compare MFA and NeMo Forced Aligner

2. Unguided pronunciation assessment
   - no reference transcript
   - compare WhisperX or ASR+alignment pipeline

## Required outputs
- runnable code for each pipeline
- benchmark scripts
- quantified results:
  - model load time
  - idle RAM
  - peak RAM
  - total inference time
  - time per word
  - concurrency results at 1, 3, 5 users
- report with graphs and code snippets

## Rules for all edits
- Prefer small, reviewable commits
- Do not change dataset paths without updating manifest files
- Do not invent metrics; only use metrics defined in docs/EVAL_PROTOCOL.md
- When adding a new script, also add a short usage comment at the top
- Save raw benchmark outputs to outputs/tables/
- Save figures to outputs/figures/

## Before modifying code
Read:
1. PLANS.md
2. docs/TASK_CONTEXT.md
3. docs/EVAL_PROTOCOL.md

## Before finishing a task
- run the relevant benchmark/test command
- summarize what changed
- list any assumptions or unresolved issues