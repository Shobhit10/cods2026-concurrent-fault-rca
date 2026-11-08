"""
stats_ci.py -- C1: honest small-n statistics for the paper's main claims (post hoc, camera-ready).

  (i)   degradation: single-fault AC@1 vs concurrent AC@2 -- exact (Clopper-Pearson) / Wilson CIs,
        case and cluster (pair / scenario) bootstrap CIs, Fisher exact tests, exact cluster-permutation test;
  (ii)  Both@k / Any@5 -- exact CIs and one-sided upper bounds;
  (iii) the bound -- per-case check that every separated case had both causes in the stage's input;
  (iv)  separation rate -- exact CI and one-sided upper bound, compared with Both@2.

Inputs: raw/cases/*.json (precompute.py) and raw/cv_lopo_cases.csv (grouped_cv.py).
Outputs: raw/stats_ci.csv, raw/stats_tests.csv, raw/bound_percase.csv, raw/bound_grid.csv, raw/stats_ci.log
"""
import sys
sys.dont_write_bytecode = True
import itertools
import math
import os

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import load_cache as L  # noqa: E402

B = 20000
RNG_SEED = 20261024
Z = stats.norm.ppf(0.975)


def cp(k, n, conf=0.95):
    a = 1 - conf
    lo = 0.0 if k == 0 else stats.beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


def cp_upper1(k, n, conf=0.95):
    return 1.0 if k == n else stats.beta.ppf(conf, k + 1, n - k)


def wilson(k, n, z=Z):
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def cluster_boot(clusters_by_stratum, rng, b=B):
    """clusters_by_stratum: list of (sums, counts) arrays per stratum. Resamples clusters with replacement
    within each stratum; returns bootstrap distribution of the pooled case-weighted mean."""
    tot_s = np.zeros(b)
    tot_n = np.zeros(b)
    for sums, cnts in clusters_by_stratum:
        sums, cnts = np.asarray(sums, float), np.asarray(cnts, float)
        idx = rng.integers(0, len(sums), size=(b, len(sums)))
        tot_s += sums[idx].sum(1)
        tot_n += cnts[idx].sum(1)
    return tot_s / tot_n


def pct(x):
    return float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))


