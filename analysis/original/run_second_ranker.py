"""
run_second_ranker.py

Runs the SAME pipeline as run_rq1.py (BARO bocpd change point) on every
concurrent case, but scores each case with TWO scorers:
  - robust_scorer  (median / IQR)      -- BARO, "ours"
  - nsigma         (mean / std)        -- non-robust second ranker

For each scorer it reports AC@1/2/3/5, both@k (both true causes in top k),
and any@5, overall and per benchmark. This tests whether the both@k ceiling
is a property of the ranking paradigm or specific to robust scoring.

Also writes rankings_robust.csv (per-case top-10 ranked entries with a
true-cause flag) for building the case-study figure.

Run from the project folder with baro-env active:
  python run_second_ranker.py
"""

import pandas as pd
import os
from cods_paths import GROUND_TRUTH, concurrent_csv, out_path
from baro.anomaly_detection import bocpd
from baro.root_cause_analysis import robust_scorer, nsigma


def parse_ground_truth(path=GROUND_TRUTH):
    cases = {}
    with open(path) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) == 8:
                case_id, namespace, svc_a, fault_a, svc_b, fault_b, stagger, start_time = parts
                cases.setdefault(case_id, {})
                cases[case_id].update({"namespace": namespace, "svc_a": svc_a, "svc_b": svc_b})
    return cases


def hits_at_k(ranked_list, true_services, k):
    top_k = ranked_list[:k]
    hits = 0
    for svc in true_services:
        if any(entry.startswith(f"{svc}_") for entry in top_k):
            hits += 1
    return hits


def metrics_from_ranked(ranked, true_services):
    h = {k: hits_at_k(ranked, true_services, k) for k in (1, 2, 3, 5)}
    return {
        "ac1": h[1] / 2, "ac2": h[2] / 2, "ac3": h[3] / 2, "ac5": h[5] / 2,
        "both2": 1.0 if h[2] == 2 else 0.0,
        "both3": 1.0 if h[3] == 2 else 0.0,
        "both5": 1.0 if h[5] == 2 else 0.0,
        "any5": 1.0 if h[5] >= 1 else 0.0,
    }


def run():
    cases = parse_ground_truth()
    rows = []
    ranking_rows = []

    for case_id, info in cases.items():
        path = concurrent_csv(case_id)
        if not os.path.exists(path):
            continue
        true_services = [info["svc_a"], info["svc_b"]]
        data = pd.read_csv(path)

        try:
            anomalies = bocpd(data)
        except Exception as e:
            print(f"  {case_id}: bocpd failed ({e})")
            continue
        if not anomalies or anomalies[0] is None:
            continue

        try:
            r_robust = robust_scorer(data, anomalies=anomalies)["ranks"]
            r_nsigma = nsigma(data, anomalies=anomalies)["ranks"]
        except Exception as e:
            print(f"  {case_id}: scoring failed ({e})")
            continue

        mr = metrics_from_ranked(r_robust, true_services)
        mn = metrics_from_ranked(r_nsigma, true_services)
        mr.update({"case_id": case_id, "namespace": info["namespace"], "scorer": "robust"})
        mn.update({"case_id": case_id, "namespace": info["namespace"], "scorer": "nsigma"})
        rows.append(mr)
        rows.append(mn)

        for rank, entry in enumerate(r_robust[:10], start=1):
            svc = entry.split("_")[0]
            is_cause = any(entry.startswith(f"{s}_") for s in true_services)
            ranking_rows.append({"case_id": case_id, "rank": rank, "entry": entry,
                                 "is_true_cause": int(is_cause)})

    df = pd.DataFrame(rows)
    df.to_csv(out_path("second_ranker_percase.csv"), index=False)
    pd.DataFrame(ranking_rows).to_csv(out_path("rankings_robust.csv"), index=False)

    cols = ["ac1", "ac2", "ac3", "ac5", "both2", "both3", "both5", "any5"]

    def summarize(sub, label):
        n = len(sub)
        means = {c: sub[c].mean() for c in cols}
        print(f"{label:16s} n={n:2d}  "
              f"AC@1={means['ac1']:.3f} AC@2={means['ac2']:.3f} AC@3={means['ac3']:.3f} AC@5={means['ac5']:.3f}  "
              f"both@2={means['both2']:.3f} both@3={means['both3']:.3f} both@5={means['both5']:.3f} any@5={means['any5']:.3f}")

    for scorer in ("robust", "nsigma"):
        s = df[df["scorer"] == scorer]
        print(f"\n===== {scorer.upper()} =====")
        summarize(s, "overall")
        summarize(s[s["namespace"] == "boutique"], "boutique")
        summarize(s[s["namespace"] == "sock-shop"], "sock-shop")

    print("\nWrote second_ranker_percase.csv and rankings_robust.csv")


if __name__ == "__main__":
    run()
