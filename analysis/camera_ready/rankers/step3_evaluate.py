"""
step3_evaluate.py -- metrics, clustering stage and Proposition 2.1 check for every ranker.
Run in baro-env (needs numpy/pandas/networkx/sklearn only):  python step3_evaluate.py [concurrent|single|all]

Rankers (all on the SAME bocpd change point and the SAME candidate metrics):
  robust        paper ranker (BARO RobustScorer, median/IQR)           -- reproduction check
  nsigma        N-Sigma (mean/std), already in the paper               -- reproduction check
  pagerank      personalised PageRank over the call graph (adapted run_graph_ranker.py), metric-expanded
  circa         CIRCA (PC + regression-based hypothesis testing), paper windows      [causal]
  circa_rcaeval CIRCA with RCAEval's default windows / node handling (sensitivity)    [causal]
  rcd           RCD (RCAEval), 10 seeds (concurrent) / 3 seeds (single)              [causal]
  random        uniformly random ranking: exact expectations; stage by Monte Carlo (200 perms/case)

Clustering stage = released cluster_candidates_v2 + score_concurrent/score_single_fault logic,
alpha=0.7, eps=0.4, minPts=2. Modes: full (entire list, as in the released code), top5, top10.
Service mapping: paper (released rsplit) and fixed (suffix-aware).
"""

import os
import sys
import json
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import common as C

MODES = {"full": None, "top5": 5, "top10": 10}
N_PERM = 200


# --------------------------------------------------------------- fast stage (for random MC only)
class FastStage:
    """Same computation as cluster_candidates_v2 with cached hop counts (verified equal on real rankers)."""

    def __init__(self, graph, svc_fn):
        self.graph, self.svc_fn, self.cache = graph, svc_fn, {}

    def hops(self, a, b):
        k = (a, b)
        if k not in self.cache:
            self.cache[k] = C.graph_hops(self.graph, a, b)
        return self.cache[k]

    def cluster(self, ranked, dev, alpha, eps):
        from sklearn.cluster import DBSCAN
        n = len(ranked)
        if n < 2:
            return {0: ranked}
        mh = self.graph.number_of_nodes()
        d = np.array([dev.get(e, 0) for e in ranked])
        s = [self.svc_fn(e) for e in ranked]
        H = np.array([[self.hops(s[i], s[j]) for j in range(n)] for i in range(n)], dtype=float)
        D = alpha * np.abs(d[:, None] - d[None, :]) + (1 - alpha) * (H / mh)
        labels = DBSCAN(eps=eps, min_samples=2, metric="precomputed").fit_predict(D)
        groups, nc = {}, 1000
        for i, lab in enumerate(labels):
            if lab == -1:
                groups["noise_%d" % nc] = [ranked[i]]
                nc += 1
            else:
                groups.setdefault(lab, []).append(ranked[i])
        return groups


def stage_input(ranked, mode):
    k = MODES[mode]
    return list(ranked) if k is None else list(ranked[:k])


def both_in(entries, true_services):
    return float(all(any(e.startswith(s + "_") for e in entries) for s in true_services))


# --------------------------------------------------------------- loading
def load_rankings(kind):
    pre = [r for r in C.read_json("%s/precompute_%s.json" % (C.OUT, kind)) if r.get("usable")]
    by_case = {r["case_id"]: r for r in pre}
    lists = {}   # ranker -> seed -> case -> list
    for name in ("robust", "nsigma"):
        lists[name] = {0: {r["case_id"]: r[name] for r in pre}}
    lists["pagerank"] = {0: {r["case_id"]: r["pagerank_metric"] for r in pre}}
    runtimes = {"robust": [r["t_robust"] for r in pre], "nsigma": [r["t_nsigma"] for r in pre],
                "pagerank": [r["t_pagerank"] for r in pre], "bocpd": [r["t_bocpd"] for r in pre]}
    fails = {}
    for m in ("circa", "circa_rcaeval", "rcd", "run", "run_native", "causalrca"):
        p = "%s/causal_%s_%s.json" % (C.OUT, m, kind)
        if not os.path.exists(p):
            continue
        res = C.read_json(p)
        lists[m] = {}
        for r in res:
            seed = 0 if r["seed"] is None else r["seed"]
            lists[m].setdefault(seed, {})[r["case_id"]] = r["ranks"] if r["ok"] else []
        runtimes[m] = [r["runtime_s"] for r in res]
        fails[m] = [(r["case_id"], r["seed"], r.get("error")) for r in res if not r["ok"]]
    return pre, by_case, lists, runtimes, fails


