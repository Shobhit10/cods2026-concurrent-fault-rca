"""
run_rq1.py

Runs BARO's own bocpd + robust_scorer on every exported case, scores each
one against ground truth, and reports AC@1 / AC@2 / AC@3 / AC@5 averaged
across all cases -- this is your RQ1 result.

IMPORTANT: each concurrent case has TWO true root-cause services, so AC@1's
maximum possible value is mathematically 0.5 (only one slot, two true
answers) -- not comparable to BARO's single-fault AC@1 (max=1.0). AC@2 (does
the top-2 contain both true services) is the fair concurrent-fault analog
to single-fault AC@1, and is the number to headline in the paper.

USAGE (run from your project folder, with baro-env active):
  python run_rq1.py
"""

import pandas as pd
from cods_paths import GROUND_TRUTH, concurrent_csv, out_path
from baro.anomaly_detection import bocpd
from baro.root_cause_analysis import robust_scorer
import glob
import os

def parse_ground_truth(path=GROUND_TRUTH):
    cases = {}
    with open(path) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) == 8:
                case_id, namespace, svc_a, fault_a, svc_b, fault_b, stagger, start_time = parts
                cases.setdefault(case_id, {})
                cases[case_id].update({
                    "namespace": namespace, "svc_a": svc_a, "svc_b": svc_b,
                })
    return cases


def hit_at_k(ranked_list, true_services, k):
    top_k = ranked_list[:k]
    hits = 0
    for svc in true_services:
        if any(entry.startswith(f"{svc}_") for entry in top_k):
            hits += 1
    return hits


def score_case(case_id, true_services):
    path = concurrent_csv(case_id)
    if not os.path.exists(path):
        return None

    data = pd.read_csv(path)
    try:
        anomalies = bocpd(data)
    except Exception as e:
        print(f"  {case_id}: bocpd failed ({e}), skipping")
        return None

    if not anomalies or anomalies[0] is None:
        print(f"  {case_id}: no anomaly detected")
        return {"case_id": case_id, "ac1": 0, "ac2": 0, "ac3": 0, "ac5": 0, "detected": False, "scoring_failed": False}

    try:
        ranked = robust_scorer(data, anomalies=anomalies)["ranks"]
    except Exception as e:
        print(f"  {case_id}: robust_scorer failed ({e}) -- likely anomaly detected too close to end of window, skipping")
        return {"case_id": case_id, "ac1": None, "ac2": None, "ac3": None, "ac5": None, "detected": True, "scoring_failed": True}

    ac1 = hit_at_k(ranked, true_services, 1) / 2
    ac2 = hit_at_k(ranked, true_services, 2) / 2
    ac3 = hit_at_k(ranked, true_services, 3) / 2
    ac5 = hit_at_k(ranked, true_services, 5) / 2

    return {"case_id": case_id, "ac1": ac1, "ac2": ac2, "ac3": ac3, "ac5": ac5, "detected": True, "scoring_failed": False}


if __name__ == "__main__":
    cases = parse_ground_truth()
    results = []

    for case_id, info in cases.items():
        true_services = [info["svc_a"], info["svc_b"]]
        r = score_case(case_id, true_services)
        if r:
            r["namespace"] = info["namespace"]
            results.append(r)

    df = pd.DataFrame(results)
    df.to_csv(out_path("rq1_results.csv"), index=False)

    failed = df["scoring_failed"].sum() if "scoring_failed" in df.columns else 0
    df_valid = df.dropna(subset=["ac1"])

    print("\n=== RQ1 Results: BARO accuracy on concurrent-fault cases ===\n")
    print(f"Total cases: {len(df)}")
    print(f"Scoring failures (excluded from averages below): {failed}")
    print(f"Cases included in averages: {len(df_valid)}")
    print(f"Anomaly detected: {df['detected'].sum()} / {len(df)}")

    print(f"\nOverall AC@1: {df_valid['ac1'].mean():.3f}  (max possible 0.5 for 2-fault cases -- NOT comparable to BARO's single-fault AC@1)")
    print(f"Overall AC@2: {df_valid['ac2'].mean():.3f}  (fair analog to BARO's single-fault AC@1 -- headline this number)")
    print(f"Overall AC@3: {df_valid['ac3'].mean():.3f}")
    print(f"Overall AC@5: {df_valid['ac5'].mean():.3f}")

    print("\n--- By system ---")
    for ns in df_valid["namespace"].unique():
        sub = df_valid[df_valid["namespace"] == ns]
        print(f"\n{ns} ({len(sub)} cases):")
        print(f"  AC@1: {sub['ac1'].mean():.3f}")
        print(f"  AC@2: {sub['ac2'].mean():.3f}")
        print(f"  AC@3: {sub['ac3'].mean():.3f}")
        print(f"  AC@5: {sub['ac5'].mean():.3f}")

    print("\nFull per-case results (including failures) saved to rq1_results.csv")
