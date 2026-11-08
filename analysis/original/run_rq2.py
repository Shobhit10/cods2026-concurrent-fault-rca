"""
run_rq2.py

Implements the Grouped RobustScorer extension: takes BARO's flat ranked
list and splits it into separate groups using DBSCAN, based on a distance
combining (a) how close two candidates are in rank position, and (b) how
far apart their services are in the real service-dependency graph.

Reports:
  - separation_rate: fraction of cases where the two true root-cause
    services ended up in DIFFERENT, REAL (non-noise) clusters
  - grouped_ac1: for each true service, is it the #1 ranked entry WITHIN
    its own REAL cluster? Noise/singleton points score 0 -- they don't
    represent a meaningful grouping, just an unclustered leftover point.

USAGE: python run_rq2.py
"""

import pandas as pd
import networkx as nx
from sklearn.cluster import DBSCAN
import numpy as np
from cods_paths import GROUND_TRUTH, concurrent_csv, out_path
from baro.anomaly_detection import bocpd
from baro.root_cause_analysis import robust_scorer
import os

def build_boutique_graph():
    G = nx.Graph()
    G.add_edges_from([
        ("frontend", "adservice"), ("frontend", "cartservice"),
        ("frontend", "checkoutservice"), ("frontend", "currencyservice"),
        ("frontend", "productcatalogservice"),
        ("checkoutservice", "cartservice"), ("checkoutservice", "currencyservice"),
        ("checkoutservice", "productcatalogservice"),
    ])
    return G

def build_sockshop_graph():
    G = nx.Graph()
    G.add_edges_from([
        ("front-end", "catalogue"), ("front-end", "carts"),
        ("front-end", "orders"), ("front-end", "user"),
        ("orders", "payment"), ("orders", "carts"), ("orders", "user"),
    ])
    return G

GRAPHS = {"boutique": build_boutique_graph(), "sock-shop": build_sockshop_graph()}


def service_of(entry):
    return entry.rsplit("_", 1)[0]


def graph_hops(graph, svc_a, svc_b):
    if svc_a == svc_b:
        return 0
    try:
        return nx.shortest_path_length(graph, svc_a, svc_b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return graph.number_of_nodes()


def cluster_candidates(ranked_list, graph, alpha=0.5, eps=0.3, min_samples=2):
    n = len(ranked_list)
    if n < 2:
        return {0: ranked_list}

    max_hops = graph.number_of_nodes()
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            rank_term = abs(i - j) / n
            svc_i, svc_j = service_of(ranked_list[i]), service_of(ranked_list[j])
            hops = graph_hops(graph, svc_i, svc_j)
            graph_term = hops / max_hops
            D[i][j] = alpha * rank_term + (1 - alpha) * graph_term

    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed").fit_predict(D)
    groups = {}
    noise_counter = 1000
    for i, label in enumerate(labels):
        if label == -1:
            groups[f"noise_{noise_counter}"] = [ranked_list[i]]
            noise_counter += 1
        else:
            groups.setdefault(label, []).append(ranked_list[i])
    return groups


def evaluate_case(case_id, namespace, true_services, alpha=0.5, eps=0.3):
    path = concurrent_csv(case_id)
    if not os.path.exists(path):
        return None
    data = pd.read_csv(path)

    try:
        anomalies = bocpd(data)
    except Exception:
        return None
    if not anomalies or anomalies[0] is None:
        return None

    try:
        ranked = robust_scorer(data, anomalies=anomalies)["ranks"]
    except Exception:
        return None

    graph = GRAPHS[namespace]
    groups = cluster_candidates(ranked, graph, alpha=alpha, eps=eps)

    svc_to_group = {}
    for label, entries in groups.items():
        for svc in true_services:
            if any(e.startswith(f"{svc}_") for e in entries) and svc not in svc_to_group:
                svc_to_group[svc] = label

    real_labels = {svc: lbl for svc, lbl in svc_to_group.items() if not str(lbl).startswith("noise_")}
    separated = (
        len(real_labels) == 2 and
        len(set(real_labels.values())) == 2
    )

    grouped_hits = 0
    for svc, label in svc_to_group.items():
        if str(label).startswith("noise_"):
            continue
        group_entries = groups[label]
        if group_entries and group_entries[0].startswith(f"{svc}_"):
            grouped_hits += 1
    grouped_ac1 = grouped_hits / 2

    return {
        "case_id": case_id, "namespace": namespace,
        "num_groups": len(groups), "separated": separated,
        "grouped_ac1": grouped_ac1,
    }


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


if __name__ == "__main__":
    cases = parse_ground_truth()
    results = []
    for case_id, info in cases.items():
        r = evaluate_case(case_id, info["namespace"], [info["svc_a"], info["svc_b"]])
        if r:
            results.append(r)

    df = pd.DataFrame(results)
    df.to_csv(out_path("rq2_results.csv"), index=False)

    print("\n=== RQ2 Results: Grouped RobustScorer ===\n")
    print(f"Cases evaluated: {len(df)}")
    print(f"\nSeparation rate (both true services in DIFFERENT, REAL clusters): {df['separated'].mean():.3f}")
    print(f"Grouped AC@1 (true service is #1 within its own REAL cluster, noise=0): {df['grouped_ac1'].mean():.3f}")

    print("\n--- By system ---")
    for ns in df["namespace"].unique():
        sub = df[df["namespace"] == ns]
        print(f"\n{ns} ({len(sub)} cases):")
        print(f"  Separation rate: {sub['separated'].mean():.3f}")
        print(f"  Grouped AC@1: {sub['grouped_ac1'].mean():.3f}")

    print("\nFull per-case results saved to rq2_results.csv")
