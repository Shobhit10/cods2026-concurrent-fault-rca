"""
run_crossval_parallel.py

Rigorous 5-fold cross-validated evaluation, with the expensive precompute
step (bocpd + robust_scorer per case) parallelized across CPU cores --
same pattern as run_rq3_v2_parallel.py. The fold/tuning logic itself runs
on the cached results and is fast, so it stays sequential.

For each fold: alpha/eps are tuned ONLY on the other 4 folds, then
applied to the held-out fold. No case ever contributes to tuning the
parameters it is then scored with.

USAGE: python run_crossval_parallel.py
"""

import pandas as pd
import numpy as np
import glob
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from run_rq2_v2 import GRAPHS, compute_deviation_scores, cluster_candidates_v2
from cods_paths import BARO_DATA_DIR, GROUND_TRUTH, concurrent_csv, out_path
from baro.anomaly_detection import bocpd
from baro.root_cause_analysis import robust_scorer

ALPHAS = [0.3, 0.5, 0.7]
EPSS = [0.1, 0.15, 0.2, 0.3, 0.4]
N_FOLDS = 5
SEED = 42


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


def find_single_fault_cases(base_dir, namespace_key):
    cases = []
    for combo_dir in glob.glob(f"{base_dir}/*"):
        combo_name = os.path.basename(combo_dir)
        parts = combo_name.rsplit("_", 1)
        if len(parts) != 2:
            continue
        true_service, fault_type = parts
        for rep_dir in glob.glob(f"{combo_dir}/*"):
            data_path = os.path.join(rep_dir, "simple_data.csv")
            if os.path.exists(data_path):
                cases.append({"path": data_path, "true_service": true_service, "namespace": namespace_key})
    return cases


# ---- Worker functions: self-contained, so they can run in separate processes ----

def precompute_concurrent(item):
    case_id, info = item
    path = concurrent_csv(case_id)
    if not os.path.exists(path):
        return None
    data = pd.read_csv(path)
    try:
        anomalies = bocpd(data)
        if not anomalies or anomalies[0] is None:
            return None
        result = robust_scorer(data, anomalies=anomalies)
        ranked = result["ranks"]
        candidates = result["node_names"]
        dev_scores = compute_deviation_scores(data, anomalies[0], candidates)
    except Exception:
        return None
    return {
        "case_id": case_id, "namespace": info["namespace"],
        "true_services": [info["svc_a"], info["svc_b"]],
        "ranked": ranked, "dev_scores": dev_scores,
    }


def precompute_single_fault(case):
    data = pd.read_csv(case["path"])
    try:
        anomalies = bocpd(data)
        if not anomalies or anomalies[0] is None:
            return None
        result = robust_scorer(data, anomalies=anomalies)
        ranked = result["ranks"]
        candidates = result["node_names"]
        dev_scores = compute_deviation_scores(data, anomalies[0], candidates)
    except Exception:
        return None
    return {
        "namespace": case["namespace"], "true_service": case["true_service"],
        "ranked": ranked, "dev_scores": dev_scores,
    }


def run_parallel(worker_fn, items, label, num_workers):
    results = []
    start = time.time()
    completed = 0
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(worker_fn, item): item for item in items}
        for future in as_completed(futures):
            completed += 1
            if completed % 10 == 0 or completed == len(items):
                print(f"  [{label} {completed}/{len(items)}] ({time.time() - start:.0f}s elapsed)")
            r = future.result()
            if r:
                results.append(r)
    print(f"  {label}: {len(results)}/{len(items)} succeeded in {time.time() - start:.0f}s")
    return results


# ---- Scoring functions (fast, run on cached precomputed results) ----

def score_concurrent(cases, alpha, eps):
    results = []
    for c in cases:
        groups = cluster_candidates_v2(c["ranked"], c["dev_scores"], GRAPHS[c["namespace"]], alpha=alpha, eps=eps)
        svc_to_group = {}
        for label, entries in groups.items():
            for svc in c["true_services"]:
                if any(e.startswith(f"{svc}_") for e in entries) and svc not in svc_to_group:
                    svc_to_group[svc] = label
        real_labels = {s: l for s, l in svc_to_group.items() if not str(l).startswith("noise_")}
        separated = len(real_labels) == 2 and len(set(real_labels.values())) == 2
        hits = 0
        for svc, label in svc_to_group.items():
            if str(label).startswith("noise_"):
                continue
            if groups[label] and groups[label][0].startswith(f"{svc}_"):
                hits += 1
        results.append({"separated": separated, "grouped_ac1": hits / 2})
    return pd.DataFrame(results)