def mean_sd(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.mean(vals)), float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0)


# --------------------------------------------------------------- concurrent
def evaluate_concurrent():
    pre, by_case, lists, runtimes, fails = load_rankings("concurrent")
    cases = sorted(by_case)
    n = len(cases)
    rank_rows, stage_rows, grid_rows = [], [], []

    # ---- real rankers
    for ranker, seeds in lists.items():
        for seed, per_case in seeds.items():
            for cid in cases:
                rec = by_case[cid]
                ranked = per_case.get(cid, [])
                ts = rec["true_services"]
                m = C.conc_rank_metrics(ranked, ts)
                m.update(C.svc_list_metrics(C.service_level_list(ranked), ts))
                m.update({"ranker": ranker, "seed": seed, "case_id": cid, "namespace": rec["namespace"]})
                rank_rows.append(m)
                dev = C.normalise_like_paper(rec["dev_raw"])
                for mapping, fn in C.SVC_FNS.items():
                    graph = C.GRAPHS[rec["namespace"]]
                    fast = FastStage(graph, fn)
                    for mode in MODES:
                        inp = stage_input(ranked, mode)
                        g = C.cluster_candidates_v2(inp, dev, graph, alpha=C.ALPHA, eps=C.EPS, svc_fn=fn)
                        sc = C.score_concurrent_case(g, ts)
                        sc.update({"ranker": ranker, "seed": seed, "case_id": cid, "mapping": mapping, "mode": mode,
                                   "k_in": len(inp), "both_in": both_in(inp, ts),
                                   "both2": m["both2"], "namespace": rec["namespace"]})
                        stage_rows.append(sc)
                        # oracle grid (tuned on the very cases it is scored on -> optimistic upper bound)
                        for a in C.ALPHAS:
                            for e in C.EPSS:
                                g2 = fast.cluster(inp, dev, a, e)
                                s2 = C.score_concurrent_case(g2, ts)
                                grid_rows.append({"ranker": ranker, "seed": seed, "case_id": cid, "mapping": mapping,
                                                  "mode": mode, "alpha": a, "eps": e, "separated": s2["separated"],
                                                  "both_in": both_in(inp, ts)})

    # ---- random ranking: exact expectations + Monte Carlo stage
    for cid in cases:
        rec = by_case[cid]
        ex = C.random_conc_expectation(rec["candidates"], rec["true_services"])
        row = {"ranker": "random", "seed": 0, "case_id": cid, "namespace": rec["namespace"]}
        for k in ("ac1", "ac2", "ac3", "ac5", "both2", "both3", "both5", "both10", "both_all", "list_len"):
            row[k] = ex[k]
        row["any5"] = ex["any5"]
        row.update(C.random_svc_expectation(rec["candidates"], rec["true_services"]))
        rank_rows.append(row)
    rng = random.Random(12345)
    for cid in cases:
        rec = by_case[cid]
        ts = rec["true_services"]
        dev = C.normalise_like_paper(rec["dev_raw"])
        stages = {mp: FastStage(C.GRAPHS[rec["namespace"]], fn) for mp, fn in C.SVC_FNS.items()}
        acc = {}
        for p in range(N_PERM):
            perm = list(rec["candidates"])
            rng.shuffle(perm)
            for mapping, st in stages.items():
                for mode in MODES:
                    inp = stage_input(perm, mode)
                    g = st.cluster(inp, dev, C.ALPHA, C.EPS)
                    sc = C.score_concurrent_case(g, ts)
                    a = acc.setdefault((mapping, mode), {"separated": 0.0, "grouped_ac1": 0.0, "both_in": 0.0,
                                                         "viol": 0.0, "k_in": len(inp)})
                    bi = both_in(inp, ts)
                    a["separated"] += sc["separated"] / N_PERM
                    a["grouped_ac1"] += sc["grouped_ac1"] / N_PERM
                    a["both_in"] += bi / N_PERM
                    a["viol"] += float(sc["separated"] > bi)
        for (mapping, mode), a in acc.items():
            stage_rows.append({"ranker": "random", "seed": 0, "case_id": cid, "mapping": mapping, "mode": mode,
                               "k_in": a["k_in"], "both_in": a["both_in"], "separated": a["separated"],
                               "grouped_ac1": a["grouped_ac1"], "perm_violations": a["viol"],
                               "both2": None, "namespace": rec["namespace"]})

    # ---- equivalence check FastStage vs verbatim (robust list)
    eq_ok = True
    for cid in cases:
        rec = by_case[cid]
        dev = C.normalise_like_paper(rec["dev_raw"])
        for mapping, fn in C.SVC_FNS.items():
            g1 = C.cluster_candidates_v2(rec["robust"], dev, C.GRAPHS[rec["namespace"]], C.ALPHA, C.EPS, svc_fn=fn)
            g2 = FastStage(C.GRAPHS[rec["namespace"]], fn).cluster(rec["robust"], dev, C.ALPHA, C.EPS)
            eq_ok &= ({str(k): v for k, v in g1.items()} == {str(k): v for k, v in g2.items()})

    R = pd.DataFrame(rank_rows)
    S = pd.DataFrame(stage_rows)
    G = pd.DataFrame(grid_rows)
    R.to_csv(C.OUT + "/concurrent_ranking_percase.csv", index=False)
    S.to_csv(C.OUT + "/concurrent_stage_percase.csv", index=False)

    # ---- summaries
    order = [o for o in ["robust", "nsigma", "pagerank", "circa", "circa_rcaeval", "rcd", "run", "run_native", "causalrca", "random"] if o in lists or o == "random"]
    order = [o for o in order if o in set(R["ranker"])]
    metr = ["ac1", "ac2", "ac3", "ac5", "both2", "both3", "both5", "both10", "any5", "both_all", "list_len"]
    summ = {"n_cases": n, "fast_stage_equivalent": bool(eq_ok), "rankers": {}, "fails": fails}
    for rk in order:
        sub = R[R["ranker"] == rk]
        seeds = sorted(sub["seed"].unique())
        ent = {"n_seeds": len(seeds), "ranking": {}, "ranking_by_ns": {}, "svc": {}, "stage": {}, "grid_best": {}}
        for mtr in metr:
            per_seed = [sub[sub["seed"] == s][mtr].mean() for s in seeds]
            ent["ranking"][mtr] = mean_sd(per_seed)
        for ns in ("boutique", "sock-shop"):
            ent["ranking_by_ns"][ns] = {mtr: mean_sd([sub[(sub["seed"] == s) & (sub["namespace"] == ns)][mtr].mean()
                                                       for s in seeds]) for mtr in ("ac2", "both2", "both5", "any5")}
        if "svc_ac2" in sub and sub["svc_ac2"].notna().any():
            for mtr in ("svc_ac1", "svc_ac2", "svc_both2", "svc_both3", "svc_both5", "svc_any1", "svc_any2",
                        "svc_any5"):
                ent["svc"][mtr] = mean_sd([sub[sub["seed"] == s][mtr].mean() for s in seeds])
        # exact 95% Clopper-Pearson intervals (deterministic rankers only: one list per case)
        if rk != "random" and len(seeds) == 1:
            ent["ci95"] = {mtr: clopper_from(sub[mtr]) for mtr in ("both2", "both5", "any5", "both_all", "svc_both2")}
        # median ranks of better / worse cause (first seed only for rcd)
        if rk != "random":
            s0 = sub[sub["seed"] == seeds[0]]
            ra = s0[["rank_a", "rank_b"]].astype(float)
            ent["median_rank_better"] = float(np.nanmedian(ra.min(axis=1)))
            # a cause missing from the list counts as rank infinity (reported as 999)
            ent["median_rank_worse"] = float(np.median(ra.fillna(999).max(axis=1)))
        ss = S[S["ranker"] == rk]
        for mapping in C.SVC_FNS:
            for mode in MODES:
                q = ss[(ss["mapping"] == mapping) & (ss["mode"] == mode)]
                per_seed_sep = [q[q["seed"] == s]["separated"].mean() for s in seeds]
                per_seed_bin = [q[q["seed"] == s]["both_in"].mean() for s in seeds]
                per_seed_gac = [q[q["seed"] == s]["grouped_ac1"].mean() for s in seeds]
                bound_ok = all(a <= b + 1e-12 for a, b in zip(per_seed_sep, per_seed_bin))
                if rk == "random":
                    viol = int(q["perm_violations"].sum())
                else:
                    viol = int(((q["separated"] > 0) & (q["both_in"] == 0)).sum())
                sep_cases = sorted(q[(q["seed"] == seeds[0]) & (q["separated"] > 0)]["case_id"].tolist()) \
                    if rk != "random" else []
                ent["stage"]["%s/%s" % (mapping, mode)] = {
                    "separation": mean_sd(per_seed_sep), "both_in": mean_sd(per_seed_bin),
                    "grouped_ac1": mean_sd(per_seed_gac), "bound_holds_every_seed": bound_ok,
                    "case_level_violations": viol, "k_in_mean": float(q["k_in"].mean()),
                    "separated_cases_seed0": sep_cases,
                    "sep_le_both2": (all(a <= b + 1e-12 for a, b in zip(per_seed_sep,
                                     [R[(R["ranker"] == rk) & (R["seed"] == s)]["both2"].mean() for s in seeds]))),
                }
                if rk != "random" and len(seeds) == 1:
                    ent["stage"]["%s/%s" % (mapping, mode)]["separation_ci95"] = clopper_from(q["separated"])
                if rk != "random":
                    gq = G[(G["ranker"] == rk) & (G["mapping"] == mapping) & (G["mode"] == mode)]
                    # per-seed mean over cases, then mean over seeds
                    bseed = gq.groupby(["alpha", "eps", "seed"])["separated"].mean().groupby(["alpha", "eps"]).mean()
                    a_e = bseed.idxmax()
                    b2 = float(np.mean([R[(R["ranker"] == rk) & (R["seed"] == s)]["both2"].mean() for s in seeds]))
                    ent["grid_best"]["%s/%s" % (mapping, mode)] = {
                        "separation": float(bseed.max()), "alpha": a_e[0], "eps": a_e[1],
                        "n_settings": int(len(bseed)), "n_settings_sep_gt_both2": int((bseed > b2 + 1e-12).sum()),
                        "grid_case_level_violations": int(((gq["separated"] > 0) & (gq["both_in"] == 0)).sum())}
        if rk in runtimes:
            ent["runtime_s_per_case"] = mean_sd(runtimes[rk])
        summ["rankers"][rk] = ent
    summ["runtime_bocpd_s_per_case"] = mean_sd(runtimes["bocpd"])

    # ---- below-chance test: P(X <= observed) when the ranker is a uniformly random permutation
    #      (X = number of cases with the event; Poisson-binomial with the exact per-case probabilities)
    rnd = R[R["ranker"] == "random"].set_index("case_id")
    summ["below_chance"] = {}
    for rk in order:
        if rk == "random":
            continue
        sub = R[R["ranker"] == rk]
        seeds = sorted(sub["seed"].unique())
        ent = {}
        for mtr in ("both2", "both5", "any5"):
            probs = [float(rnd.loc[c, mtr]) for c in cases]
            obs = [int(round(sub[sub["seed"] == s][mtr].sum())) for s in seeds]
            ent[mtr] = {"observed_cases": obs if len(obs) > 1 else obs[0],
                        "expected_cases_random": float(sum(probs)),
                        "p_le_observed": [poisson_binomial_cdf(probs, o) for o in obs] if len(obs) > 1
                        else poisson_binomial_cdf(probs, obs[0])}
        summ["below_chance"][rk] = ent

    # ---- service-level-only lists from the original run_graph_ranker.py design
    svc_only = {}
    for name, key in (("pagerank_all_graph_nodes", "pagerank_svc"), ("deviation_service_max", "devsvc_svc")):
        rows = [C.svc_list_metrics(by_case[c][key], by_case[c]["true_services"]) for c in cases]
        svc_only[name] = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
    summ["service_level_only"] = svc_only
    C.atomic_write_json(C.OUT + "/summary_concurrent.json", summ)
    return summ


