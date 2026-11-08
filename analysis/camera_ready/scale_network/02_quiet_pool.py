"""Step 2 (BARO environment). QUIET noise pool for the noise-floor scale model.

A service far from both faults is, to the scorer, just a healthy series. We measure what the paper's scorer
(BARO robust_scorer, same preprocessing, same max-of-robust-z statistic) gives a healthy service by running it
on the fault-free part of every case: the rows recorded before the first injection (time < 90 s, 18 rows at 5 s).
That window is split into a reference half and a test half (placebo change point). Every instrumented service is
healthy there, including the two services that are injected later, so each case contributes 5 (Online Boutique)
or 3 (Sock Shop) healthy service vectors.

Caveat (documented in RESULTS_SCALE.md): the placebo windows (9+9 rows; sensitivity 12+6) are shorter than the
real reference/test windows (19-55 / 3-39 rows). A shorter test window lowers the max statistic, a shorter
reference window makes the IQR noisier and raises it; net direction is not fixed, so both splits are reported.

Run:  python 02_quiet_pool.py   (environment of requirements.txt)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONC_DIR, OUT, atomic_write_csv, baro_scores, entry_service, services_from_cols

FAULT_T = 90  # seconds after export start (paper: export starts 90 s before the first fault)
SPLITS = {"9+9": 9, "12+6": 12}


def main():
    summ = pd.read_csv(os.path.join(OUT, "cods_case_summary.csv"))
    ok = summ[summ.status == "ok"]
    rows = []
    for _, c in ok.iterrows():
        data = pd.read_csv(os.path.join(CONC_DIR, f"{c.case_id}.csv"))
        pre = data[data["time"] < FAULT_T].reset_index(drop=True)
        assert len(pre) == 18, (c.case_id, len(pre))
        services = sorted(services_from_cols([x for x in data.columns if x != "time"]))
        for name, split in SPLITS.items():
            for e, s in baro_scores(pre, split_row=split):
                svc = entry_service(e, services)
                rows.append({"case_id": c.case_id, "ns": c.ns, "split": name, "service": svc,
                             "entry": e, "metric": e[len(svc) + 1:], "score": s,
                             "later_role": "cpu_cause" if svc == c.cpu_svc else
                             ("mem_cause" if svc == c.mem_svc else "non_cause")})
    df = pd.DataFrame(rows)
    atomic_write_csv(df, os.path.join(OUT, "quiet_pool_scores.csv"))
    for (ns, sp), g in df.groupby(["ns", "split"]):
        top = g.groupby(["case_id", "service"]).score.max()
        print(f"{ns:9s} {sp:5s} vectors={len(top):3d} entries={len(g):4d} "
              f"service-max score: median={top.median():.2f} p75={top.quantile(.75):.2f} p90={top.quantile(.9):.2f}")


if __name__ == "__main__":
    main()
