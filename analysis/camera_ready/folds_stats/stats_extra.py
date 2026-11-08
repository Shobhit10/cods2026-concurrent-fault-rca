"""
stats_extra.py -- C1 additions (post hoc, camera-ready), run after grouped_cv.py and stats_ci.py.

  (a) Any@2 and a conservative EXACT 95% bracket for concurrent AC@2, using AC@2 = (Both@2 + Any@2)/2 per case, so
      Both@2 <= AC@2 <= Any@2 case-wise:  [CP_lo(Both@2), CP_hi(Any@2)] (two one-sided 97.5% bounds, union bound).
  (b) the drop (single AC@1 - concurrent AC@2): conservative exact lower bound CP_lo(single) - CP_hi(Any@2);
      Newcombe hybrid-score (Wilson) interval on cause slots (approximate); cluster-robust t interval
      (pairs / scenarios as clusters, df = #pairs - 1).
  (c) the separated cases at the chosen setting with their true-cause ranks (Prop. 2.1 per case).
  (d) pair leakage of the published case-random folds (reconstructed, seed 42, and over 1000 seeds).

Outputs: raw/stats_extra.csv, raw/separated_cases.csv, raw/fold_leakage.csv, raw/stats_extra.log
"""
import sys
sys.dont_write_bytecode = True
import math
import os

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import cv_engine as E  # noqa: E402
import load_cache as L  # noqa: E402
from stats_ci import B, RNG_SEED, cluster_boot, cp, pct, wilson  # noqa: E402

SYSTEMS = [("boutique", "Online Boutique"), ("sock-shop", "Sock Shop"), ("all", "Both systems")]


def newcombe(k1, n1, k2, n2):
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    return d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def cr_se(values, clusters):
    """Cluster-robust SE of a case-weighted mean (CR1 small-sample factor G/(G-1))."""
    df = pd.DataFrame({"v": values, "g": clusters})
    n, mu = len(df), df["v"].mean()
    g = df.groupby("g")["v"].agg(["sum", "count"])
    G = len(g)
    s = ((g["sum"] - mu * g["count"]) ** 2).sum()
    return math.sqrt(s * G / (G - 1)) / n, G


