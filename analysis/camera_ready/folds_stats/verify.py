"""
verify.py -- reproduce the paper's published numbers (PROJECT_CONTEXT.md section 4 + Tables 1-4) from the raw
data (via precompute.py cache) and cross-check them against the stored result CSVs of the original project.

Writes raw/verification.csv and raw/verification.log. Any mismatch is flagged MISMATCH.
Checks that need the BARO single-fault cases (not redistributed) are flagged SKIPPED when raw/cases/sf__*.json is absent.
"""
import sys
sys.dont_write_bytecode = True
import json
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import cv_engine as E  # noqa: E402
import load_cache as L  # noqa: E402

rows = []
log = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    log.append(s)


def check(item, paper, recomputed, stored=None, tol=None, digits=3, note=""):
    """paper: number as printed; recomputed: float; tolerance = half a unit in the printed last digit."""
    if tol is None:
        tol = 0.5 * 10 ** (-digits) + 1e-12
    ok_r = abs(recomputed - paper) <= tol
    ok_s = True if stored is None else abs(stored - recomputed) <= 1e-9
    rows.append({"item": item, "paper": paper, "recomputed": recomputed,
                 "stored_csv": stored if stored is not None else "", "match": "OK" if (ok_r and ok_s) else "MISMATCH",
                 "note": note})


def skip(item):
    """Packaging addition: records a check that needs the BARO single-fault cases, which are not redistributed."""
    rows.append({"item": item, "paper": "", "recomputed": "", "stored_csv": "", "match": "SKIPPED",
                 "note": "needs the BARO single-fault cases (BARO_DATA_DIR; precompute.py --only single)"})