def poisson_binomial_cdf(probs, x):
    dist = np.zeros(len(probs) + 1)
    dist[0] = 1.0
    for p in probs:
        dist[1:] = dist[1:] * (1 - p) + dist[:-1] * p
        dist[0] = dist[0] * (1 - p)
    return float(dist[: x + 1].sum())


def clopper_from(series):
    v = [float(x) for x in series if x is not None and not (isinstance(x, float) and np.isnan(x))]
    k = int(round(sum(v)))
    return {"k": k, "n": len(v), "ci": C.clopper_pearson(k, len(v))}


# --------------------------------------------------------------- single fault
def evaluate_single():
    pre, by_case, lists, runtimes, fails = load_rankings("single")
    cases = sorted(by_case)
    rank_rows, stage_rows = [], []
    for ranker, seeds in lists.items():
        for seed, per_case in seeds.items():
            for cid in cases:
                if cid not in per_case:      # causal rankers may cover only the stratified subset
                    continue
                rec = by_case[cid]
                ranked = per_case[cid]
                t = rec["true_services"][0]
                m = C.single_rank_metrics(ranked, t)
                m.update({"ranker": ranker, "seed": seed, "case_id": cid, "namespace": rec["namespace"],
                          "fault": rec["faults"][0]})
                rank_rows.append(m)
                dev = C.normalise_like_paper(rec["dev_raw"])
                for mode in MODES:
                    inp = stage_input(ranked, mode)
                    g = C.cluster_candidates_v2(inp, dev, C.GRAPHS[rec["namespace"]], alpha=C.ALPHA, eps=C.EPS,
                                                svc_fn=C.svc_paper)
                    sc = C.score_single_case(g, t)
                    sc.update({"ranker": ranker, "seed": seed, "case_id": cid, "mode": mode, "k_in": len(inp),
                               "namespace": rec["namespace"]})
                    stage_rows.append(sc)
    for cid in cases:
        rec = by_case[cid]
        ex = C.random_single_expectation(rec["candidates"], rec["true_services"][0])
        ex.update({"ranker": "random", "seed": 0, "case_id": cid, "namespace": rec["namespace"],
                   "fault": rec["faults"][0]})
        rank_rows.append(ex)
    R = pd.DataFrame(rank_rows)
    S = pd.DataFrame(stage_rows)
    R.to_csv(C.OUT + "/single_ranking_percase.csv", index=False)
    S.to_csv(C.OUT + "/single_stage_percase.csv", index=False)
    summ = {"n_cases": len(cases), "n_total": len(C.read_json("%s/precompute_single.json" % C.OUT)),
            "rankers": summarise_single(R, S, None, runtimes), "fails": fails}
    covered = [set(R[R["ranker"] == rk]["case_id"]) for rk in set(R["ranker"])]
    common_cases = sorted(set.intersection(*covered))
    summ["paired_subset"] = {"n_cases": len(common_cases),
                             "reps": sorted(set(c.split("__")[-1] for c in common_cases)),
                             "rankers": summarise_single(R, S, set(common_cases), runtimes)}
    summ["runtime_bocpd_s_per_case"] = mean_sd(runtimes["bocpd"])
    C.atomic_write_json(C.OUT + "/summary_single.json", summ)
    return summ


