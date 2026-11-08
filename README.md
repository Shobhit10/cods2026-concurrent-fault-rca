# Replication package for the CODS 2026 paper on concurrent microservice faults

This package accompanies "Root-Cause Analysis Under Concurrent Microservice Faults: A Measurement Study and a Ranking
Bound" by Shobhit Gupta and Suchi Kumari (Shiv Nadar Institution of Eminence), ACM IKDD International Conference on
Data Science (CODS 2026). It holds the fault-injection scripts, the raw Prometheus exports, the ground-truth labels,
the analysis and cross-validation scripts, and the stored per-fold and per-case results from which every table and
figure of the paper is regenerated. How to cite it is in `CITATION.cff`.

## Contents

```
README.md, LICENSE (MIT, code), DATA_LICENSE (CC BY 4.0, data), CITATION.cff, THIRD_PARTY_NOTICES.md
requirements.txt, requirements-causal.txt   Python packages (pinned); the second only to recompute causal rankers
data/
  concurrent_clean/          the 30 core concurrent cases: exports, ground truth, case report, sha256 manifest
  larger_set/                the 138 cases of the larger set, same files
  merged_format/             both sets in the merged format (see "Two metric formats")
  netdelay/                  the network-delay cases: 60 exports, case list, run record, ground truth, fault check
  results/                   stored outputs behind every table and figure (clean/ as exported, merged/ merged format,
                             learned_rankers/, netdelay/)
  reference_results/         seven reference files (see "Single-fault cases and reference files")
analysis/
  original/                  the BARO-based analysis scripts (RQ1 ranking, grouped deviation clustering)
  camera_ready/              the paper's pipeline: folds_stats/ (per-case records, cross-validation, statistics),
                             clean/, rankers/ (Table 2), scale_network/ (Figure 6), netdelay/, precision/
injection/
  clean_collection/core/     driver, fault check, export, resource limits, case list and fault check of the 30 cases
  clean_collection/larger_set/   case list and fault check of the larger set
  netdelay/                  driver, tc netem script, fault check, export and analysis of the network-delay cases
  *.yaml                     Istio scrape configuration and the Sock Shop load generator
figures/src/                 TikZ sources of the figures and where each plotted number comes from
```

## Setup

