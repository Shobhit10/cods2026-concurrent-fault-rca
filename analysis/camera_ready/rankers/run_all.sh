#!/usr/bin/env bash
# Ranker comparison (camera-ready Table "rankers"): BARO robust scorer, N-Sigma, PageRank, CIRCA, RCD, random.
# Every step caches per case and is resume-safe; re-running only recomputes missing cache entries.
#
#   BARO_PY     Python with requirements.txt (default: python3)
#   RCAEVAL_PY  Python 3.10 with RCAEval 1.6.0 installed (CIRCA)                 (default: $BARO_PY)
#   RCD_PY      RCAEval's Python 3.8 RCD environment (patched causal-learn)    (default: $RCAEVAL_PY)
#   WORKERS     parallel worker processes (default: 4)
# Outputs go to data/results/camera_ready/rankers/ (override with CODS_RANKERS_OUT).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BARO_PY="${BARO_PY:-python3}"
RCAEVAL_PY="${RCAEVAL_PY:-$BARO_PY}"
RCD_PY="${RCD_PY:-$RCAEVAL_PY}"
export WORKERS="${WORKERS:-4}" PYTHONDONTWRITEBYTECODE=1
cd "$HERE"
L="$("$BARO_PY" -c 'import common; print(common.OUT)')"
mkdir -p "$L"

"$BARO_PY" step1_precompute_baro.py concurrent          > "$L/step1_concurrent.log" 2>&1
CP_REUSE=1 "$BARO_PY" step1_precompute_baro.py single   > "$L/step1_single.log" 2>&1
"$RCAEVAL_PY" step2_causal.py circa concurrent          > "$L/step2_circa_concurrent.log" 2>&1
"$RCAEVAL_PY" step2_causal.py circa_rcaeval concurrent  > "$L/step2_circa_rcaeval_concurrent.log" 2>&1
"$RCD_PY" step2_causal.py rcd concurrent                > "$L/step2_rcd_concurrent.log" 2>&1
# Single-fault reference: stratified subset (reps 1 and 2 of every service x fault combination = 80 cases).
SUBSET_REPS=1,2 "$RCAEVAL_PY" step2_causal.py circa single                > "$L/step2_circa_single.log" 2>&1
SUBSET_REPS=1,2 RCD_SINGLE_SEEDS=0 "$RCD_PY" step2_causal.py rcd single   > "$L/step2_rcd_single.log" 2>&1
"$BARO_PY" step3_evaluate.py concurrent                 > "$L/step3_concurrent.log" 2>&1
"$BARO_PY" step3_evaluate.py single                     > "$L/step3_single.log" 2>&1
"$BARO_PY" make_tables.py
echo "done: $L"