def score_single_fault(cases, alpha, eps):
    results = []
    for c in cases:
        groups = cluster_candidates_v2(c["ranked"], c["dev_scores"], GRAPHS[c["namespace"]], alpha=alpha, eps=eps)
        real_groups = [g for label, g in groups.items() if not str(label).startswith("noise_")]
        single_group = len(real_groups) <= 1
        hit = 0
        for label, entries in groups.items():
            if str(label).startswith("noise_"):
                continue
            if entries and entries[0].startswith(f"{c['true_service']}_"):
                hit = 1
                break
        results.append({"single_group": single_group, "hit": hit})
    return pd.DataFrame(results)


def make_folds(items, n_folds, seed):
    rng = random.Random(seed)
    shuffled = items[:]
    rng.shuffle(shuffled)
    folds = [[] for _ in range(n_folds)]
    for i, item in enumerate(shuffled):
        folds[i % n_folds].append(item)
    return folds


if __name__ == "__main__":
    num_workers = min(8, os.cpu_count() or 4)
    print(f"Using {num_workers} parallel workers (detected {os.cpu_count()} CPU cores)\n")

    print("=== Step 1: Precomputing bocpd + robust_scorer (parallel) ===")
    concurrent_cases_raw = list(parse_ground_truth().items())
    concurrent_precomputed = run_parallel(precompute_concurrent, concurrent_cases_raw, "concurrent", num_workers)

    single_fault_cases_raw = (
        find_single_fault_cases(os.path.join(BARO_DATA_DIR, "fse-ob"), "boutique")
        + find_single_fault_cases(os.path.join(BARO_DATA_DIR, "fse-ss"), "sock-shop")
    )
    single_fault_precomputed = run_parallel(precompute_single_fault, single_fault_cases_raw, "single-fault", num_workers)

    print(f"\n=== Step 2: {N_FOLDS}-fold cross-validation (fast, sequential, cached data) ===")
    conc_folds = make_folds(concurrent_precomputed, N_FOLDS, SEED)
    sf_folds = make_folds(single_fault_precomputed, N_FOLDS, SEED)

    fold_results = []
    for fold_i in range(N_FOLDS):
        print(f"\n--- Fold {fold_i + 1}/{N_FOLDS} ---")
        conc_test = conc_folds[fold_i]
        conc_train = [c for j, f in enumerate(conc_folds) if j != fold_i for c in f]
        sf_test = sf_folds[fold_i]
        sf_train = [c for j, f in enumerate(sf_folds) if j != fold_i for c in f]

        best_score, best_alpha, best_eps = -1, None, None
        for alpha in ALPHAS:
            for eps in EPSS:
                conc_df = score_concurrent(conc_train, alpha, eps)
                sf_df = score_single_fault(sf_train, alpha, eps)
                if len(conc_df) == 0 or len(sf_df) == 0:
                    continue
                combined = (conc_df["separated"].mean() + sf_df["single_group"].mean()) / 2
                if combined > best_score:
                    best_score, best_alpha, best_eps = combined, alpha, eps

        print(f"  Best on training folds: alpha={best_alpha}, eps={best_eps} (train combined score={best_score:.3f})")

        conc_test_df = score_concurrent(conc_test, best_alpha, best_eps)
        sf_test_df = score_single_fault(sf_test, best_alpha, best_eps)

        fold_results.append({
            "fold": fold_i + 1, "alpha": best_alpha, "eps": best_eps,
            "concurrent_separation": conc_test_df["separated"].mean() if len(conc_test_df) else np.nan,
            "concurrent_grouped_ac1": conc_test_df["grouped_ac1"].mean() if len(conc_test_df) else np.nan,
            "single_fault_single_group": sf_test_df["single_group"].mean() if len(sf_test_df) else np.nan,
            "single_fault_hit_rate": sf_test_df["hit"].mean() if len(sf_test_df) else np.nan,
            "n_concurrent_test": len(conc_test_df), "n_single_fault_test": len(sf_test_df),
        })
        print(f"  Held-out fold results: {fold_results[-1]}")

    results_df = pd.DataFrame(fold_results)
    results_df.to_csv(out_path("crossval_results.csv"), index=False)

    print("\n" + "=" * 60)
    print("FINAL CROSS-VALIDATED RESULTS (mean +/- std across 5 held-out folds)")
    print("=" * 60)
    for metric in ["concurrent_separation", "concurrent_grouped_ac1", "single_fault_single_group", "single_fault_hit_rate"]:
        mean = results_df[metric].mean()
        std = results_df[metric].std()
        print(f"{metric}: {mean:.3f} +/- {std:.3f}")

    print(f"\nAlpha/eps selected per fold: {list(zip(results_df['alpha'], results_df['eps']))}")
    print("\nFull fold-by-fold results saved to crossval_results.csv")