Python 3.10 to 3.12 (the paper's numbers were produced with Python 3.12.10) and `git` on the path, because pip
installs BARO from its source repository at a fixed commit.

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements-causal.txt` is needed only to recompute the ranked lists of CIRCA, RCD and the learned rankers; their
stored lists are in `data/results/`, so the Table 2 values are recomputed without it. RCD runs in RCAEval's own Python 3.8 RCD
environment; the learned rankers also need CPU torch and scikit-network 0.33.5
(`analysis/camera_ready/rankers/learned/requirements_causal_venv_freeze.txt` is the full freeze of those runs).

Keep the files in `analysis/original/` byte for byte: `analysis/camera_ready/folds_stats/common.py` checks the md5 of
three of them before it imports them, and `.gitattributes` stops git from changing line endings.

## Reproducing the paper

Run every command from the repository root. The scripts take their inputs and outputs from environment variables;
choose the set and format first (bash shown; in PowerShell write `$env:NAME = "$PWD\..."`). Other operating systems or
Python versions can change line endings and the last floating-point digit.

| Set and format | `DIR` | `CODS_OUT` (stored per-case records) | `CODS_CR_RESULTS` |
|---|---|---|---|
| core, as exported | `data/concurrent_clean` | `data/results/clean/folds_stats` | `data/results/clean` |
| core, merged | `data/merged_format/core` | `data/results/merged/core/folds_stats` | `data/results/merged/core` |
| larger set, as exported | `data/larger_set` | `data/results/clean/larger_set/folds_stats` | not used |
| larger set, merged | `data/merged_format/larger_set` | `data/results/merged/larger_set/folds_stats` | not used |

```
DIR=data/concurrent_clean          # example: core, as exported
export CODS_CONCURRENT_DIR=$PWD/$DIR/concurrent CODS_GROUND_TRUTH=$PWD/$DIR/ground_truth_log.csv
export CODS_OUT=$PWD/data/results/clean/folds_stats CODS_CR_RESULTS=$PWD/data/results/clean
```

With `CODS_OUT` at the stored folder, `case_numbers.py` reads the stored records. To recompute the records instead,
point `CODS_OUT` at an empty folder and run `python analysis/camera_ready/folds_stats/precompute.py --only concurrent
--workers 4` first (one to two minutes per set; the records come out identical to the stored ones).

### Where each number comes from

Commands marked * need the 200 single-fault cases of BARO (see below); their stored outputs are listed so the values
can be checked without them. The ranking bound is Proposition 3.1 of the paper; the scripts print its check as
"Proposition 2.1 violations" and name its files `*prop21*`.

| Paper item | Set | Command | Output | Paper value |
|---|---|---|---|---|
| Table 1, core columns | core, as exported | `python analysis/camera_ready/clean/case_numbers.py` | printed; stored `data/results/clean/folds_stats/raw/corrected_table1_nsigma.csv` | AC@2 0.383 overall, 0.300 (Online Boutique) and 0.467 (Sock Shop); Both@2 0.100 |
| Table 1, larger set | larger set, as exported | `case_numbers.py` | printed | AC@2 0.366, Both@2 5 of 138 (0.036) |
| Table 1, per case | core, as exported | `CODS_OUT_DIR=$PWD/rerun/original_scripts python analysis/original/run_rq1.py`, then `run_second_ranker.py` and `run_faulttype_analysis.py` | `rerun/original_scripts/*.csv`, equal to `data/results/clean/original_scripts/` | per-case values behind Table 1 |
| Figure 5 | core, as exported | `case_numbers.py` | printed | Both@2 0.100, Both@3 0.467, Both@5 0.767, Any@5 0.967 |
| Figure 9 | core, as exported | `case_numbers.py` (last block) | printed; field `ranked` of `data/results/clean/folds_stats/raw/cases/conc__boutique_cpu-mem_pair3_rep5.json` | adservice at ranks 1 to 3, productcatalogservice at 6, currencyservice at 14 |
| RQ1 results, merged series | core and larger set, merged | `case_numbers.py` | printed | AC@2 0.717; Both@2 14 of 30 and 60 of 138 |
| Separation and the ranking bound | core and larger set, merged | `case_numbers.py` | printed; `data/results/merged/core/folds_stats/raw/corrected_prop21_*.csv` | 2 of 30 separated, 4 of 138 in the larger set; zero violations of Proposition 3.1 |
| Precision of the separation rate | none | `python analysis/camera_ready/precision/precision.py` | printed | 4 of 138, exact 95% interval 0.8 to 7.3%; 2 of 30, 0.008 to 0.221; at least one separated case in 30 with probability 0.887 at a true rate of 7% |
| Table 2, first four columns | core, as exported | rankers, below | `rerun/rankers/tables_rankers.md`, `summary_concurrent.json` | AC@2 0.383, 0.200, 0.367, 0.397 (Robust, N-Sigma, CIRCA, RCD) |
| Table 2, Sep. column | core, merged | rankers, below | stage table of `tables_rankers.md` (input `full`) | 0.067, 0.033, 0.000, 0.007 |
| Table 2, CausalRCA row | both | learned rankers, below | `rerun/learned/<fmt>/summary_concurrent.json`; stored `data/results/learned_rankers/LEARNED_TABLE_PAPER_CONVENTION.csv` | AC@2 0.250, Both@2 0.000, Both@5 0.000, Any@5 0.500, Sep. 0.033 |
| Figure 6 | core, as exported | scale model, below | `rerun/scale_network/scale_plot_data.csv`, `scale_model_summary.json` | Both@5 about 0.38 at 12 services, about 0.12 at 25, almost zero by 100 |
| Network delay | none | `python analysis/camera_ready/netdelay/reproduce_netdelay.py rerun/netdelay` | `rerun/netdelay/RESULTS_NETDELAY_numbers.json` (equals `data/results/netdelay/`) | 55 of 60 cases used; Both@2 10 of 55, Both@5 41 of 55; 7 of 53 with caller-observed latency; 2 of 55 separated (merged) |
| Table 3 * | core, merged | statistics, below | `raw/cv_lopo_folds.csv`, row `lopo` of `raw/cv_summary.csv`, first table of `raw/tables_generated.md` | pooled separation 0.067 (2/30), grouped AC@1 0.350, single kept 0.910 (182/200), hit rate 0.740 (148/200) |
| Table 4 * | both | statistics, below | `table_folds_stats.tex`, `raw/stats_ci.csv`, `raw/stats_extra.csv` | first rows from the run as exported, the three LOPO rows from the merged run |
| Figure 4 * | core, as exported | statistics, below | `data/results/clean/folds_stats/raw/stats_ci.csv` | single-fault AC@1 0.70 and 0.85 against concurrent AC@2 0.300 and 0.467 |
| Figure 7 * | core, merged | statistics, below | `raw/verification.csv` (first design), `raw/cv_summary.csv` | 0.0 against 0.910 single-fault cases kept |

**Rankers (Table 2).** Re-evaluates every ranker and the stage from the stored change points and ranked lists. Set
the core variables as exported, then run:

```
mkdir -p rerun/rankers && cp data/results/clean/rankers/* rerun/rankers/
export CODS_RANKERS_OUT=$PWD/rerun/rankers
python analysis/camera_ready/rankers/step3_evaluate.py concurrent
python analysis/camera_ready/rankers/make_tables.py
```

For the Sep. column, set the merged core variables and repeat with `data/results/merged/core/rankers` copied to
`rerun/rankers_merged`. RCD values are means over 10 seeds. The stored `tables_rankers.md` also has a single-fault
section, which needs the single-fault cases; without them the rerun writes the same file without that section.
`make_tables.py` prints one format per run and its caption text still says 28 cases (typed for an earlier data set);
the values are those of the 30 cases, and the paper's Table 2 combines the rows listed above. To recompute the lists, run `step1_precompute_baro.py concurrent`, then `step2_causal.py circa concurrent` and
`step2_causal.py rcd concurrent` in the RCAEval environments (`run_all.sh` runs every step).

**Learned rankers (Table 2, CausalRCA).** CausalRCA and RUN (RCAEval 1.6.0, default parameters, 5 seeds) ran on the
same change point, window and candidate metrics as the other rankers. RUN needs 214 samples, so it ran on a 1-s
interpolated window, and it learned no edge in most runs; the paper reports CausalRCA only. From the stored lists:

```
for fmt in exported merged; do
  mkdir -p rerun/learned/$fmt
  cp data/results/learned_rankers/$fmt/causal_*.json data/results/learned_rankers/$fmt/precompute_concurrent.json rerun/learned/$fmt/
done
export CODS_CR_RESULTS=$PWD/rerun/learned
CODS_CONCURRENT_DIR=$PWD/data/concurrent_clean/concurrent CODS_GROUND_TRUTH=$PWD/data/concurrent_clean/ground_truth_log.csv \
  CODS_RANKERS_OUT=$PWD/rerun/learned/exported python analysis/camera_ready/rankers/step3_evaluate.py concurrent
CODS_CONCURRENT_DIR=$PWD/data/merged_format/core/concurrent CODS_GROUND_TRUTH=$PWD/data/merged_format/core/ground_truth_log.csv \
  CODS_RANKERS_OUT=$PWD/rerun/learned/merged python analysis/camera_ready/rankers/step3_evaluate.py concurrent
```

The first four values of the row come from `exported`, Sep. from `merged`. To recompute the lists, run
`step2_causal.py causalrca concurrent` in the RCAEval environment with `LEARNED_SEEDS=0,1,2,3,4`, once per format.

**Scale model (Figure 6).** Core variables as exported, then:

```
export CODS_PUBLISHED_RESULTS=$PWD/data/results/clean/original_scripts CODS_SCALE_OUT=$PWD/rerun/scale_network
for s in 01_extract_cods_scores 02_quiet_pool 03_scale_model 04_sim_check 05_report_assets; do
  python analysis/camera_ready/scale_network/$s.py
done
```

**Statistics (Tables 3 and 4, Figures 4 and 7).** These need the single-fault cases. Run once with the merged core
variables (Table 3, the LOPO rows of Table 4, Figure 7) and once with the core variables as exported (the other rows
of Table 4, Figure 4), each with its own scratch `CODS_OUT`:

```
export BARO_DATA_DIR=$PWD/external/baro_data
export CODS_PUBLISHED_RESULTS=$PWD/data/reference_results
python analysis/camera_ready/folds_stats/precompute.py --workers 4
for s in verify grouped_cv stats_ci stats_extra make_tables; do python analysis/camera_ready/clean/run_patched.py $s; done
CODS_ORIG_OUT=$PWD/data/results/clean/original_scripts python analysis/camera_ready/clean/corrected_numbers.py
```

`run_patched.py` runs each statistics script unchanged on disk with a listed set of in-memory substitutions that
replace typed case counts by the counts of the run; it stops if a substitution does not match. `verify.py` also
compares with the reference files, so those reference rows read `MISMATCH` by design. On the merged
format, set `CODS_ORIG_OUT=$PWD/data/results/merged/core/original_scripts` for the last line.

### Single-fault cases and reference files

The single-fault baseline (AC@1 0.70 for Online Boutique, 0.85 for Sock Shop) and every number that uses single-fault
cases come from the 200 single-fault cases published with BARO (Pham, Ha and Zhang, FSE 2024). They are third-party
data and are not redistributed; obtain them from the BARO or RCAEval release and place them as
`external/baro_data/fse-ob/<service>_<fault>/<repetition>/simple_data.csv` (Online Boutique) and `fse-ss/...` (Sock
Shop), or set `BARO_DATA_DIR`. Our results on them (counts, ranks, intervals) are in the stored `raw/` folders.

`data/reference_results/` holds seven result files of an earlier collection that the paper does not use;
`verify.py` and `folds_stats/make_tables.py` read them (`CODS_PUBLISHED_RESULTS`) only for reference rows.

## Rerunning the fault injection

The cases were collected on a five-node Kubernetes cluster (4 vCPUs and 16 GiB per node) running Online Boutique
(namespace `boutique`) and Sock Shop (`sock-shop`) with Istio sidecars, the kube-prometheus stack (namespace
`monitoring`), cAdvisor and Node Exporter. `injection/istio-podmonitor.yaml` and `istio-scrape-values.yaml` make
Prometheus scrape Istio; `injection/loadgen-sockshop-deployment.yaml` is the Sock Shop load generator. Set `KUBECONFIG`.
Images without a shell (cartservice, checkoutservice, productcatalogservice) are faulted through one node debug pod
per node, created with `kubectl debug node/<node> --image=nicolaka/netshoot --profile=sysadmin -- sleep infinity`.

**Core set.**

```
cd injection/clean_collection/core
python set_limits.py --aug19      # the container resources of the paper ("aug19" in health/restore_plan.json)
python driver_ext.py run          # runs cases_ext.json; writes state.json, ground_truth_ext.csv, driver.log, fault_logs/
python verify_injections.py       # injection_check.csv: is every fault visible in Prometheus?
python -c "import sys, export_ext as E; E.SERVICES['sock-shop'] = ['catalogue', 'carts', 'payment']; sys.argv = ['x']; E.main()"
python set_limits.py              # sets the resources listed as "now" in health/restore_plan.json
```

The export line writes `data_ext/primary/<case>.csv` with the core set's targets. The "now" entries of
`restore_plan.json` are the resources of the authors' cluster before the run; replace them with your own first.

* **Faults.** CPU: a busy loop for 60 s in the application container, bounded by `timeout` (the driver picks the
  syntax that the container's BusyBox accepts). Memory: 60 MB written to `/dev/shm`, held 60 s, then removed. The
  second fault is scripted 15 s after the first; consecutive cases on one application start at least five minutes
  apart. The output and exit code of every fault command are recorded.
* **Checks.** The floor of a series is its minimum at t-35, t-20, t-5, t+130 and t+150 s from the fault start t. A CPU
  fault is visible if the CPU rate at t+50 s is at least 0.05 cores above the floor, a memory fault if the working set
  at t+40 s is at least 40 MiB above it. A case is used if the driver finished it and both faults are visible.
* **Re-run rule.** A case whose second fault fired more than 25 s after the first (fire times in `driver.log`) is re-run
  once: add a copy of its entry with the id `<case>_rerun` to `cases_ext.json` and run `python driver_ext.py run --only
  <case>_rerun`; the re-run replaces the case. The stored list ends with the one re-run of the paper's collection;
  remove it for a fresh run.
* **Export.** Five series per target (CPU usage rate, memory usage, memory working set, Istio request latency and
  request rate) on a 5-s grid, from 90 s before the first fault to 180 s after the second; Istio is sampled every 30 s
  and held on the grid. The core set exports Sock Shop catalogue, carts and payment (set `SERVICES["sock-shop"]` in
  `export_ext.py` to these three); the larger set exports all five Sock Shop targets.

**Larger set.** It is the 110 cases of `larger_set/cases_ext.json` plus the 30 core cases exported with all five Sock
Shop targets (`python export_ext.py` in `core/`, the default targets), renamed to the larger-set ids that
`data/larger_set/CASE_REPORT.csv` lists; the 2 cases with a fault that is not visible are left out, giving 138. For
the 110 cases, copy `driver_ext.py`, `verify_injections.py` and `export_ext.py` from `core/` into `larger_set/` (they
read `cases_ext.json` from their own folder) and run them there in the same order, with `python export_ext.py`.

**Network delay.** In `injection/netdelay/`, with a fresh working folder:
`mkdir run && cp cases_ext.json run/`, then `python driver_netdelay.py run --workdir run`,
`python verify_netdelay.py --workdir run` and `python export_netdelay.py --workdir run`. The delay is a 300-ms `tc netem`
egress delay on the faulted pod, injected from the node debug pod with `netem.sh`, held 60 s and removed; it is visible
if the latency that callers observe rises by at least 100 ms at t+50 s. Arm D1 pairs a delay on the first service with
a memory fault on the second, arm D2 a CPU fault with a delay. The export adds `<svc>_istio_latency_src`, the latency
callers observe, because the destination-reported latency does not see an egress delay.

## Data format

* `concurrent/<case>.csv`: column `time` (seconds since the window start, 5-s steps) and the series columns
  `<svc>_cpu_usage_seconds`, `<svc>_memory_usage_bytes`, `<svc>_memory_working_set_bytes`, `<svc>_istio_latency`,
  `<svc>_istio_requests`.
* `ground_truth_log.csv`: per case, case id, namespace, service A, fault A, service B, fault B, scripted stagger (s),
  start time (Unix s), plus a line `case,end_time,<Unix s>`.
* `CASE_REPORT.csv`: every case run, with driver status, faults visible, measured stagger and the id it is used as.
  Larger-set ids name both services, CPU-faulted first (`boutique_cpu-mem_adservice_cartservice_rep2` is core case
  `boutique_cpu-mem_pair1_rep2`).
* `DATA_MANIFEST.sha256`: check with `cd data/concurrent_clean && sha256sum -c DATA_MANIFEST.sha256`.
* `data/netdelay/`: `data_ext/primary/<case>.csv` (five series plus `<svc>_istio_latency_src`), `cases_ext.json`,
  `state.json` (driver status per case, including how long each delay was held), `ground_truth_ext.csv` and
  `injection_check.csv`.
* `data/results/`: `folds_stats/raw/cases/conc__<case>.json` are the per-case records (change point, ranked lists, stage
  groups on the full parameter grid); the other files of `raw/` hold the cross-validation folds, intervals and tests.

### Two metric formats

The export holds five series per target; two of them, `<svc>_memory_usage_bytes` and `<svc>_memory_working_set_bytes`,
move together, so a fault can fill two ranks with one service. The merged format is the export without every
`*_memory_usage_bytes` column (`analysis/camera_ready/clean/make_merged_format.py` writes or checks it). RQ1 ranking
uses the series as exported; the separation stage uses the merged format.

## Licences

Code (Python and shell scripts, Kubernetes manifests, figure sources) is under the MIT licence (`LICENSE`). The
authors' measured data and results are under CC BY 4.0 (`DATA_LICENSE`). BARO, RCAEval and the benchmark applications
are third-party software, not included, and are obtained under their own licences;
`analysis/camera_ready/rankers/step2_causal.py` contains a short excerpt adapted from RCAEval (MIT), see
`THIRD_PARTY_NOTICES.md`.