def main():
    log = []

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        log.append(s)

    _, conc, conc_grid = L.concurrent_tables()
    _, sf, sf_grid = L.single_tables()
    assert len(conc) == 28 and len(sf) == 200
    conc["any2"] = (conc["hits2"] >= 1).astype(int)
    rows = []

    def add(quantity, scope, k, n, est, method, lo, hi, note=""):
        rows.append({"quantity": quantity, "scope": scope, "k": k, "n": n, "estimate": est, "method": method,
                     "lo": lo, "hi": hi, "note": note})

    for ns, name in SYSTEMS:
        c = conc if ns == "all" else conc[conc["namespace"] == ns]
        s = sf if ns == "all" else sf[sf["namespace"] == ns]
        n_c, n_s = len(c), len(s)
        k_any, k_both, hits = int(c["any2"].sum()), int(c["both2"].sum()), int(c["hits2"].sum())
        k_s = int(s["flat_ac1"].sum())
        lo, hi = cp(k_any, n_c)
        add("Any@2 (at least one cause in top 2)", name, k_any, n_c, k_any / n_c, "Clopper-Pearson exact 95%", lo, hi)
        lo, hi = wilson(k_any, n_c)
        add("Any@2 (at least one cause in top 2)", name, k_any, n_c, k_any / n_c, "Wilson 95%", lo, hi)
        b_lo, _ = cp(k_both, n_c)
        _, a_hi = cp(k_any, n_c)
        add("concurrent AC@2", name, hits, 2 * n_c, hits / (2 * n_c),
            "conservative exact 95% bracket [CP_lo(Both@2), CP_hi(Any@2)]", b_lo, a_hi,
            f"Both@2={k_both}/{n_c}, Any@2={k_any}/{n_c}; valid because Both@2 <= AC@2 <= Any@2 per case; "
            "union of two one-sided 97.5% bounds; cases treated as independent")
        s_lo, s_hi = cp(k_s, n_s)
        d = k_s / n_s - hits / (2 * n_c)
        add("drop: single AC@1 minus concurrent AC@2", name, f"{k_s}/{n_s} vs {hits}/{2 * n_c}", "", d,
            "conservative exact lower bound CP_lo(single AC@1) - CP_hi(Any@2) (>=95%)", s_lo - a_hi, np.nan,
            f"CP_lo(single)={s_lo:.3f}, CP_hi(Any@2)={a_hi:.3f}; positive => drop established without the slot "
            "independence assumption")
        lo, hi = newcombe(k_s, n_s, hits, 2 * n_c)
        add("drop: single AC@1 minus concurrent AC@2", name, f"{k_s}/{n_s} vs {hits}/{2 * n_c}", "", d,
            "Newcombe hybrid-score (Wilson) 95% on cause slots (approximate)", lo, hi,
            "treats the 2 cause slots per concurrent case as independent")
        se_c, g_c = cr_se(c["ac2"].to_numpy(float), c["pair"].to_numpy())
        se_s, g_s = cr_se(s["flat_ac1"].to_numpy(float), s["combo"].to_numpy())
        se = math.sqrt(se_c ** 2 + se_s ** 2)
        t = stats.t.ppf(0.975, g_c - 1)
        add("drop: single AC@1 minus concurrent AC@2", name, f"{k_s}/{n_s} vs {hits}/{2 * n_c}", "", d,
            f"cluster-robust t 95% (pairs/scenarios as clusters, df={g_c - 1})", d - t * se, d + t * se,
            f"SE_conc={se_c:.3f} ({g_c} pairs), SE_single={se_s:.3f} ({g_s} scenarios); df = #pairs-1 is conservative")
        add("concurrent AC@2", name, hits, 2 * n_c, hits / (2 * n_c),
            f"cluster-robust t 95% (pairs as clusters, df={g_c - 1})", hits / (2 * n_c) - t * se_c,
            hits / (2 * n_c) + t * se_c, f"SE={se_c:.3f}")

    # clustered bootstrap for the stage's pooled held-out outcomes (alpha=0.7, eps=0.4 is chosen in every fold of
    # every design, so the held-out outcome of each case is its outcome at that setting)
    rng = np.random.default_rng(RNG_SEED + 1)
    g7 = conc_grid[(conc_grid["alpha"] == 0.7) & (conc_grid["eps"] == 0.4)].set_index("case_id")
    s7 = sf_grid[(sf_grid["alpha"] == 0.7) & (sf_grid["eps"] == 0.4)].set_index("sf_id")
    cc = conc.set_index("case_id").join(g7[["separated", "grouped_ac1"]])
    ss = sf.set_index("sf_id").join(s7[["single_group", "hit"]])
    for col, label, df, cl, n in [("separated", "separation (pooled held-out)", cc, "pair", 28),
                                  ("grouped_ac1", "grouped AC@1 (pooled held-out)", cc, "pair", 28),
                                  ("single_group", "single kept (pooled held-out)", ss, "combo", 200),
                                  ("hit", "hit rate (pooled held-out)", ss, "combo", 200)]:
        strata = []
        for s_ns, _ in SYSTEMS[:2]:
            g = df[df["namespace"] == s_ns].groupby(cl)[col].agg(["sum", "count"])
            strata.append((g["sum"].values, g["count"].values))
        lo, hi = pct(cluster_boot(strata, rng))
        add(label, "Both systems", float(df[col].sum()), n, df[col].mean(),
            f"{'pair' if cl == 'pair' else 'scenario'}-clustered bootstrap 95% (percentile, B={B})", lo, hi,
            "clusters resampled within system")

    ex = pd.DataFrame(rows)
    C.atomic_write_df(os.path.join(C.RAW, "stats_extra.csv"), ex)

    # (c) separated cases at the chosen setting (alpha=0.7, eps=0.4, chosen in every fold of every design)
    g = conc_grid[(conc_grid["alpha"] == 0.7) & (conc_grid["eps"] == 0.4)].set_index("case_id")
    pc = conc.set_index("case_id").join(g[["separated", "grouped_ac1"]])
    pc["k_star"] = pc[["rank_cpu", "rank_mem"]].max(axis=1)
    sep = pc[pc["separated"] == 1].reset_index()
    sep_tab = sep[["case_id", "pair", "svc_cpu", "svc_mem", "rank_cpu", "rank_mem", "k_star", "n_ranked",
                   "both_in_input", "both2", "both5", "grouped_ac1"]]
    C.atomic_write_df(os.path.join(C.RAW, "separated_cases.csv"), sep_tab)
    b2 = set(pc.index[pc["both2"] == 1])
    P("Separated cases at (0.7, 0.4):")
    P(sep_tab.to_string(index=False))
    P(f"separated: {len(sep)}/28; in stage input (full ranked list): {int(sep['both_in_input'].sum())}/{len(sep)}; "
      f"Both@5: {int(sep['both5'].sum())}/{len(sep)}; Both@2: {int(sep['both2'].sum())}/{len(sep)}")
    P(f"Both@2 cases: {sorted(b2)}; Both@2 cases NOT separated: {sorted(b2 - set(sep['case_id']))}")
    P(f"cases with both causes in the stage input: {int(pc['both_in_input'].sum())}/28 "
      f"(ranked-list length {int(pc['n_ranked'].min())}-{int(pc['n_ranked'].max())})")

    # (d) pair leakage of case-random folds
    lk = []
    for seed in range(1000):
        folds = E.make_folds_orig(list(conc["case_id"]), 5, seed)
        pair_of = conc.set_index("case_id")["pair"].to_dict()
        leaked = 0
        for i, f in enumerate(folds):
            train_pairs = {pair_of[c] for j, ff in enumerate(folds) if j != i for c in ff}
            leaked += sum(1 for c in f if pair_of[c] in train_pairs)
        lk.append({"seed": seed, "held_out_cases_whose_pair_is_in_training": leaked, "n": 28})
    lk = pd.DataFrame(lk)
    C.atomic_write_df(os.path.join(C.RAW, "fold_leakage.csv"), lk)
    P(f"case-random 5-fold: held-out cases whose pair also appears in training -- seed 42: "
      f"{int(lk.loc[lk.seed == 42, 'held_out_cases_whose_pair_is_in_training'].iloc[0])}/28; over 1000 seeds: "
      f"min {lk.iloc[:, 1].min()}, median {lk.iloc[:, 1].median():.0f}, max {lk.iloc[:, 1].max()} of 28")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    P("")
    P(ex[["quantity", "scope", "k", "n", "estimate", "method", "lo", "hi"]].round(3).to_string(index=False))
    C.atomic_write_text(os.path.join(C.RAW, "stats_extra.log"), "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
