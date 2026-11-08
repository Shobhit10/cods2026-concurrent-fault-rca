"""
corrected_numbers.py -- quantities for RESULTS_CORRECTED.md that verify.py computes but cannot finish on the corrected
set (it crashes on the published per-case files), or that no camera-ready script tabulates per system.
Imports common.py / load_cache.py from R (clustering NOT re-implemented; every per-case outcome comes from the
cached raw/cases/*.json written by the released pipeline via precompute.py).

Also cross-checks the cached per-case records against the CSVs that the ORIGINAL scripts (run_rq1.py,
run_second_ranker.py, run_faulttype_analysis.py) wrote for the same 30 cases (CODS_OUT_DIR=results/original_scripts).

Writes OUT/raw/corrected_*.csv and OUT/raw/corrected_numbers.log.
"""
import os
import sys

sys.dont_write_bytecode = True
FS = os.path.join(os.environ.get("CODS_REPO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")),
                  "analysis", "camera_ready", "folds_stats")
sys.path.insert(0, FS)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import load_cache as L  # noqa: E402

ORIG_OUT = os.environ.get("CODS_ORIG_OUT", os.path.join(os.path.dirname(C.OUT), "original_scripts"))
SYSTEMS = [("all", "overall"), ("boutique", "Online Boutique"), ("sock-shop", "Sock Shop")]
SEL = (0.7, 0.4)  # setting selected in every fold of every CV design (raw/cv_summary.csv)

log = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    log.append(s)


