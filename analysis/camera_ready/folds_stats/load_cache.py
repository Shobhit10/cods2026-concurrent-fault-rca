"""load_cache.py -- loads raw/cases/*.json written by precompute.py into tidy pandas tables."""
import sys
sys.dont_write_bytecode = True
import glob
import json
import os

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def load_records(prefix):
    recs = []
    for f in sorted(glob.glob(os.path.join(C.RAW, "cases", f"{prefix}__*.json"))):
        with open(f) as fh:
            recs.append(json.load(fh))
    return recs


def concurrent_tables():
    """Returns (all_records, per-case DataFrame of usable cases, per-case x grid outcomes DataFrame)."""
    recs = load_records("conc")
    gt_order = list(C.parse_ground_truth().keys())
    recs.sort(key=lambda r: gt_order.index(r["case_id"]))
    rows, grid_rows = [], []
    for r in recs:
        if r.get("status") != "ok":
            continue
        truth = [r["svc_a"], r["svc_b"]]
        ranked = r["ranked"]
        h = {k: C.hits_at_k(ranked, truth, k) for k in (1, 2, 3, 5)}
        row = {
            "case_id": r["case_id"], "namespace": r["namespace"], "pair": r["pair"], "rep": r["rep"],
            "svc_cpu": r["svc_a"], "svc_mem": r["svc_b"],
            "ac1": h[1] / 2, "ac2": h[2] / 2, "ac3": h[3] / 2, "ac5": h[5] / 2,
            "hits2": h[2],
            "both2": int(h[2] == 2), "both3": int(h[3] == 2), "both5": int(h[5] == 2), "any5": int(h[5] >= 1),
            "rank_cpu": r["rank_a"], "rank_mem": r["rank_b"], "n_ranked": r["n_ranked"],
            "both_in_input": int(r["rank_a"] is not None and r["rank_b"] is not None),
        }
        rn = r.get("ranked_nsigma")
        if rn:
            hn = {k: C.hits_at_k(rn, truth, k) for k in (1, 2, 3, 5)}
            row.update({"ns_ac2": hn[2] / 2, "ns_both2": int(hn[2] == 2), "ns_both5": int(hn[5] == 2),
                        "ns_any5": int(hn[5] >= 1), "ns_ac1": hn[1] / 2, "ns_ac3": hn[3] / 2, "ns_ac5": hn[5] / 2})
        rows.append(row)
        for a, e in C.GRID:
            g = r["grid"][f"{a}_{e}"]
            grid_rows.append({"case_id": r["case_id"], "alpha": a, "eps": e,
                              "separated": int(g["separated"]), "grouped_ac1": g["grouped_ac1"]})
    return recs, pd.DataFrame(rows), pd.DataFrame(grid_rows)


def single_tables():
    recs = load_records("sf")
    recs.sort(key=lambda r: r["sf_id"])
    rows, grid_rows = [], []
    for r in recs:
        if r.get("status") != "ok":
            continue
        rows.append({
            "sf_id": r["sf_id"], "namespace": r["namespace"], "combo": r["combo"],
            "true_service": r["true_service"], "fault_type": r["fault_type"],
            "flat_ac1": r["flat_ac1"], "true_rank": r["true_rank"], "n_ranked": r["n_ranked"],
            "v1_single_group": int(r["v1_0.5_0.3"]["single_group"]),
        })
        for a, e in C.GRID:
            g = r["grid"][f"{a}_{e}"]
            grid_rows.append({"sf_id": r["sf_id"], "alpha": a, "eps": e,
                              "single_group": int(g["single_group"]), "hit": int(g["hit"])})
    return recs, pd.DataFrame(rows), pd.DataFrame(grid_rows)
