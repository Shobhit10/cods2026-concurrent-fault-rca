"""
cv_engine.py -- cross-validation over cached per-case outcomes.

Replicates run_crossval_parallel.py exactly:
  * for each held-out fold, every (alpha, eps) in GRID (alpha outer, eps inner) is scored on the
    training folds as combined = (mean concurrent `separated` + mean single-fault `single_group`) / 2;
  * the first strictly-best setting is kept (`if combined > best_score`), as in the original;
  * the chosen setting is applied to the held-out fold.
Per-case outcomes for each grid point were produced by the ORIGINAL cluster_candidates_v2 and the
original scoring rules (precompute.py), so aggregating them is equivalent to re-running the script.
"""
import sys
sys.dont_write_bytecode = True
import os
import random

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def make_folds_orig(items, n_folds, seed):
    """Verbatim copy of run_crossval_parallel.make_folds."""
    rng = random.Random(seed)
    shuffled = items[:]
    rng.shuffle(shuffled)
    folds = [[] for _ in range(n_folds)]
    for i, item in enumerate(shuffled):
        folds[i % n_folds].append(item)
    return folds


def grouped_folds(groups_of_items, n_folds, seed):
    """Groups (lists of ids) are shuffled with random.Random(seed) and dealt round-robin into folds,
    so all members of a group land in the same fold (the grouped analogue of make_folds)."""
    folds_of_groups = make_folds_orig(groups_of_items, n_folds, seed)
    return [[i for g in fg for i in g] for fg in folds_of_groups]


class Outcomes:
    """Fast lookup of per-case outcomes for every grid point."""

    def __init__(self, conc_grid: pd.DataFrame, sf_grid: pd.DataFrame, conc_cases: pd.DataFrame):
        self.sep, self.gac = {}, {}
        self.sg, self.hit = {}, {}
        for (a, e), sub in conc_grid.groupby(["alpha", "eps"]):
            s = sub.set_index("case_id")
            self.sep[(a, e)] = s["separated"].to_dict()
            self.gac[(a, e)] = s["grouped_ac1"].to_dict()
        for (a, e), sub in sf_grid.groupby(["alpha", "eps"]):
            s = sub.set_index("sf_id")
            self.sg[(a, e)] = s["single_group"].to_dict()
            self.hit[(a, e)] = s["hit"].to_dict()
        cc = conc_cases.set_index("case_id")
        self.case = cc.to_dict("index")


def run_cv(O: Outcomes, conc_folds, sf_folds, fold_labels=None):
    nf = len(conc_folds)
    assert nf == len(sf_folds)
    fold_rows, case_rows = [], []
    for i in range(nf):
        c_test = conc_folds[i]
        c_train = [c for j, f in enumerate(conc_folds) if j != i for c in f]
        s_test = sf_folds[i]
        s_train = [c for j, f in enumerate(sf_folds) if j != i for c in f]
        best, ba, be = -1, None, None
        for a, e in C.GRID:
            if len(c_train) == 0 or len(s_train) == 0:
                continue
            sep_tr = sum(O.sep[(a, e)][c] for c in c_train) / len(c_train)
            sg_tr = sum(O.sg[(a, e)][c] for c in s_train) / len(s_train)
            comb = (sep_tr + sg_tr) / 2
            if comb > best:
                best, ba, be = comb, a, e
        n_c, n_s = len(c_test), len(s_test)
        k_sep = sum(O.sep[(ba, be)][c] for c in c_test)
        sum_gac = sum(O.gac[(ba, be)][c] for c in c_test)
        k_sg = sum(O.sg[(ba, be)][c] for c in s_test)
        k_hit = sum(O.hit[(ba, be)][c] for c in s_test)
        k_b2 = sum(O.case[c]["both2"] for c in c_test)
        k_b5 = sum(O.case[c]["both5"] for c in c_test)
        k_bin = sum(O.case[c]["both_in_input"] for c in c_test)
        sep_cases = [c for c in c_test if O.sep[(ba, be)][c]]
        fold_rows.append({
            "fold": i + 1,
            "held_out": fold_labels[i] if fold_labels else "",
            "alpha": ba, "eps": be, "train_combined": best,
            "n_conc_test": n_c, "k_separated": k_sep,
            "separation": k_sep / n_c if n_c else np.nan,
            "grouped_ac1_sum": sum_gac, "grouped_ac1": sum_gac / n_c if n_c else np.nan,
            "n_sf_test": n_s, "k_single_kept": k_sg, "single_kept": k_sg / n_s if n_s else np.nan,
            "k_hit": k_hit, "hit_rate": k_hit / n_s if n_s else np.nan,
            "k_both2": k_b2, "both2": k_b2 / n_c if n_c else np.nan,
            "k_both5": k_b5, "both5": k_b5 / n_c if n_c else np.nan,
            "k_both_in_stage_input": k_bin,
            # Proposition 2.1 with k = |pi| (the stage partitions the FULL ranked list in the code):
            "prop21_holds_input": bool(k_sep <= k_bin),
            # empirical comparisons (not implied by Prop. 2.1 because the stage reads beyond top-2/top-5):
            "sep_le_both2_count": bool(k_sep <= k_b2),
            "sep_subset_both2": bool(all(O.case[c]["both2"] for c in sep_cases)),
            "sep_subset_both5": bool(all(O.case[c]["both5"] for c in sep_cases)),
            "separated_cases": ";".join(sep_cases),
        })
        for c in c_test:
            cc = O.case[c]
            case_rows.append({
                "fold": i + 1, "case_id": c, "pair": cc["pair"], "alpha": ba, "eps": be,
                "separated": O.sep[(ba, be)][c], "grouped_ac1": O.gac[(ba, be)][c],
                "rank_cpu": cc["rank_cpu"], "rank_mem": cc["rank_mem"], "n_ranked": cc["n_ranked"],
                "both2": cc["both2"], "both5": cc["both5"], "both_in_stage_input": cc["both_in_input"],
            })
    return pd.DataFrame(fold_rows), pd.DataFrame(case_rows)


def summarize(design, folds: pd.DataFrame):
    out = {"design": design, "n_folds": len(folds)}
    for m in ["separation", "grouped_ac1", "single_kept", "hit_rate"]:
        out[f"{m}_mean"] = folds[m].mean()
        out[f"{m}_sd"] = folds[m].std()  # pandas sample SD (ddof=1), as in the original script
    out["sep_pooled_k"] = int(folds["k_separated"].sum())
    out["conc_n"] = int(folds["n_conc_test"].sum())
    out["gac_pooled"] = folds["grouped_ac1_sum"].sum() / folds["n_conc_test"].sum()
    out["single_kept_pooled_k"] = int(folds["k_single_kept"].sum())
    out["hit_pooled_k"] = int(folds["k_hit"].sum())
    out["sf_n"] = int(folds["n_sf_test"].sum())
    out["both2_pooled_k"] = int(folds["k_both2"].sum())
    out["both5_pooled_k"] = int(folds["k_both5"].sum())
    out["params"] = ";".join(f"({a},{e})" for a, e in zip(folds["alpha"], folds["eps"]))
    out["all_folds_0.7_0.4"] = bool(((folds["alpha"] == 0.7) & (folds["eps"] == 0.4)).all())
    out["n_folds_sep_zero"] = int((folds["k_separated"] == 0).sum())
    out["prop21_holds_all_folds"] = bool(folds["prop21_holds_input"].all())
    out["sep_le_both2_all_folds"] = bool(folds["sep_le_both2_count"].all())
    out["sep_subset_both5_all_folds"] = bool(folds["sep_subset_both5"].all())
    return out
