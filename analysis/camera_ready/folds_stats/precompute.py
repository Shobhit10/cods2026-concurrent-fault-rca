"""
precompute.py -- runs the ORIGINAL pipeline once per case and caches everything needed downstream.

For each of the 30 concurrent cases (data_v2/) and the 200 single-fault cases (baro/data/fse-ob, fse-ss):
  bocpd -> robust_scorer (+ nsigma for concurrent) -> compute_deviation_scores (original run_rq2_v2 code)
  -> cluster_candidates_v2 for all 15 (alpha, eps) grid points -> per-case outcome
     (concurrent: separated, grouped_ac1 ; single-fault: single_group, hit)
  -> rank-position first design (run_rq2.cluster_candidates) at alpha=0.5, eps=0.3 (run_rq3.py setting)

Per-case results are written atomically to raw/cases/<id>.json, so the run is resumable.
The fold logic downstream only aggregates these per-case outcomes, exactly as
run_crossval_parallel.py does (its score_* functions are per-case then averaged).

Usage (WSL, baro-env):  PYTHONDONTWRITEBYTECODE=1 python precompute.py [--workers 8]
"""
import sys
sys.dont_write_bytecode = True
import argparse
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

CASE_DIR = os.path.join(C.RAW, "cases")


def _safe_name(s):
    return s.replace("/", "__")


def _cluster_outcomes(v2, ranked, dev_scores, graph, scorer, truth):
    out = {}
    for a, e in C.GRID:
        groups = v2.cluster_candidates_v2(ranked, dev_scores, graph, alpha=a, eps=e)
        out[f"{a}_{e}"] = scorer(groups, truth)
        if (a, e) == (0.7, 0.4):
            out["groups_0.7_0.4"] = {str(k): v for k, v in groups.items()}
    return out


def work_concurrent(item):
    warnings.filterwarnings("ignore")
    import pandas as pd
    from baro.anomaly_detection import bocpd
    from baro.root_cause_analysis import robust_scorer, nsigma
    v2 = C.load_rq2_v2()
    case_id, info = item
    rec = {"kind": "concurrent", "case_id": case_id, **info}
    path = os.path.join(C.CONC_DIR, f"{case_id}.csv")
    rec["data_md5"] = C.md5(path)
    data = pd.read_csv(path)
    rec["n_rows"], rec["n_cols"] = int(data.shape[0]), int(data.shape[1])
    try:
        anomalies = bocpd(data)
    except Exception as ex:  # noqa: BLE001
        rec["status"] = f"bocpd_failed: {ex}"
        return rec
    rec["detected"] = bool(anomalies) and anomalies[0] is not None
    if not rec["detected"]:
        rec["status"] = "no_anomaly"
        return rec
    rec["anomaly_idx"] = int(anomalies[0])
    try:
        res = robust_scorer(data, anomalies=anomalies)
    except Exception as ex:  # noqa: BLE001
        rec["status"] = f"scoring_failed: {ex}"
        return rec
    ranked, cands = res["ranks"], res["node_names"]
    try:
        rec["ranked_nsigma"] = nsigma(data, anomalies=anomalies)["ranks"]
    except Exception as ex:  # noqa: BLE001
        rec["ranked_nsigma"] = None
        rec["nsigma_error"] = str(ex)
    dev = v2.compute_deviation_scores(data, anomalies[0], cands)
    truth = [info["svc_a"], info["svc_b"]]
    rec.update({
        "status": "ok", "ranked": ranked, "node_names": cands, "dev_scores": dev,
        "rank_a": C.first_rank(ranked, info["svc_a"]), "rank_b": C.first_rank(ranked, info["svc_b"]),
        "n_ranked": len(ranked),
    })
    rec["grid"] = _cluster_outcomes(v2, ranked, dev, v2.GRAPHS[info["namespace"]], C.score_concurrent_case, truth)
    return rec


def work_single(case):
    warnings.filterwarnings("ignore")
    import pandas as pd
    from baro.anomaly_detection import bocpd
    from baro.root_cause_analysis import robust_scorer
    v2 = C.load_rq2_v2()
    v1 = C.load_rq2_v1()
    rec = {"kind": "single", **{k: case[k] for k in ("sf_id", "true_service", "fault_type", "namespace", "combo")}}
    rec["path_rel"] = "baro/data/" + os.path.relpath(case["path"], C.BARO_DATA).replace(os.sep, "/")
    rec["data_md5"] = C.md5(case["path"])
    data = pd.read_csv(case["path"])
    rec["n_rows"], rec["n_cols"] = int(data.shape[0]), int(data.shape[1])
    try:
        anomalies = bocpd(data)
    except Exception as ex:  # noqa: BLE001
        rec["status"] = f"bocpd_failed: {ex}"
        return rec
    rec["detected"] = bool(anomalies) and anomalies[0] is not None
    if not rec["detected"]:
        rec["status"] = "no_anomaly"
        return rec
    rec["anomaly_idx"] = int(anomalies[0])
    try:
        res = robust_scorer(data, anomalies=anomalies)
    except Exception as ex:  # noqa: BLE001
        rec["status"] = f"scoring_failed: {ex}"
        return rec
    ranked, cands = res["ranks"], res["node_names"]
    dev = v2.compute_deviation_scores(data, anomalies[0], cands)
    ts = case["true_service"]
    rec.update({
        "status": "ok", "ranked_top10": ranked[:10], "n_ranked": len(ranked),
        "flat_ac1": 1 if ranked and ranked[0].startswith(f"{ts}_") else 0,  # run_rq3.py rule
        "true_rank": C.first_rank(ranked, ts),
    })
    graph = v2.GRAPHS[case["namespace"]]
    grid = _cluster_outcomes(v2, ranked, dev, graph, C.score_single_case, ts)
    grid.pop("groups_0.7_0.4", None)
    rec["grid"] = grid
    # first (rank-position) design, run_rq3.py setting alpha=0.5, eps=0.3
    g1 = v1.cluster_candidates(ranked, graph, alpha=0.5, eps=0.3)
    rec["v1_0.5_0.3"] = C.score_single_case(g1, ts)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    ap.add_argument("--only", choices=["concurrent", "single", "all"], default="all")
    args = ap.parse_args()
    os.makedirs(CASE_DIR, exist_ok=True)
    C.load_rq2_v2()  # md5 gate
    import baro
    print("baro imported from:", os.path.dirname(baro.__file__), flush=True)

    jobs = []
    if args.only in ("concurrent", "all"):
        for item in C.parse_ground_truth().items():
            jobs.append(("c", item, os.path.join(CASE_DIR, f"conc__{item[0]}.json")))
    if args.only in ("single", "all"):
        for case in C.find_single_fault_cases():
            jobs.append(("s", case, os.path.join(CASE_DIR, f"sf__{_safe_name(case['sf_id'])}.json")))
    todo = [j for j in jobs if not os.path.exists(j[2])]
    print(f"{len(jobs)} cases total, {len(todo)} to compute, workers={args.workers}", flush=True)

    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for kind, payload, out in todo:
            fn = work_concurrent if kind == "c" else work_single
            futs[ex.submit(fn, payload)] = out
        for fut in as_completed(futs):
            out = futs[fut]
            rec = fut.result()
            C.atomic_write_json(out, rec)
            done += 1
            if done % 10 == 0 or done == len(todo):
                print(f"  {done}/{len(todo)} done ({time.time() - t0:.0f}s)", flush=True)
    print("precompute finished", flush=True)


if __name__ == "__main__":
    main()
