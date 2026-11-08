"""Step 1 (BARO environment). Re-run the paper's exact pipeline (BARO bocpd + robust_scorer) on the
28 concurrent CPU+memory cases in the read-only CODS artifact, and export every metric entry's
deviation score so the scale model can be calibrated on it.

Checks: per-case r_cpu, r_mem, n must equal faulttype_ranks.csv; Both@2=0.071, Both@5=0.321,
AC@2=0.232 must be reproduced.

Run:  python 01_extract_cods_scores.py   (environment of requirements.txt)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CONC_DIR, GT_PATH, PUB, OUT, atomic_write_csv, baro_scores, entry_metrics, entry_service,
                    first_rank, services_from_cols)
from baro.anomaly_detection import bocpd
from baro.root_cause_analysis import robust_scorer


def parse_gt(path):
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


def main():
    cases = parse_gt(GT_PATH)
    rows, crow = [], []
    for cid, info in cases.items():
        path = os.path.join(CONC_DIR, f"{cid}.csv")
        if not os.path.exists(path):
            continue
        data = pd.read_csv(path)
        anom = bocpd(data)
        if not anom or anom[0] is None:
            crow.append({"case_id": cid, "status": "no_cp"})
            continue
        try:
            ranked = robust_scorer(data, anomalies=anom)["ranks"]
        except Exception as e:  # the two cases excluded in the paper
            crow.append({"case_id": cid, "status": f"scorer_failed: {type(e).__name__}"})
            continue
        scored = baro_scores(data, split_row=anom[0])
        assert [e for e, _ in scored] == list(ranked), f"score replica mismatch in {cid}"
        services = sorted(services_from_cols([c for c in data.columns if c != "time"]))
        r_cpu = first_rank(ranked, info["cpu"], services)
        r_mem = first_rank(ranked, info["mem"], services)
        m = entry_metrics(ranked, [info["cpu"], info["mem"]], services)
        crow.append({"case_id": cid, "ns": info["ns"], "status": "ok", "cp_row": anom[0],
                     "n_entries": len(ranked), "n_services": len(services),
                     "cpu_svc": info["cpu"], "mem_svc": info["mem"], "r_cpu": r_cpu, "r_mem": r_mem, **m})
        for i, (e, s) in enumerate(scored):
            svc = entry_service(e, services)
            role = "cpu_cause" if svc == info["cpu"] else ("mem_cause" if svc == info["mem"] else "non_cause")
            rows.append({"case_id": cid, "ns": info["ns"], "rank": i + 1, "entry": e, "service": svc,
                         "metric": e[len(svc) + 1:], "score": s, "role": role})

    ent = pd.DataFrame(rows)
    cs = pd.DataFrame(crow)
    atomic_write_csv(ent, os.path.join(OUT, "cods_entry_scores.csv"))
    atomic_write_csv(cs, os.path.join(OUT, "cods_case_summary.csv"))

    ok = cs[cs.status == "ok"].copy()
    ref = pd.read_csv(os.path.join(PUB, "faulttype_ranks.csv"))
    mg = ok.merge(ref, left_on="case_id", right_on="cid", suffixes=("", "_ref"))
    same = ((mg.r_cpu == mg.r_cpu_ref) & (mg.r_mem == mg.r_mem_ref) & (mg.n_entries == mg.n)).all()
    print(f"usable cases: {len(ok)} / {len(cs)}   excluded: {cs[cs.status != 'ok'][['case_id','status']].values.tolist()}")
    print(f"per-case ranks identical to faulttype_ranks.csv: {same} ({len(mg)} matched)")
    for k in ("ac2", "both2", "both3", "both5", "any5"):
        print(f"  {k}: {ok[k].mean():.3f}")
    for ns, g in ok.groupby("ns"):
        print(f"  {ns}: n={len(g)} both2={g.both2.mean():.3f} both5={g.both5.mean():.3f} "
              f"services={sorted(g.n_services.unique())} entries={g.n_entries.min()}-{g.n_entries.max()}")


if __name__ == "__main__":
    main()
