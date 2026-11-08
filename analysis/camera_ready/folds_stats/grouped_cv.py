"""
grouped_cv.py -- C2: cross-validation with folds GROUPED by service pair (post hoc, camera-ready).

Designs (same grid, same selection rule, same per-case scoring as run_crossval_parallel.py):
  orig_reconstructed : the published case-random 5-fold design (seed 42). The original list order came from
                       as_completed() (non-deterministic), so the exact original fold membership cannot be
                       rebuilt; here the order is the ground-truth order (concurrent) / sorted ids (single).
  orig_seed_sweep    : the case-random 5-fold design over seeds 0..999 (shows the published result is not a
                       lucky split).
  lopo               : PRIMARY. Leave-one-pair-out, 6 folds; each service pair held out entirely; alpha/eps tuned
                       only on the other 5 pairs. Single-fault cases are also grouped: each (service, fault-type)
                       scenario (5 repetitions) stays in one fold; scenarios dealt into 6 folds (seed 42).
  lopo_sfcase        : sensitivity, LOPO for concurrent, single-fault cases split case-randomly (seed 42).
  lopo_sfseed_sweep  : sensitivity, LOPO with the single-fault scenario-to-fold assignment over seeds 0..999.
  g5                 : grouped 5-fold, pairs kept together (6 pairs dealt into 5 folds, seed 42),
                       single-fault scenarios kept together (seed 42).
  g5_all15           : all 15 ways of choosing which two pairs share a fold (others alone), single-fault seed 42.

Writes raw/cv_*.csv and raw/cv_summary.csv.
"""
import sys
sys.dont_write_bytecode = True
import itertools
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import cv_engine as E  # noqa: E402
import load_cache as L  # noqa: E402

SEED = 42
N_SWEEP = int(os.environ.get("N_SWEEP", "1000"))


def main():
    _, conc, conc_grid = L.concurrent_tables()
    _, sf, sf_grid = L.single_tables()
    assert len(conc) == 28, len(conc)
    if os.environ.get("ALLOW_PARTIAL") != "1":
        assert len(sf) == 200, len(sf)
    O = E.Outcomes(conc_grid, sf_grid, conc)

    conc_ids = list(conc["case_id"])                      # ground-truth order
    sf_ids = list(sf["sf_id"])                            # sorted ids
    pairs = list(dict.fromkeys(conc["pair"]))             # 6 pairs, GT order
    pair_members = {p: list(conc.loc[conc["pair"] == p, "case_id"]) for p in pairs}
    combos = list(dict.fromkeys(sf["combo"]))             # 40 scenarios
    combo_members = {c: list(sf.loc[sf["combo"] == c, "sf_id"]) for c in combos}

    summaries, sweeps = [], []

    def record(design, cf, sf_f, labels):
        folds, cases = E.run_cv(O, cf, sf_f, labels)
        C.atomic_write_df(os.path.join(C.RAW, f"cv_{design}_folds.csv"), folds)
        C.atomic_write_df(os.path.join(C.RAW, f"cv_{design}_cases.csv"), cases)
        s = E.summarize(design, folds)
        summaries.append(s)
        return folds, s

    # ---- published design, reconstructed ----
    cf = E.make_folds_orig(conc_ids, 5, SEED)
    sff = E.make_folds_orig(sf_ids, 5, SEED)
    labels = [",".join(sorted({O.case[c]["pair"].replace("_cpu-mem_", ":") for c in f})) for f in cf]
    record("orig_reconstructed", cf, sff, labels)

    # ---- published design over many seeds ----
    for seed in range(N_SWEEP):
        cf = E.make_folds_orig(conc_ids, 5, seed)
        sff = E.make_folds_orig(sf_ids, 5, seed)
        folds, _ = E.run_cv(O, cf, sff)
        s = E.summarize("orig_seed_sweep", folds)
        s["seed"] = seed
        sweeps.append(s)

    # ---- LOPO (primary) ----
    cf = [pair_members[p] for p in pairs]
    sff = E.grouped_folds([combo_members[c] for c in combos], 6, SEED)
    lopo_folds, _ = record("lopo", cf, sff, [p.replace("_cpu-mem_", ":") for p in pairs])

    # ---- LOPO, single-fault split by case ----
    record("lopo_sfcase", cf, E.make_folds_orig(sf_ids, 6, SEED), [p.replace("_cpu-mem_", ":") for p in pairs])

    # ---- LOPO, single-fault scenario assignment over many seeds ----
    for seed in range(N_SWEEP):
        sff = E.grouped_folds([combo_members[c] for c in combos], 6, seed)
        folds, _ = E.run_cv(O, cf, sff)
        s = E.summarize("lopo_sfseed_sweep", folds)
        s["seed"] = seed
        sweeps.append(s)

    # ---- grouped 5-fold (seed 42) ----
    pf = E.make_folds_orig(pairs, 5, SEED)
    cf5 = [[c for p in f for c in pair_members[p]] for f in pf]
    sff5 = E.grouped_folds([combo_members[c] for c in combos], 5, SEED)
    record("g5", cf5, sff5, ["+".join(p.replace("_cpu-mem_", ":") for p in f) for f in pf])

    # ---- grouped 5-fold, all 15 pairings ----
    for i, (p, q) in enumerate(itertools.combinations(pairs, 2), 1):
        rest = [x for x in pairs if x not in (p, q)]
        pf = [[p, q]] + [[x] for x in rest]
        cfx = [[c for pp in f for c in pair_members[pp]] for f in pf]
        lab = ["+".join(pp.replace("_cpu-mem_", ":") for pp in f) for f in pf]
        folds, cases = E.run_cv(O, cfx, sff5, lab)
        s = E.summarize(f"g5_all15_{i:02d}", folds)
        s["merged_pairs"] = lab[0]
        summaries.append(s)

    summ = pd.DataFrame(summaries)
    C.atomic_write_df(os.path.join(C.RAW, "cv_summary.csv"), summ)
    sw = pd.DataFrame(sweeps)
    C.atomic_write_df(os.path.join(C.RAW, "cv_seed_sweeps.csv"), sw)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(summ[["design", "separation_mean", "separation_sd", "grouped_ac1_mean", "grouped_ac1_sd",
                "single_kept_mean", "single_kept_sd", "hit_rate_mean", "hit_rate_sd", "sep_pooled_k", "conc_n",
                "single_kept_pooled_k", "hit_pooled_k", "params", "prop21_holds_all_folds",
                "sep_le_both2_all_folds", "sep_subset_both5_all_folds", "n_folds_sep_zero"]].to_string(index=False))
    print()
    print(lopo_folds.to_string(index=False))
    for d in ("orig_seed_sweep", "lopo_sfseed_sweep"):
        s = sw[sw["design"] == d]
        print(f"\n{d}: {len(s)} seeds; all-folds (0.7,0.4) in {int(s['all_folds_0.7_0.4'].sum())}; "
              f"pooled separation k: {s['sep_pooled_k'].value_counts().sort_index().to_dict()}; "
              f"sep fold-mean range [{s['separation_mean'].min():.3f}, {s['separation_mean'].max():.3f}] "
              f"median {s['separation_mean'].median():.3f}; single-kept pooled k: "
              f"{s['single_kept_pooled_k'].value_counts().sort_index().to_dict()}; "
              f"prop21 holds in all folds for {int(s['prop21_holds_all_folds'].sum())} seeds")


if __name__ == "__main__":
    main()
