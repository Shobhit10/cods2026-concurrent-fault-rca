"""
run_rq2_v2.py

Improved Grouped RobustScorer: replaces the rank-position distance proxy
with a genuine, scale-independent magnitude signal computed directly from
the raw data.

USAGE: python run_rq2_v2.py
"""

import pandas as pd
import numpy as np
import networkx as nx
from sklearn.cluster import DBSCAN
from cods_paths import CONCURRENT_DIR, GROUND_TRUTH, out_path
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


def compute_deviation_scores(data, anomaly_idx, candidates):
    """Replicates BARO's OWN internal robust_scorer formula exactly
    (confirmed via inspect.getsource(robust_scorer)): fit RobustScaler on
    the pre-anomaly window, transform the post-anomaly window, take the
    max |z-score| per column. This IS BARO's real signal, not a proxy."""
    from sklearn.preprocessing import RobustScaler
    import numpy as np

    normal_df = data.head(anomaly_idx)
    anomal_df = data.tail(len(data) - anomaly_idx)

    raw_scores = {}
    for col in candidates:
        if col not in data.columns:
            raw_scores[col] = 0.0
            continue
        a = normal_df[col].dropna().to_numpy()
        b = anomal_df[col].dropna().to_numpy()
        if len(a) < 2 or len(b) < 1:
            raw_scores[col] = 0.0
            continue
        try:
            scaler = RobustScaler().fit(a.reshape(-1, 1))
            zscores = scaler.transform(b.reshape(-1, 1))[:, 0]
            score = float(np.max(np.abs(zscores))) if len(zscores) else 0.0
        except Exception:
            score = 0.0
        raw_scores[col] = score

    max_score = max(raw_scores.values()) if raw_scores else 1.0
    if max_score == 0:
        max_score = 1.0
    normalized = {k: v / max_score for k, v in raw_scores.items()}
    return normalized


def cluster_candidates_v2(ranked_list, deviation_scores, graph, alpha=0.5, eps=0.3, min_samples=2):
    n = len(ranked_list)
    if n < 2:
        return {0: ranked_list}

    max_hops = graph.number_of_nodes()
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            dev_term = abs(deviation_scores.get(ranked_list[i], 0) - deviation_scores.get(ranked_list[j], 0))
            svc_i, svc_j = service_of(ranked_list[i]), service_of(ranked_list[j])
            hops = graph_hops(graph, svc_i, svc_j)
            graph_term = hops / max_hops
            D[i][j] = alpha * dev_term + (1 - alpha) * graph_term

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


def evaluate_case(case_id, namespace, true_services, data_folder=CONCURRENT_DIR, alpha=0.5, eps=0.3):
    path = f"{data_folder}/{case_id}.csv"
    if not os.path.exists(path):
        return None
    data = pd.read_csv(path)

    try:
        anomalies = bocpd(data)
    except Exception:
        return None
    if not anomalies or anomalies[0] is None:
        return None
    anomaly_idx = anomalies[0]

    try:
        result = robust_scorer(data, anomalies=anomalies)
        ranked = result["ranks"]
        candidates = result["node_names"]
    except Exception:
        return None

    deviation_scores = compute_deviation_scores(data, anomaly_idx, candidates)

    graph = GRAPHS[namespace]
    groups = cluster_candidates_v2(ranked, deviation_scores, graph, alpha=alpha, eps=eps)

    svc_to_group = {}
    for label, entries in groups.items():
        for svc in true_services:
            if any(e.startswith(f"{svc}_") for e in entries) and svc not in svc_to_group:
                svc_to_group[svc] = label

    real_labels = {svc: lbl for svc, lbl in svc_to_group.items() if not str(lbl).startswith("noise_")}
    separated = len(real_labels) == 2 and len(set(real_labels.values())) == 2

    grouped_hits = 0
    for svc, label in svc_to_group.items():
        if str(label).startswith("noise_"):
            continue
        group_entries = groups[label]
        if group_entries and group_entries[0].startswith(f"{svc}_"):
            grouped_hits += 1
    grouped_ac1 = grouped_hits / 2

    return {"case_id": case_id, "namespace": namespace,
            "num_groups": len(groups), "separated": separated, "grouped_ac1": grouped_ac1}


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
    df.to_csv(out_path("rq2_v2_results.csv"), index=False)

    print("\n=== RQ2 v2 Results: Magnitude-based Grouped RobustScorer ===\n")
    print(f"Cases evaluated: {len(df)}")
    print(f"Separation rate: {df['separated'].mean():.3f}")
    print(f"Grouped AC@1: {df['grouped_ac1'].mean():.3f}")

    print("\n--- By system ---")
    for ns in df["namespace"].unique():
        sub = df[df["namespace"] == ns]
        print(f"\n{ns} ({len(sub)} cases):")
        print(f"  Separation rate: {sub['separated'].mean():.3f}")
        print(f"  Grouped AC@1: {sub['grouped_ac1'].mean():.3f}")
