"""
step1_precompute_baro.py -- run in baro-env (py3.10).

For every concurrent case (data_v2, 30) and every single-fault case (fse-ob/fse-ss, 200):
  * change point  tau = bocpd(data)[0]                         (paper Stage 1, unchanged)
  * paper ranker  robust_scorer(data, anomalies=[tau, ...])      (median/IQR, the paper's ranker)
  * N-Sigma       nsigma(data, anomalies=...)                    (already in the paper, reproduced)
  * candidates    = robust_scorer node_names (columns non-constant in both windows)
  * dev_raw       = Eq. (dev) max|z| per candidate (compute_deviation_scores without normalisation)
  * PageRank      personalised PageRank over the call graph seeded with per-service max dev
                  (adapted run_graph_ranker.py: same graph/alpha/personalisation, but restricted to the
                  same candidate metrics as every other ranker), expanded back to metric entries.
Each case is cached to outputs/cache/baro/<case>.json (resume-safe); combined files are written atomically.
"""

import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if os.environ.get("BARO_SRC"):  # optional: a BARO source checkout instead of the pip-installed fse-baro
    sys.path.insert(0, os.environ["BARO_SRC"])

import numpy as np
import pandas as pd
import networkx as nx

import common as C


def pagerank_rank(dev_raw, candidates, graph):
    svc_score = {}
    for c in candidates:
        s = C.svc_fixed(c)
        svc_score[s] = max(svc_score.get(s, 0.0), dev_raw.get(c, 0.0))
    pers = {v: svc_score.get(v, 0.0) + 1e-6 for v in graph.nodes()}
    pr = nx.pagerank(graph, alpha=0.85, personalization=pers)
    svc_rank = [v for v, _ in sorted(pr.items(), key=lambda x: -x[1])]
    by_svc = {}
    for c in candidates:
        by_svc.setdefault(C.svc_fixed(c), []).append(c)
    expanded = []
    for s in svc_rank:
        for c in sorted(by_svc.get(s, []), key=lambda c: -dev_raw.get(c, 0.0)):
            expanded.append(c)
    # candidates whose service is not a graph node (should not happen for the concurrent set)
    missing = [c for c in candidates if c not in set(expanded)]
    expanded += sorted(missing, key=lambda c: -dev_raw.get(c, 0.0))
    dev_svc_rank = [s for s, _ in sorted(svc_score.items(), key=lambda x: -x[1])]
    return {"pagerank_svc": svc_rank, "pagerank_scores": {k: float(v) for k, v in pr.items()},
            "pagerank_metric": expanded, "devsvc_svc": dev_svc_rank,
            "n_unmapped": len(missing)}


FOLDS_CASES = C.FOLDS_CASES