def main():
    recs, conc, conc_grid = L.concurrent_tables()
    _, sf, sf_grid = L.single_tables()

    # ---- inventory / exclusions (paper rule: robust_scorer fails when the change point is too close to the end) ----
    inv = pd.DataFrame([{"case_id": r["case_id"], "namespace": r["namespace"], "status": r.get("status"),
                         "detected": r.get("detected"), "anomaly_idx": r.get("anomaly_idx"), "n_rows": r.get("n_rows"),
                         "n_cols": r.get("n_cols"), "n_ranked": r.get("n_ranked")} for r in recs])
    C.atomic_write_df(os.path.join(C.RAW, "corrected_inventory.csv"), inv)
    P(f"cases: {len(recs)}; status ok: {int((inv.status == 'ok').sum())}; change point detected: "
      f"{int(inv.detected.astype(bool).sum())}; excluded: {inv.loc[inv.status != 'ok', 'case_id'].tolist()}")
    P(f"single-fault cases ok: {len(sf)}")

    # ---- (a) Table 1 ----
    rows = []
    for ns, name in SYSTEMS:
        sub = conc if ns == "all" else conc[conc["namespace"] == ns]
        n = len(sub)
        for m in ["ac1", "ac2", "ac3", "ac5"]:
            k = int(round(sub[m].sum() * 2))
            rows.append({"ranker": "BARO robust", "metric": m.upper().replace("AC", "AC@"), "scope": name, "k": k,
                         "n": 2 * n, "unit": "cause slots", "value": k / (2 * n)})
        for m, lab in [("both2", "Both@2"), ("both3", "Both@3"), ("both5", "Both@5"), ("any5", "Any@5")]:
            k = int(sub[m].sum())
            rows.append({"ranker": "BARO robust", "metric": lab, "scope": name, "k": k, "n": n, "unit": "cases",
                         "value": k / n})
        any2 = int((sub["hits2"] >= 1).sum())
        rows.append({"ranker": "BARO robust", "metric": "Any@2", "scope": name, "k": any2, "n": n, "unit": "cases",
                     "value": any2 / n})
        # ---- (c) N-Sigma ----
        for m in ["ns_ac1", "ns_ac2", "ns_ac3", "ns_ac5"]:
            k = int(round(sub[m].sum() * 2))
            rows.append({"ranker": "N-Sigma", "metric": m[3:].upper().replace("AC", "AC@"), "scope": name, "k": k,
                         "n": 2 * n, "unit": "cause slots", "value": k / (2 * n)})
        for m, lab in [("ns_both2", "Both@2"), ("ns_both5", "Both@5"), ("ns_any5", "Any@5")]:
            k = int(sub[m].sum())
            rows.append({"ranker": "N-Sigma", "metric": lab, "scope": name, "k": k, "n": n, "unit": "cases",
                         "value": k / n})
    t1 = pd.DataFrame(rows)
    C.atomic_write_df(os.path.join(C.RAW, "corrected_table1_nsigma.csv"), t1)
    P("\n(a)/(c) Table 1 (BARO robust) and N-Sigma:")
    P(t1.pivot_table(index=["ranker", "metric"], columns="scope", values="value", sort=False).round(3).to_string())

    # ---- (b) ranks ----
    rk = []
    for ns, name in SYSTEMS:
        sub = conc if ns == "all" else conc[conc["namespace"] == ns]
        n = len(sub)
        better = sub[["rank_cpu", "rank_mem"]].min(axis=1)
        worse = sub[["rank_cpu", "rank_mem"]].max(axis=1)
        rk.append({"scope": name, "n": n, "median_rank_better": float(np.median(better)),
                   "median_rank_second": float(np.median(worse)),
                   "k_second_outside_top5": int((worse > 5).sum()), "share_second_outside_top5": float((worse > 5).mean()),
                   "k_cpu_top5": int((sub["rank_cpu"] <= 5).sum()), "share_cpu_top5": float((sub["rank_cpu"] <= 5).mean()),
                   "k_mem_top5": int((sub["rank_mem"] <= 5).sum()), "share_mem_top5": float((sub["rank_mem"] <= 5).mean()),
                   "median_rank_cpu": float(np.median(sub["rank_cpu"])), "median_rank_mem": float(np.median(sub["rank_mem"])),
                   "ranked_list_len_min": int(sub["n_ranked"].min()), "ranked_list_len_max": int(sub["n_ranked"].max())})
    rk = pd.DataFrame(rk)
    C.atomic_write_df(os.path.join(C.RAW, "corrected_ranks.csv"), rk)
    P("\n(b) ranks:")
    P(rk.round(3).to_string(index=False))

    # ---- (g) Proposition 2.1 per separated case at the selected setting ----
    g = conc_grid[(conc_grid.alpha == SEL[0]) & (conc_grid.eps == SEL[1])].set_index("case_id")
    pc = conc.set_index("case_id").join(g[["separated", "grouped_ac1"]])
    pc["k_star"] = pc[["rank_cpu", "rank_mem"]].max(axis=1)
    pc["violation"] = ((pc["separated"] == 1) & (pc["both_in_input"] == 0)).astype(int)
    cols = ["namespace", "pair", "svc_cpu", "svc_mem", "rank_cpu", "rank_mem", "k_star", "n_ranked", "both_in_input",
            "both2", "both3", "both5", "separated", "grouped_ac1", "violation"]
    C.atomic_write_df(os.path.join(C.RAW, "corrected_prop21_allcases.csv"), pc.reset_index()[["case_id"] + cols])
    sep = pc[pc["separated"] == 1].reset_index()[["case_id"] + cols]
    C.atomic_write_df(os.path.join(C.RAW, "corrected_prop21_separated.csv"), sep)
    P(f"\n(g) separated at {SEL}: {len(sep)}/{len(pc)}; both in partitioned (full ranked) list: "
      f"{int(sep.both_in_input.sum())}/{len(sep)}; both in top 2: {int(sep.both2.sum())}; top 3: {int(sep.both3.sum())}; "
      f"top 5: {int(sep.both5.sum())}; violations: {int(pc.violation.sum())}")
    P(sep.to_string(index=False))
    b2 = set(pc.index[pc.both2 == 1])
    P(f"Both@2 cases: {sorted(b2)}; Both@2 not separated: {sorted(b2 - set(sep.case_id))}")

    # ---- (h) full-data grid (descriptive) ----
    gr = []
    for a, e in C.GRID:
        cg = conc_grid[(conc_grid.alpha == a) & (conc_grid.eps == e)]
        sg = sf_grid[(sf_grid.alpha == a) & (sf_grid.eps == e)]
        cgb = cg.merge(conc[["case_id", "namespace"]], on="case_id")
        gr.append({"alpha": a, "eps": e, "k_separated": int(cg.separated.sum()), "n_conc": len(cg),
                   "k_sep_boutique": int(cgb.loc[cgb.namespace == "boutique", "separated"].sum()),
                   "k_sep_sockshop": int(cgb.loc[cgb.namespace == "sock-shop", "separated"].sum()),
                   "grouped_ac1_halfpoints": float(cg.grouped_ac1.sum() * 2), "k_single_kept": int(sg.single_group.sum()),
                   "k_hit": int(sg.hit.sum()), "n_sf": len(sg),
                   "combined": (cg.separated.mean() + sg.single_group.mean()) / 2})
    gr = pd.DataFrame(gr)
    C.atomic_write_df(os.path.join(C.RAW, "corrected_grid_fulldata.csv"), gr)
    P("\n(h) full-data grid (all 30 + 200; descriptive):")
    P(gr.round(4).to_string(index=False))

    # ---- cross-check with the original scripts' CSVs ----
    chk = []
    try:
        rq1 = pd.read_csv(os.path.join(ORIG_OUT, "rq1_results.csv")).set_index("case_id")
        sr = pd.read_csv(os.path.join(ORIG_OUT, "second_ranker_percase.csv"))
        ft = pd.read_csv(os.path.join(ORIG_OUT, "faulttype_ranks.csv")).set_index("cid")
        rr = pd.read_csv(os.path.join(ORIG_OUT, "rankings_robust.csv"))
        cc = conc.set_index("case_id")
        ids = list(cc.index)
        chk.append(("rq1_results.csv: 30 rows with ac1, ids identical", bool(set(rq1.dropna(subset=["ac1"]).index) == set(ids))))
        for col in ["ac1", "ac2", "ac3", "ac5"]:
            chk.append((f"per-case {col} == rq1_results.csv", bool(np.allclose(cc[col], rq1.loc[ids, col]))))
        for scorer, pre in [("robust", ""), ("nsigma", "ns_")]:
            s = sr[sr["scorer"] == scorer].set_index("case_id")
            for col in ["both2", "both5", "any5"] + (["both3"] if scorer == "robust" else []):
                chk.append((f"per-case {pre}{col} == second_ranker_percase.csv ({scorer})",
                            bool(np.allclose(cc[pre + col], s.loc[ids, col]))))
            for col in ["ac2"]:
                chk.append((f"per-case {pre}{col} == second_ranker_percase.csv ({scorer})",
                            bool(np.allclose(cc[pre + col], s.loc[ids, col]))))
        chk.append(("per-case ranks (cpu, mem, n) == faulttype_ranks.csv",
                    bool((cc[["rank_cpu", "rank_mem", "n_ranked"]].values == ft.loc[ids, ["r_cpu", "r_mem", "n"]].values).all())))
        ok = True
        for r in recs:
            st = list(rr.loc[rr["case_id"] == r["case_id"]].sort_values("rank")["entry"])
            ok &= st == r["ranked"][:10]
        chk.append(("top-10 ranked lists == rankings_robust.csv (30 cases)", bool(ok)))
    except Exception as ex:  # report, do not hide
        chk.append((f"cross-check failed: {type(ex).__name__}: {ex}", False))
    chk = pd.DataFrame(chk, columns=["check", "ok"])
    C.atomic_write_df(os.path.join(C.RAW, "corrected_crosscheck_original_scripts.csv"), chk)
    P("\ncross-check with original scripts (results/original_scripts):")
    P(chk.to_string(index=False))
    C.atomic_write_text(os.path.join(C.RAW, "corrected_numbers.log"), "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
