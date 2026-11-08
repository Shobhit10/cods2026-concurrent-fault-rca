"""
run_faulttype_analysis.py

Deeper analysis on the 28 concurrent cases using the SAME pipeline as
run_rq1.py (bocpd + robust_scorer). Reports, all from real data:
  - change-point detection rate
  - per-fault-type recall@k (is the CPU-faulted cause / the memory-faulted
    cause inside the top k), which exposes any asymmetry between fault types
  - the rank distribution of true causes, and how often the second (worse-
    ranked) true cause is buried beyond the top five -- the mechanism behind
    the both@5 ceiling.

Run with baro-env active:  python run_faulttype_analysis.py
"""

import pandas as pd
import numpy as np
import os
from cods_paths import GROUND_TRUTH, concurrent_csv, out_path
from baro.anomaly_detection import bocpd
from baro.root_cause_analysis import robust_scorer


def parse_gt(path=GROUND_TRUTH):
    cases = {}
    with open(path) as f:
        for line in f:
            p = line.strip().split(",")
            if len(p) == 8:
                cid, ns, sa, fa, sb, fb, stg, st = p
                cpu = sa if fa == "cpu" else sb
                mem = sb if fb == "mem" else sa
                cases[cid] = {"ns": ns, "cpu": cpu, "mem": mem}
    return cases


def first_rank(ranked, svc):
    for i, e in enumerate(ranked):
        if e.startswith(svc + "_"):
            return i + 1
    return None


def main():
    cases = parse_gt()
    rows = []
    detected = 0
    total = 0
    ac2_hits = 0
    for cid, info in cases.items():
        path = concurrent_csv(cid)
        if not os.path.exists(path):
            continue
        total += 1
        data = pd.read_csv(path)
        try:
            anom = bocpd(data)
        except Exception:
            continue
        if not anom or anom[0] is None:
            continue
        detected += 1
        try:
            ranked = robust_scorer(data, anomalies=anom)["ranks"]
        except Exception:
            continue
        r_cpu = first_rank(ranked, info["cpu"])
        r_mem = first_rank(ranked, info["mem"])
        # AC@2 sanity: hits in top-2 / 2
        top2 = ranked[:2]
        hits2 = sum(1 for s in (info["cpu"], info["mem"]) if any(e.startswith(s + "_") for e in top2))
        ac2_hits += hits2 / 2
        rows.append({"cid": cid, "ns": info["ns"], "r_cpu": r_cpu, "r_mem": r_mem, "n": len(ranked)})

    df = pd.DataFrame(rows)
    n = len(df)
    print(f"change-point detected: {detected}/{total}")
    print(f"usable cases: {n}")
    print(f"AC@2 sanity (should be 0.232): {ac2_hits / n:.3f}")

    print("\n--- per-fault-type recall@k (fraction of cases with that cause in top k) ---")
    for k in (1, 2, 3, 5):
        rc = (df["r_cpu"].fillna(9999) <= k).mean()
        rm = (df["r_mem"].fillna(9999) <= k).mean()
        print(f"recall@{k}:  CPU-cause={rc:.3f}   MEM-cause={rm:.3f}")

    found = [x for x in list(df["r_cpu"]) + list(df["r_mem"]) if pd.notna(x)]
    print(f"\ntrue-cause rank: median={np.median(found):.0f}  mean={np.mean(found):.1f}  "
          f"(found in list {len(found)}/{2*n})")

    better, worse = [], []
    for _, r in df.iterrows():
        rc = r["r_cpu"] if pd.notna(r["r_cpu"]) else 999
        rm = r["r_mem"] if pd.notna(r["r_mem"]) else 999
        better.append(min(rc, rm))
        worse.append(max(rc, rm))
    worse_beyond5 = sum(1 for x in worse if x > 5)
    print(f"better-ranked cause: median rank={np.median(better):.0f}")
    print(f"worse-ranked cause:  median rank={np.median([w for w in worse if w < 999]) if any(w<999 for w in worse) else float('nan'):.0f}, "
          f"beyond top-5 in {worse_beyond5}/{n} cases ({worse_beyond5/n:.0%})")

    df.to_csv(out_path("faulttype_ranks.csv"), index=False)
    print("\nwrote faulttype_ranks.csv")


if __name__ == "__main__":
    main()