def main():
    rng = np.random.default_rng(RNG_SEED)
    log = []

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        log.append(s)

    _, conc, conc_grid = L.concurrent_tables()
    _, sf, _ = L.single_tables()
    assert len(conc) == 28 and len(sf) == 200
    systems = [("boutique", "Online Boutique"), ("sock-shop", "Sock Shop")]
    rows, tests = [], []

    def add(quantity, scope, k, n, est, method, lo, hi, note=""):
        rows.append({"quantity": quantity, "scope": scope, "k": k, "n": n, "estimate": est,
                     "method": method, "lo": lo, "hi": hi, "note": note})

    def add_prop(quantity, scope, k, n, note=""):
        lo, hi = cp(k, n)
        add(quantity, scope, k, n, k / n, "Clopper-Pearson exact 95% (two-sided)", lo, hi, note)
        lo, hi = wilson(k, n)
        add(quantity, scope, k, n, k / n, "Wilson 95%", lo, hi, note)
        add(quantity, scope, k, n, k / n, "Clopper-Pearson one-sided 95% upper bound", 0.0, cp_upper1(k, n), note)

    # ---------- (i) single-fault AC@1 ----------
    sf_clusters = {}
    for ns, name in systems + [("all", "Both systems")]:
        sub = sf if ns == "all" else sf[sf["namespace"] == ns]
        k, n = int(sub["flat_ac1"].sum()), len(sub)
        add_prop("single-fault AC@1", name, k, n, "binary per case; 100 cases per system")
        strata = []
        for s_ns, _ in systems:
            if ns not in ("all", s_ns):
                continue
            g = sf[sf["namespace"] == s_ns].groupby("combo")["flat_ac1"].agg(["sum", "count"])
            strata.append((g["sum"].values, g["count"].values))
        sf_clusters[ns] = strata
        bs = cluster_boot(strata, rng)
        lo, hi = pct(bs)
        add("single-fault AC@1", name, k, n, k / n, "scenario-clustered bootstrap 95% (percentile, B=20000)", lo, hi,
            "clusters = (service, fault type) scenarios, 20 per system x 5 reps, resampled within system")

    # ---------- (i) concurrent AC@2 ----------
    conc_clusters = {}
    for ns, name in systems + [("all", "Both systems")]:
        sub = conc if ns == "all" else conc[conc["namespace"] == ns]
        hits, slots, n = int(sub["hits2"].sum()), 2 * len(sub), len(sub)
        est = sub["ac2"].mean()
        lo, hi = cp(hits, slots)
        add("concurrent AC@2", name, hits, slots, est, "Clopper-Pearson 95% on cause slots (approximate)", lo, hi,
            "treats the 2 cause slots per case as independent; ignores within-case and within-pair dependence")
        lo, hi = wilson(hits, slots)
        add("concurrent AC@2", name, hits, slots, est, "Wilson 95% on cause slots (approximate)", lo, hi,
            "same caveat as above")
        vals = sub["ac2"].to_numpy()
        strata_case = []
        for s_ns, _ in systems:
            if ns not in ("all", s_ns):
                continue
            v = conc.loc[conc["namespace"] == s_ns, "ac2"].to_numpy()
            strata_case.append((v, np.ones_like(v)))
        bs = cluster_boot(strata_case, rng)
        lo, hi = pct(bs)
        add("concurrent AC@2", name, hits, slots, est, "case bootstrap 95% (percentile, B=20000)", lo, hi,
            "resamples cases within system; ignores pair clustering")
        strata = []
        for s_ns, _ in systems:
            if ns not in ("all", s_ns):
                continue
            g = conc[conc["namespace"] == s_ns].groupby("pair")["ac2"].agg(["sum", "count"])
            strata.append((g["sum"].values, g["count"].values))
        conc_clusters[ns] = strata
        bs = cluster_boot(strata, rng)
        lo, hi = pct(bs)
        add("concurrent AC@2", name, hits, slots, est, "pair-clustered bootstrap 95% (percentile, B=20000)", lo, hi,
            "clusters = service pairs (3 per system), resampled within system; few clusters -> coarse, may under-cover")
        if ns == "all":
            pm = conc.groupby("pair")["ac2"].mean().to_numpy()
            m, se = pm.mean(), pm.std(ddof=1) / math.sqrt(len(pm))
            t = stats.t.ppf(0.975, len(pm) - 1)
            add("concurrent AC@2", name, hits, slots, m, "t-interval on 6 pair means (df=5), 95%", m - t * se, m + t * se,
                "estimate here is the unweighted mean of pair means")

    # ---------- (i) difference and tests ----------
    for ns, name in systems + [("all", "Both systems")]:
        s_sub = sf if ns == "all" else sf[sf["namespace"] == ns]
        c_sub = conc if ns == "all" else conc[conc["namespace"] == ns]
        diff = s_sub["flat_ac1"].mean() - c_sub["ac2"].mean()
        bs = cluster_boot(sf_clusters[ns], rng) - cluster_boot(conc_clusters[ns], rng)
        lo, hi = pct(bs)
        add("drop: single AC@1 minus concurrent AC@2", name, "", "", diff,
            "cluster bootstrap 95% (scenarios / pairs, within system)", lo, hi,
            f"bootstrap P(diff<=0) = {np.mean(bs <= 0):.5f}")

        # Fisher exact on cause slots (approximate independence)
        a, b_ = int(s_sub["flat_ac1"].sum()), len(s_sub) - int(s_sub["flat_ac1"].sum())
        c, d = int(c_sub["hits2"].sum()), 2 * len(c_sub) - int(c_sub["hits2"].sum())
        orr, p = stats.fisher_exact([[a, b_], [c, d]], alternative="greater")
        tests.append({"test": "Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits)",
                      "scope": name, "table": f"[[{a},{b_}],[{c},{d}]]", "statistic": orr, "p_value": p,
                      "note": "approximate: the 2 slots of a case are not independent"})
        # Conservative case-level Fisher: concurrent success = at least ONE cause in top-2
        c1 = int((c_sub["hits2"] >= 1).sum())
        d1 = len(c_sub) - c1
        orr, p = stats.fisher_exact([[a, b_], [c1, d1]], alternative="greater")
        tests.append({"test": "Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 "
                              "(generous to concurrent)", "scope": name, "table": f"[[{a},{b_}],[{c1},{d1}]]",
                      "statistic": orr, "p_value": p, "note": "one row per case; ignores clustering"})

    # Exact cluster-permutation test (clusters = single-fault scenarios and concurrent pairs, within system)
    per_sys = {}
    for ns, name in systems:
        g_s = sf[sf["namespace"] == ns].groupby("combo")["flat_ac1"].agg(["sum", "count"])
        g_c = conc[conc["namespace"] == ns].groupby("pair")["ac2"].agg(["sum", "count"])
        sums = np.concatenate([g_s["sum"].values, g_c["sum"].values]).astype(float)
        cnts = np.concatenate([g_s["count"].values, g_c["count"].values]).astype(float)
        n_c = len(g_c)
        combs = np.array(list(itertools.combinations(range(len(sums)), n_c)))
        Sc = sums[combs].sum(1)
        Nc = cnts[combs].sum(1)
        St, Nt = sums.sum(), cnts.sum()
        stat = (St - Sc) / (Nt - Nc) - Sc / Nc
        obs_idx = np.where((combs == np.arange(len(g_s), len(sums))).all(1))[0][0]
        obs = stat[obs_idx]
        p = np.mean(stat >= obs - 1e-12)
        per_sys[ns] = (Sc, Nc, St, Nt, obs_idx)
        tests.append({"test": "exact cluster-permutation test, one-sided (all C(23,3) relabelings of 3 of 23 clusters as "
                              "'concurrent'); statistic = mean(single) - mean(concurrent)",
                      "scope": name, "table": f"{len(g_s)} scenario clusters + {n_c} pair clusters; {len(combs)} relabelings",
                      "statistic": obs, "p_value": p, "note": f"min attainable p = 1/{len(combs)} = {1/len(combs):.5f}"})
    (Sc1, Nc1, St1, Nt1, o1), (Sc2, Nc2, St2, Nt2, o2) = per_sys["boutique"], per_sys["sock-shop"]
    Sc = Sc1[:, None] + Sc2[None, :]
    Nc = Nc1[:, None] + Nc2[None, :]
    stat = (St1 + St2 - Sc) / (Nt1 + Nt2 - Nc) - Sc / Nc
    obs = stat[o1, o2]
    p = np.mean(stat >= obs - 1e-12)
    tests.append({"test": "exact stratified cluster-permutation test, one-sided (relabel within each system; "
                          "statistic = pooled mean(single) - pooled mean(concurrent))",
                  "scope": "Both systems", "table": f"{stat.size} relabelings",
                  "statistic": obs, "p_value": p, "note": f"min attainable p = 1/{stat.size} = {1/stat.size:.2e}"})

    # Case-level stratified Monte Carlo permutation (ignores clustering)
    scores = {ns: (sf.loc[sf["namespace"] == ns, "flat_ac1"].to_numpy(float),
                   conc.loc[conc["namespace"] == ns, "ac2"].to_numpy(float)) for ns, _ in systems}
    obs = np.concatenate([scores[ns][0] for ns, _ in systems]).mean() - np.concatenate([scores[ns][1] for ns, _ in systems]).mean()
    nperm = 200000
    cnt = 0
    tot_s = sum(len(scores[ns][0]) for ns, _ in systems)
    tot_c = sum(len(scores[ns][1]) for ns, _ in systems)
    chunk = 20000
    for start in range(0, nperm, chunk):
        m = min(chunk, nperm - start)
        s_sum = np.zeros(m)
        c_sum = np.zeros(m)
        for ns, _ in systems:
            allv = np.concatenate(scores[ns])
            nc = len(scores[ns][1])
            perm = rng.permuted(np.tile(allv, (m, 1)), axis=1)
            c_sum += perm[:, :nc].sum(1)
            s_sum += perm[:, nc:].sum(1)
        cnt += int(np.sum(s_sum / tot_s - c_sum / tot_c >= obs - 1e-12))
    tests.append({"test": "case-level stratified permutation test, one-sided, Monte Carlo (200000 permutations)",
                  "scope": "Both systems", "table": f"{tot_s} single + {tot_c} concurrent cases",
                  "statistic": obs, "p_value": (cnt + 1) / (nperm + 1), "note": "ignores pair/scenario clustering"})

    # ---------- (ii) Both@k, Any@5 ----------
    for col, label in [("both2", "Both@2"), ("both3", "Both@3"), ("both5", "Both@5"), ("any5", "Any@5")]:
        for ns, name in systems + [("all", "Both systems")]:
            sub = conc if ns == "all" else conc[conc["namespace"] == ns]
            add_prop(label, name, int(sub[col].sum()), len(sub))
        strata = []
        for s_ns, _ in systems:
            g = conc[conc["namespace"] == s_ns].groupby("pair")[col].agg(["sum", "count"])
            strata.append((g["sum"].values, g["count"].values))
        lo, hi = pct(cluster_boot(strata, rng))
        add(label, "Both systems", int(conc[col].sum()), len(conc), conc[col].mean(),
            "pair-clustered bootstrap 95% (percentile, B=20000)", lo, hi, "3 pairs per system; coarse")
    if "ns_both2" in conc.columns:
        for col, label in [("ns_both2", "N-Sigma Both@2"), ("ns_both5", "N-Sigma Both@5"), ("ns_any5", "N-Sigma Any@5")]:
            add_prop(label, "Both systems", int(conc[col].sum()), len(conc))

    # ---------- (iii) the bound, per case ----------
    sep = conc_grid[(conc_grid["alpha"] == 0.7) & (conc_grid["eps"] == 0.4)].set_index("case_id")["separated"]
    pc = conc.copy()
    pc["separated_0.7_0.4"] = pc["case_id"].map(sep).astype(int)
    lopo_cases = pd.read_csv(os.path.join(C.RAW, "cv_lopo_cases.csv")).set_index("case_id")
    pc["lopo_alpha"] = pc["case_id"].map(lopo_cases["alpha"])
    pc["lopo_eps"] = pc["case_id"].map(lopo_cases["eps"])
    pc["lopo_separated"] = pc["case_id"].map(lopo_cases["separated"]).astype(int)
    pc["k_star"] = pc[["rank_cpu", "rank_mem"]].max(axis=1)  # smallest k with both causes in top k
    C.atomic_write_df(os.path.join(C.RAW, "bound_percase.csv"), pc[[
        "case_id", "namespace", "pair", "rep", "svc_cpu", "svc_mem", "rank_cpu", "rank_mem", "k_star", "n_ranked",
        "both_in_input", "both2", "both3", "both5", "any5", "ac2", "separated_0.7_0.4", "lopo_alpha", "lopo_eps",
        "lopo_separated"]])
    grid_rows = []
    for (a, e), g in conc_grid.groupby(["alpha", "eps"]):
        sc = set(g.loc[g["separated"] == 1, "case_id"])
        sub = pc[pc["case_id"].isin(sc)]
        grid_rows.append({"alpha": a, "eps": e, "n_cases": len(g), "k_separated": len(sc),
                          "k_sep_both_in_input": int(sub["both_in_input"].sum()),
                          "k_sep_both2": int(sub["both2"].sum()), "k_sep_both5": int(sub["both5"].sum()),
                          "max_kstar_of_separated": int(sub["k_star"].max()) if len(sub) else None,
                          "separated_cases": ";".join(sorted(sc))})
    bg = pd.DataFrame(grid_rows)
    C.atomic_write_df(os.path.join(C.RAW, "bound_grid.csv"), bg)

    # ---------- (iv) separation ----------
    k_sep = int(pc["separated_0.7_0.4"].sum())
    add_prop("separation (published 5-fold design; alpha=0.7, eps=0.4 in every fold; pooled held-out)", "Both systems",
             k_sep, 28, "fold-mean reported in paper = 0.073; pooled = k/28")
    k_lopo = int(pc["lopo_separated"].sum())
    add_prop("separation (post hoc leave-one-pair-out; pooled held-out)", "Both systems", k_lopo, 28)
    # paired comparison separated vs Both@2 (exact McNemar = binomial on discordant cases)
    b01 = int(((pc["separated_0.7_0.4"] == 1) & (pc["both2"] == 0)).sum())
    b10 = int(((pc["separated_0.7_0.4"] == 0) & (pc["both2"] == 1)).sum())
    p = stats.binomtest(b01, b01 + b10, 0.5).pvalue if b01 + b10 else 1.0
    tests.append({"test": "exact McNemar (separated vs Both@2, paired per case)", "scope": "Both systems",
                  "table": f"separated-not-Both@2={b01}, Both@2-not-separated={b10}", "statistic": b01 - b10,
                  "p_value": p, "note": "no evidence that separation differs from Both@2; per-case sets differ"})

    ci = pd.DataFrame(rows)
    ts = pd.DataFrame(tests)
    C.atomic_write_df(os.path.join(C.RAW, "stats_ci.csv"), ci)
    C.atomic_write_df(os.path.join(C.RAW, "stats_tests.csv"), ts)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 70)
    P(ci[["quantity", "scope", "k", "n", "estimate", "method", "lo", "hi"]].to_string(index=False))
    P("")
    P(ts[["test", "scope", "table", "statistic", "p_value"]].to_string(index=False))
    P("")
    P(pc[["case_id", "rank_cpu", "rank_mem", "k_star", "n_ranked", "both_in_input", "both2", "both5",
          "separated_0.7_0.4", "lopo_separated"]].to_string(index=False))
    P("")
    P(bg.to_string(index=False))
    C.atomic_write_text(os.path.join(C.RAW, "stats_ci.log"), "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