def reused_change_point(case_id, path):
    """Single-fault only (CP_REUSE=1): bocpd takes ~4 min per 721x59 case. The folds_stats
    pipeline already ran the SAME baro bocpd on the SAME files (md5-checked here) and cached
    anomalies[0]; robust_scorer/nsigma read only anomalies[0], so reusing it is exact. Verified on
    cases recomputed without reuse."""
    import hashlib
    p = "%s/sf__%s.json" % (FOLDS_CASES, case_id)
    if not os.path.exists(p):
        return None
    r = C.read_json(p)
    if r.get("status") != "ok" or "anomaly_idx" not in r:
        return None
    with open(path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    if md5 != r.get("data_md5"):
        return None
    return int(r["anomaly_idx"])


def process(item):
    kind, case_id, path, ns = item["kind"], item["case_id"], item["path"], item["namespace"]
    cache = "%s/baro/%s.json" % (C.CACHE, case_id)
    if os.path.exists(cache):
        return C.read_json(cache)
    from baro.anomaly_detection import bocpd
    from baro.root_cause_analysis import robust_scorer, nsigma
    rec = dict(item)
    data = pd.read_csv(C.resolve(path))
    rec["n_rows"], rec["n_cols"] = int(data.shape[0]), int(data.shape[1] - 1)
    t0 = time.time()
    reused = reused_change_point(case_id, C.resolve(path)) if (kind == "single" and os.environ.get("CP_REUSE")) else None
    if reused is not None:
        anomalies = [reused]
        rec["cp_source"] = "folds_stats bocpd cache (md5-matched)"
        rec["t_bocpd"] = None
    else:
        try:
            anomalies = bocpd(data)
        except Exception as e:
            rec.update({"usable": False, "reason": "bocpd exception: %r" % (e,)})
            C.atomic_write_json(cache, rec)
            return rec
        rec["cp_source"] = "bocpd (this run)"
        rec["t_bocpd"] = time.time() - t0
    if not anomalies or anomalies[0] is None:
        rec.update({"usable": False, "reason": "bocpd returned no change point", "anomalies": list(anomalies or [])})
        C.atomic_write_json(cache, rec)
        return rec
    cp = int(anomalies[0])
    rec["cp"] = cp
    rec["cp_time"] = float(data["time"].iloc[cp]) if cp < len(data) else None
    rec["anomalies"] = [int(a) for a in anomalies]
    try:
        t0 = time.time()
        r = robust_scorer(data, anomalies=anomalies)
        rec["t_robust"] = time.time() - t0
        t0 = time.time()
        rn = nsigma(data, anomalies=anomalies)
        rec["t_nsigma"] = time.time() - t0
    except Exception as e:
        rec.update({"usable": False, "reason": "scoring exception: %r" % (e,)})
        C.atomic_write_json(cache, rec)
        return rec
    cands = list(r["node_names"])
    rec["candidates"] = cands
    rec["robust"] = list(r["ranks"])
    rec["nsigma"] = list(rn["ranks"])
    t0 = time.time()
    dev_raw = C.dev_scores_raw(data, cp, cands)
    rec["dev_raw"] = dev_raw
    if kind == "concurrent":
        graph = C.GRAPHS[ns]
    else:
        graph = C.single_fault_graph(ns, sorted(set(C.svc_fixed(c) for c in cands)))
    rec.update(pagerank_rank(dev_raw, cands, graph))
    rec["t_pagerank"] = time.time() - t0
    rec["usable"] = True
    C.atomic_write_json(cache, rec)
    return rec


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    workers = int(os.environ.get("WORKERS", "8"))
    items = []
    if which in ("all", "concurrent"):
        gt = C.parse_ground_truth()
        for cid, info in gt.items():
            p = "%s/%s.csv" % (C.DATA_V2, cid)
            if os.path.exists(p):
                items.append({"kind": "concurrent", "case_id": cid, "path": C.portable(p), "namespace": info["namespace"],
                              "true_services": [info["svc_a"], info["svc_b"]],
                              "faults": [info["fault_a"], info["fault_b"]]})
    if which in ("all", "single"):
        for c in C.find_single_fault_cases():
            items.append({"kind": "single", "case_id": c["case_id"], "path": c["path"], "namespace": c["namespace"],
                          "true_services": [c["true_service"]], "faults": [c["fault"]]})
    os.makedirs(C.CACHE + "/baro", exist_ok=True)
    t_start = time.time()
    res = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process, it): it for it in items}
        for i, f in enumerate(as_completed(futs), 1):
            it = futs[f]
            try:
                res.append(f.result())
            except Exception as e:
                print("FAILED", it["case_id"], repr(e), flush=True)
            if i % 10 == 0 or i == len(items):
                print("  %d/%d done (%.0fs)" % (i, len(items), time.time() - t_start), flush=True)
    for kind in ("concurrent", "single"):
        sub = sorted([r for r in res if r["kind"] == kind], key=lambda r: r["case_id"])
        if sub:
            C.atomic_write_json("%s/precompute_%s.json" % (C.OUT, kind), sub)
            us = [r for r in sub if r.get("usable")]
            print("%s: %d cases, %d usable" % (kind, len(sub), len(us)))
            for r in sub:
                if not r.get("usable"):
                    print("   unusable:", r["case_id"], r.get("reason"))


if __name__ == "__main__":
    main()
