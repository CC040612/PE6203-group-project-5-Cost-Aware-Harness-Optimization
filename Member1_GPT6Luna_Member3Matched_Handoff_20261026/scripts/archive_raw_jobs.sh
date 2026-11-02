#!/usr/bin/env bash
set -euo pipefail
JOBS="/home/member2/experiments/member1/jobs"
OUT="/mnt/d/夏嫣然/6203/group project/member1/handoff/Member1_GPT6Luna_Member3Matched_Handoff_20261026/raw/raw_jobs.tar.gz"
cd "$JOBS"
tar -czf "$OUT" \
  gpt6luna-member3-matched-baseline-formal-20261025T113533Z \
  gpt6luna-member3-matched-baseline-formal-rerun-20261025T115523Z \
  gpt6luna-member3-matched-baseline-formal-continue-20261025T122500Z \
  gpt6luna-member3-matched-baseline-formal-resume-20261025T155552Z \
  gpt6luna-member3-matched-baseline-formal-resume-20261025T164228Z \
  gpt6luna-member3-matched-baseline-resilient-20261025T164947Z-task-*
printf 'Created %s\n' "$OUT"