def summarise_single(R, S, case_set, runtimes):
    if case_set is not None:
        R = R[R["case_id"].isin(case_set)]
        S = S[S["case_id"].isin(case_set)]
    out = {}
    order = [o for o in ["robust", "nsigma", "pagerank", "circa", "circa_rcaeval", "rcd", "random"]
             if o in set(R["ranker"])]
    for rk in order:
        sub = R[R["ranker"] == rk]
        seeds = sorted(sub["seed"].unique())
        ent = {"n_seeds": len(seeds), "n_cases": int(sub["case_id"].nunique()), "ranking": {},
               "ranking_by_ns": {}, "stage": {}}
        for mtr in ("ac1", "ac3", "ac5", "list_len"):
            ent["ranking"][mtr] = mean_sd([sub[sub["seed"] == s][mtr].mean() for s in seeds])
        if rk != "random" and len(seeds) == 1:
            ent["ci95"] = {"ac1": clopper_from(sub["ac1"]), "ac5": clopper_from(sub["ac5"])}
        for ns in ("boutique", "sock-shop"):
            ent["ranking_by_ns"][ns] = {mtr: mean_sd([sub[(sub["seed"] == s) & (sub["namespace"] == ns)][mtr].mean()
                                                       for s in seeds]) for mtr in ("ac1", "ac3", "ac5")}
        ss = S[S["ranker"] == rk] if len(S) else S
        for mode in MODES:
            if not len(ss):
                break
            q = ss[ss["mode"] == mode]
            ent["stage"][mode] = {"kept_one_group": mean_sd([q[q["seed"] == s]["single_group"].mean() for s in seeds]),
                                  "hit": mean_sd([q[q["seed"] == s]["hit"].mean() for s in seeds]),
                                  "k_in_mean": float(q["k_in"].mean())}
        if rk in runtimes and case_set is None:
            ent["runtime_s_per_case"] = mean_sd(runtimes[rk])
        out[rk] = ent
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "concurrent"
    t0 = time.time()
    if which in ("concurrent", "all"):
        s = evaluate_concurrent()
        print("concurrent: n=%d, fast-stage equivalent=%s" % (s["n_cases"], s["fast_stage_equivalent"]))
        for rk, e in s["rankers"].items():
            r = e["ranking"]
            st = e["stage"]
            print("%-14s AC1 %.3f AC2 %.3f AC5 %.3f B2 %.3f B5 %.3f A5 %.3f | sep full/paper %.3f full/fixed %.3f "
                  "top5/paper %.3f (both@5in %.3f) top10/paper %.3f" % (
                      rk, r["ac1"][0], r["ac2"][0], r["ac5"][0], r["both2"][0], r["both5"][0], r["any5"][0],
                      st["paper/full"]["separation"][0], st["fixed/full"]["separation"][0],
                      st["paper/top5"]["separation"][0], st["paper/top5"]["both_in"][0],
                      st["paper/top10"]["separation"][0]))
    if which in ("single", "all"):
        s = evaluate_single()
        print("single: n=%d of %d" % (s["n_cases"], s["n_total"]))
        for rk, e in s["rankers"].items():
            r = e["ranking"]
            st = e["stage"].get("full", {})
            print("%-14s AC1 %.3f AC3 %.3f AC5 %.3f | kept %s hit %s" % (
                rk, r["ac1"][0], r["ac3"][0], r["ac5"][0], st.get("kept_one_group"), st.get("hit")))
    print("done in %.0fs" % (time.time() - t0))