def main():
    recs, conc, conc_grid = L.concurrent_tables()
    sf_recs, sf, sf_grid = L.single_tables()
    have_sf = len(sf) > 0  # packaging addition: False when the BARO single-fault cases are absent
    src = C.PUB

    # ---------------- data inventory ----------------
    check("concurrent cases injected", 30, len(recs), digits=0)
    check("change point detected (of 30)", 30, sum(1 for r in recs if r.get("detected")), digits=0)
    check("usable concurrent cases", 28, len(conc), digits=0,
          note="2 excluded: " + ", ".join(r["case_id"] for r in recs if r.get("status") != "ok"))
    if have_sf:
        check("single-fault cases", 200, len(sf), digits=0)
        for ns, name in [("boutique", "Online Boutique"), ("sock-shop", "Sock Shop")]:
            check(f"single-fault cases, {name}", 100, int((sf["namespace"] == ns).sum()), digits=0)
    else:
        skip("single-fault cases (200; 100 per system)")

    # ---------------- single-fault AC@1 ----------------
    rq3 = pd.read_csv(os.path.join(src, "rq3_results.csv"))
    if have_sf:
        for ns, name, paper in [("boutique", "Online Boutique", 0.70), ("sock-shop", "Sock Shop", 0.85)]:
            check(f"single-fault AC@1, {name}", paper, sf.loc[sf["namespace"] == ns, "flat_ac1"].mean(),
                  rq3.loc[rq3["namespace"] == ns, "flat_ac1"].mean(), digits=2,
                  note=f"k={int(sf.loc[sf['namespace'] == ns, 'flat_ac1'].sum())}/100; stored = rq3_results.csv")
        # per-scenario multiset comparison with the stored file (order of rows differs)
        a = sf.groupby(["true_service", "fault_type"])["flat_ac1"].sum().sort_index()
        b = rq3.groupby(["true_service", "fault_type"])["flat_ac1"].sum().sort_index()
        same = a.equals(b.astype(a.dtype))
        rows.append({"item": "single-fault AC@1 per (service, fault type) == rq3_results.csv", "paper": "",
                     "recomputed": "identical" if same else "differs", "stored_csv": "", "match": "OK" if same else "MISMATCH",
                     "note": "40 scenarios x 5 reps"})
    else:
        skip("single-fault AC@1 (0.70 Online Boutique, 0.85 Sock Shop) and per-scenario == rq3_results.csv")

    # ---------------- RQ1 table ----------------
    rq1 = pd.read_csv(os.path.join(src, "rq1_results.csv")).dropna(subset=["ac1"]).set_index("case_id")
    sr = pd.read_csv(os.path.join(src, "second_ranker_percase.csv"))
    srr = sr[sr["scorer"] == "robust"].set_index("case_id")
    srn = sr[sr["scorer"] == "nsigma"].set_index("case_id")
    T1 = {  # metric: (overall, boutique, sock-shop)
        "ac1": (0.143, 0.067, 0.231), "ac2": (0.232, 0.167, 0.308), "ac3": (0.375, 0.300, 0.462),
        "ac5": (0.536, 0.400, 0.692), "both2": (0.071, 0.067, 0.077), "both5": (0.321, 0.267, 0.385),
        "any5": (0.750, 0.533, 1.000),
    }
    for m, vals in T1.items():
        for (ns, name), paper in zip([("all", "overall"), ("boutique", "Boutique"), ("sock-shop", "Sock Shop")], vals):
            sub = conc if ns == "all" else conc[conc["namespace"] == ns]
            stored_src = rq1 if m.startswith("ac") else srr
            st = stored_src.loc[sub["case_id"], m].mean()
            k = sub[m].sum() * (2 if m.startswith("ac") else 1)
            check(f"Table 1 {m.upper().replace('AC', 'AC@').replace('BOTH', 'Both@').replace('ANY', 'Any@')} {name}",
                  paper, sub[m].mean(), st, note=f"{'hits' if m.startswith('ac') else 'cases'}={k:g} of "
                                                 f"{len(sub) * (2 if m.startswith('ac') else 1)}")
    check("Fig 3 Both@3 overall", 0.107, conc["both3"].mean(), srr.loc[conc["case_id"], "both3"].mean(),
          note=f"{conc['both3'].sum()}/28")
    # per-case identity with stored per-case files
    for col in ["ac1", "ac2", "ac3", "ac5"]:
        same = np.allclose(conc.set_index("case_id")[col], rq1.loc[conc["case_id"], col])
        rows.append({"item": f"per-case {col} == rq1_results.csv (28 cases)", "paper": "", "recomputed": same,
                     "stored_csv": "", "match": "OK" if same else "MISMATCH", "note": ""})
    for col in ["both2", "both3", "both5", "any5"]:
        same = np.allclose(conc.set_index("case_id")[col], srr.loc[conc["case_id"], col])
        rows.append({"item": f"per-case {col} == second_ranker_percase.csv (robust)", "paper": "", "recomputed": same,
                     "stored_csv": "", "match": "OK" if same else "MISMATCH", "note": ""})

    # ---------------- ranks / fault types ----------------
    ft = pd.read_csv(os.path.join(src, "faulttype_ranks.csv")).set_index("cid")
    same = (conc.set_index("case_id")[["rank_cpu", "rank_mem", "n_ranked"]].values ==
            ft.loc[conc["case_id"], ["r_cpu", "r_mem", "n"]].values).all()
    rows.append({"item": "per-case true-cause ranks == faulttype_ranks.csv", "paper": "", "recomputed": bool(same),
                 "stored_csv": "", "match": "OK" if same else "MISMATCH", "note": ""})
    better = conc[["rank_cpu", "rank_mem"]].min(axis=1)
    worse = conc[["rank_cpu", "rank_mem"]].max(axis=1)
    check("second cause outside top 5 (%)", 68, 100 * (worse > 5).mean(), digits=0, note=f"{int((worse > 5).sum())}/28")
    check("median rank, better-ranked cause", 3, float(np.median(better)), digits=0)
    med_w = float(np.median(worse))
    rows.append({"item": "median rank, second cause", "paper": 6, "recomputed": med_w, "stored_csv": "",
                 "match": "OK" if med_w == 6 else "MINOR",
                 "note": "true median of 28 values is 6.5 (14th=6, 15th=7); run_faulttype_analysis.py printed it with "
                         "'{:.0f}', which rounds half-to-even to 6" if med_w == 6.5 else ""})
    check("CPU-cause recall@5", 0.61, (conc["rank_cpu"] <= 5).mean(), digits=2, note=f"{int((conc['rank_cpu'] <= 5).sum())}/28")
    check("memory-cause recall@5", 0.46, (conc["rank_mem"] <= 5).mean(), digits=2, note=f"{int((conc['rank_mem'] <= 5).sum())}/28")

    # ---------------- N-Sigma ----------------
    for m, paper in [("ns_ac2", 0.232), ("ns_both2", 0.071), ("ns_both5", 0.464), ("ns_any5", 0.893)]:
        st = srn.loc[conc["case_id"], m[3:]].mean()
        check(f"Table 2 N-Sigma {m[3:]}", paper, conc[m].mean(), st)

    # ---------------- rankings_robust.csv (top-10 lists) ----------------
    rr = pd.read_csv(os.path.join(src, "rankings_robust.csv"))
    ok = True
    for r in recs:
        if r.get("status") != "ok":
            continue
        st = list(rr.loc[rr["case_id"] == r["case_id"]].sort_values("rank")["entry"])
        ok &= st == r["ranked"][:10]
    rows.append({"item": "top-10 ranked lists == rankings_robust.csv (28 cases)", "paper": "", "recomputed": ok,
                 "stored_csv": "", "match": "OK" if ok else "MISMATCH", "note": ""})

    # ---------------- Fig 6 case study ----------------
    cs = [r for r in recs if r.get("status") == "ok" and r["pair"] == "sockshop_cpu-mem_pair1" and r["rank_a"] == 4
          and r["rank_b"] == 10]
    if cs:
        top = cs[0]["ranked"][:10]
        P("Fig 6 candidate case:", cs[0]["case_id"], "top-10:", top)
        rows.append({"item": "Fig 6 case (Sock Shop catalogue+carts): payment ranks 1-3, catalogue first at 4, carts first at 10",
                     "paper": "payment x3; catalogue 4,5; carts 10", "recomputed": " | ".join(f"{i+1}:{e}" for i, e in enumerate(top)),
                     "stored_csv": "", "match": "OK" if (all(e.startswith("payment_") for e in top[:3]) and
                                                        top[3].startswith("catalogue_") and top[4].startswith("catalogue_")
                                                        and top[9].startswith("carts_")) else "CHECK",
                     "note": cs[0]["case_id"]})

    # ---------------- first design ----------------
    if have_sf:
        check("first (rank-position) design: single-fault kept as one group", 0.0, sf["v1_single_group"].mean(),
              rq3["single_group"].astype(bool).mean(), note=f"{int(sf['v1_single_group'].sum())}/200 at alpha=0.5, eps=0.3")
    else:
        skip("first (rank-position) design: single-fault kept as one group (0/200)")
    c_cols = [r["n_cols"] - 1 for r in recs if r.get("status") == "ok"]
    s_cols = [r["n_cols"] - 1 for r in sf_recs if r.get("status") == "ok"]
    check("metric columns per case, concurrent (max)", 25, max(c_cols), digits=0,
          note=f"metric columns (excl. time) range {min(c_cols)}-{max(c_cols)}; ranked candidates after "
               f"preprocessing {conc['n_ranked'].min()}-{conc['n_ranked'].max()}; paper: 'carry 25 scored columns'")
    if have_sf:
        s_mode = int(pd.Series(s_cols).mode().iloc[0])
        check("metric columns per case, single-fault (mode)", 59, s_mode, digits=0,
              note=f"mode in {s_cols.count(s_mode)}/{len(s_cols)} cases; metric columns (excl. time) range "
                   f"{min(s_cols)}-{max(s_cols)}; ranked candidates after preprocessing {sf['n_ranked'].min()}-"
                   f"{sf['n_ranked'].max()}; paper: 'carries 59' (typical value, not the max); concurrent 25 = every "
                   f"Boutique case ({c_cols.count(25)}/28), Sock Shop cases have {min(c_cols)}")
    else:
        skip("metric columns per case, single-fault (mode 59)")

    # ---------------- corrected stage, cross-validation ----------------
    cv = pd.read_csv(os.path.join(src, "crossval_results.csv"))
    pub = {"separation": (0.073, 0.101), "grouped_ac1": (0.277, 0.132), "single_kept": (0.910, 0.034),
           "hit_rate": (0.740, 0.055)}
    colmap = {"separation": "concurrent_separation", "grouped_ac1": "concurrent_grouped_ac1",
              "single_kept": "single_fault_single_group", "hit_rate": "single_fault_hit_rate"}
    for m, (mu, sd) in pub.items():
        check(f"stored crossval_results.csv {m} mean", mu, cv[colmap[m]].mean())
        check(f"stored crossval_results.csv {m} SD", sd, cv[colmap[m]].std())
    check("stored crossval: folds choosing alpha=0.7, eps=0.4", 5, int(((cv.alpha == 0.7) & (cv.eps == 0.4)).sum()), digits=0)
    # pooled counts implied by the stored per-fold file vs full-data recomputation at (0.7, 0.4)
    g = conc_grid[(conc_grid.alpha == 0.7) & (conc_grid.eps == 0.4)]
    st_sep = float((cv.concurrent_separation * cv.n_concurrent_test).sum())
    st_gac = float((cv.concurrent_grouped_ac1 * cv.n_concurrent_test).sum())
    st_sg = float((cv.single_fault_single_group * cv.n_single_fault_test).sum())
    st_hit = float((cv.single_fault_hit_rate * cv.n_single_fault_test).sum())
    check("pooled held-out separated cases (count)", round(st_sep), g.separated.sum(), st_sep, digits=0,
          note="paper value = count implied by crossval_results.csv; recomputed on all 28 at (0.7,0.4)")
    check("pooled grouped AC@1 sum (half-points)", st_gac, g.grouped_ac1.sum(), st_gac, digits=6)
    if have_sf:
        s = sf_grid[(sf_grid.alpha == 0.7) & (sf_grid.eps == 0.4)]
        check("pooled single-fault kept (count)", round(st_sg), s.single_group.sum(), st_sg, digits=0)
        check("pooled single-fault hit (count)", round(st_hit), s.hit.sum(), st_hit, digits=0)
    else:
        skip("pooled single-fault kept (182/200) and hit (148/200), recomputed at (0.7, 0.4)")
    rq3v2 = pd.read_csv(os.path.join(src, "rq3_v2_final_results.csv"))
    rows.append({"item": "INFO: rq3_v2_final_results.csv (15 Aug, superseded pre-RobustScaler proxy; NOT used in paper)",
                 "paper": "", "recomputed": f"file: kept {int(rq3v2.single_group.sum())}/200, hit {int(rq3v2.hit.sum())}/200",
                 "stored_csv": "", "match": "INFO",
                 "note": "matches the 'intermediate step' 0.905/0.705 in PROJECT_CONTEXT (1).md; the paper uses crossval_results.csv"})

    # full-data grid: is (0.7, 0.4) the unique best on all data?
    if have_sf:
        full = []
        for a, e in C.GRID:
            sep = conc_grid[(conc_grid.alpha == a) & (conc_grid.eps == e)].separated.mean()
            sg = sf_grid[(sf_grid.alpha == a) & (sf_grid.eps == e)].single_group.mean()
            hit = sf_grid[(sf_grid.alpha == a) & (sf_grid.eps == e)].hit.mean()
            gac = conc_grid[(conc_grid.alpha == a) & (conc_grid.eps == e)].grouped_ac1.mean()
            full.append({"alpha": a, "eps": e, "separation": sep, "grouped_ac1": gac, "single_kept": sg, "hit": hit,
                         "combined": (sep + sg) / 2})
        full = pd.DataFrame(full).sort_values("combined", ascending=False)
        C.atomic_write_df(os.path.join(C.RAW, "grid_fulldata.csv"), full)
        P("Full-data grid (all 28 + 200; descriptive only):")
        P(full.to_string(index=False))

        # reconstructed published 5-fold (order assumption: ground-truth / sorted ids)
        O = E.Outcomes(conc_grid, sf_grid, conc)
        cf = E.make_folds_orig(list(conc["case_id"]), 5, 42)
        sff = E.make_folds_orig(list(sf["sf_id"]), 5, 42)
        folds, _ = E.run_cv(O, cf, sff)
        P("\nReconstructed published 5-fold (seed 42; list order = ground-truth order, NOT the original as_completed order):")
        P(folds[["fold", "alpha", "eps", "n_conc_test", "k_separated", "separation", "grouped_ac1", "n_sf_test",
                 "k_single_kept", "single_kept", "k_hit", "hit_rate"]].to_string(index=False))
    else:
        skip("full-data grid (raw/grid_fulldata.csv) and reconstructed published 5-fold")
    P("Published per-fold (crossval_results.csv):")
    P(cv.to_string(index=False))

    df = pd.DataFrame(rows)
    C.atomic_write_df(os.path.join(C.RAW, "verification.csv"), df)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 90)
    P("\n" + df.to_string(index=False))
    P(f"\nMISMATCH rows: {int((df['match'] == 'MISMATCH').sum())}; MINOR rows: {int((df['match'] == 'MINOR').sum())}; "
      f"CHECK rows: {int((df['match'] == 'CHECK').sum())}")
    if not have_sf:
        P(f"SKIPPED rows: {int((df['match'] == 'SKIPPED').sum())} (BARO single-fault cases not present)")
    C.atomic_write_text(os.path.join(C.RAW, "verification.log"), "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
