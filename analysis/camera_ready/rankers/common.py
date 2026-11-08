"""
common.py -- shared helpers for the multi-ranker analysis (Table 2).

Python 3.8-compatible (RCD runs in RCAEval's py3.8 env-rcd).
All data is READ-ONLY; every write goes to ../outputs via atomic_write_*.

The clustering stage below is a verbatim copy of cluster_candidates_v2 /
score_concurrent / score_single_fault from the released code
(analysis/original/run_rq2_v2.py and run_crossval_parallel.py), with ONE
optional, clearly-labelled change: the function used to map a metric entry
to its service (`svc_fn`). The released code uses entry.rsplit("_", 1)[0],
which is correct for the single-fault column names ("cartservice_cpu") but
NOT for the concurrent data_v2 names ("cartservice_cpu_usage_seconds" ->
"cartservice_cpu_usage", a node that is not in the call graph). We run both
the released mapping ("paper") and a suffix-aware mapping ("fixed").
"""

import json
import os
import glob
import math

import numpy as np
import networkx as nx

# Paths (repository layout by default; override with environment variables).
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
DATA_DIR = os.environ.get("CODS_DATA_DIR", os.path.join(REPO, "data"))
DATA_V2 = os.environ.get("CODS_CONCURRENT_DIR", os.path.join(DATA_DIR, "concurrent"))
GT_PATH = os.environ.get("CODS_GROUND_TRUTH", os.path.join(DATA_DIR, "ground_truth_log.csv"))
BARO_DATA = os.environ.get("BARO_DATA_DIR", os.path.join(REPO, "external", "baro_data"))
SINGLE_DIRS = {
    "boutique": BARO_DATA + "/fse-ob",
    "sock-shop": BARO_DATA + "/fse-ss",
}
CR_RESULTS = os.environ.get("CODS_CR_RESULTS", os.path.join(DATA_DIR, "results", "camera_ready"))
OUT = os.environ.get("CODS_RANKERS_OUT", os.path.join(CR_RESULTS, "rankers"))
CACHE = OUT + "/cache"
FOLDS_CASES = os.path.join(CR_RESULTS, "folds_stats", "raw", "cases")

# Data paths are stored in the output JSON files in a portable form ("{CONCURRENT}/<case>.csv",
# "{BARO_DATA}/fse-ob/<combo>/<rep>/simple_data.csv") and resolved against the paths above when read.
_PATH_TAGS = (("{CONCURRENT}", DATA_V2), ("{BARO_DATA}", BARO_DATA))


def portable(path):
    for tag, root in _PATH_TAGS:
        if path.startswith(root):
            return tag + path[len(root):].replace(os.sep, "/")
    return path


def resolve(path):
    for tag, root in _PATH_TAGS:
        if path.startswith(tag):
            return root + path[len(tag):]
    return path

ALPHA = 0.7
EPS = 0.4
ALPHAS = [0.3, 0.5, 0.7]
EPSS = [0.1, 0.15, 0.2, 0.3, 0.4]

V2_SUFFIXES = ("_cpu_usage_seconds", "_memory_usage_bytes", "_memory_working_set_bytes",
               "_istio_latency", "_istio_requests")


# ------------------------------------------------------------------ io
def atomic_write_text(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, indent=1, default=_json_default))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(str(type(o)))


def read_json(path):
    with open(path) as f:
        return json.load(f)


# ------------------------------------------------------------------ cases
def parse_ground_truth(path=GT_PATH):
    """Identical to the released parse_ground_truth (8-field lines only)."""
    cases = {}
    with open(path) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) == 8:
                case_id, namespace, svc_a, fault_a, svc_b, fault_b, stagger, start_time = parts
                cases.setdefault(case_id, {})
                cases[case_id].update({"namespace": namespace, "svc_a": svc_a, "svc_b": svc_b,
                                       "fault_a": fault_a, "fault_b": fault_b})
    return cases


def find_single_fault_cases():
    """Identical traversal to the released find_single_fault_cases, sorted for determinism."""
    out = []
    for ns, base_dir in SINGLE_DIRS.items():
        for combo_dir in sorted(glob.glob(base_dir + "/*")):
            combo = os.path.basename(combo_dir)
            parts = combo.rsplit("_", 1)
            if len(parts) != 2:
                continue
            true_service, fault_type = parts
            for rep_dir in sorted(glob.glob(combo_dir + "/*")):
                p = os.path.join(rep_dir, "simple_data.csv")
                if os.path.exists(p):
                    out.append({"case_id": "%s__%s__%s" % (ns, combo, os.path.basename(rep_dir)),
                                "path": portable(p), "true_service": true_service, "fault": fault_type,
                                "namespace": ns})
    return out


# ------------------------------------------------------------------ services
def svc_fixed(entry):
    """Suffix-aware service of a metric column (correct for data_v2 and fse names)."""
    for suf in V2_SUFFIXES:
        if entry.endswith(suf):
            return entry[: -len(suf)]
    return entry.rsplit("_", 1)[0]


def svc_paper(entry):
    """The released code's service_of (run_rq2_v2.py)."""
    return entry.rsplit("_", 1)[0]


SVC_FNS = {"paper": svc_paper, "fixed": svc_fixed}


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


# ------------------------------------------------------------------ deviation (Eq. dev)
def dev_scores_raw(data, anomaly_idx, candidates):
    """compute_deviation_scores from run_rq2_v2.py WITHOUT the final max-normalisation."""
    from sklearn.preprocessing import RobustScaler
    normal_df = data.head(anomaly_idx)
    anomal_df = data.tail(len(data) - anomaly_idx)
    raw = {}
    for col in candidates:
        if col not in data.columns:
            raw[col] = 0.0
            continue
        a = normal_df[col].dropna().to_numpy()
        b = anomal_df[col].dropna().to_numpy()
        if len(a) < 2 or len(b) < 1:
            raw[col] = 0.0
            continue
        try:
            scaler = RobustScaler().fit(a.reshape(-1, 1))
            z = scaler.transform(b.reshape(-1, 1))[:, 0]
            raw[col] = float(np.max(np.abs(z))) if len(z) else 0.0
        except Exception:
            raw[col] = 0.0
    return raw


def normalise_like_paper(raw):
    """Same normalisation as compute_deviation_scores: divide by the per-case max."""
    m = max(raw.values()) if raw else 1.0
    if m == 0:
        m = 1.0
    return {k: v / m for k, v in raw.items()}


# ------------------------------------------------------------------ ranking metrics
def hits_at_k(ranked, true_services, k):
    """Released definition (run_second_ranker.py): a cause is hit if any of its metric entries is in the top k."""
    top = ranked[:k]
    return sum(1 for s in true_services if any(e.startswith(s + "_") for e in top))


def conc_rank_metrics(ranked, true_services):
    h = {k: hits_at_k(ranked, true_services, k) for k in (1, 2, 3, 5, 10)}
    hn = hits_at_k(ranked, true_services, len(ranked))
    return {
        "ac1": h[1] / 2.0, "ac2": h[2] / 2.0, "ac3": h[3] / 2.0, "ac5": h[5] / 2.0,
        "both2": float(h[2] == 2), "both3": float(h[3] == 2), "both5": float(h[5] == 2),
        "both10": float(h[10] == 2), "any5": float(h[5] >= 1),
        "both_all": float(hn == 2), "list_len": len(ranked),
        "rank_a": first_rank(ranked, true_services[0]), "rank_b": first_rank(ranked, true_services[1]),
    }


def first_rank(ranked, svc):
    for i, e in enumerate(ranked):
        if e.startswith(svc + "_"):
            return i + 1
    return None


def single_rank_metrics(ranked, true_service):
    r = first_rank(ranked, true_service)
    out = {"list_len": len(ranked), "rank_true": r}
    for k in (1, 3, 5):
        out["ac%d" % k] = float(r is not None and r <= k)
    return out


def service_level_list(ranked, svc_fn=svc_fixed):
    seen, out = set(), []
    for e in ranked:
        s = svc_fn(e)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def svc_list_metrics(svc_ranked, true_services):
    def hk(k):
        top = set(svc_ranked[:k])
        return sum(1 for s in true_services if s in top)
    h = {k: hk(k) for k in (1, 2, 3, 5)}
    return {"svc_ac1": h[1] / 2.0, "svc_ac2": h[2] / 2.0, "svc_ac3": h[3] / 2.0,
            "svc_both2": float(h[2] == 2), "svc_both3": float(h[3] == 2), "svc_both5": float(h[5] == 2),
            "svc_any1": float(h[1] >= 1), "svc_any2": float(h[2] >= 1), "svc_any5": float(h[5] >= 1),
            "svc_list_len": len(svc_ranked)}


# ------------------------------------------------------------------ random-ranking expectations (exact)
def _comb(n, k):
    if k < 0 or n < 0 or k > n:
        return 0
    return math.comb(n, k) if hasattr(math, "comb") else math.factorial(n) // (math.factorial(k) * math.factorial(n - k))


def random_conc_expectation(candidates, true_services):
    n = len(candidates)
    m = [sum(1 for e in candidates if e.startswith(s + "_")) for s in true_services]
    out = {}
    for k in (1, 2, 3, 5, 10):
        kk = min(k, n)
        tot = _comb(n, kk)
        pa_abs = _comb(n - m[0], kk) / tot
        pb_abs = _comb(n - m[1], kk) / tot
        pab_abs = _comb(n - m[0] - m[1], kk) / tot
        p_both = 1 - pa_abs - pb_abs + pab_abs
        out["ac%d" % k] = ((1 - pa_abs) + (1 - pb_abs)) / 2.0
        out["both%d" % k] = p_both
        out["any%d" % k] = 1 - pab_abs
    out["any5"] = out["any5"]
    out["both_all"] = float(m[0] > 0 and m[1] > 0)
    out["list_len"] = n
    return out


def random_single_expectation(candidates, true_service):
    n = len(candidates)
    m = sum(1 for e in candidates if e.startswith(true_service + "_"))
    out = {"list_len": n}
    for k in (1, 3, 5):
        kk = min(k, n)
        out["ac%d" % k] = 1 - _comb(n - m, kk) / _comb(n, kk)
    return out


def random_svc_expectation(candidates, true_services, svc_fn=None):
    """Uniformly random order of the candidate SERVICES (service-level list), exact."""
    svc_fn = svc_fn or svc_fixed
    S = sorted(set(svc_fn(c) for c in candidates))
    n = len(S)
    t = sum(1 for s in true_services if s in S)
    out = {"svc_list_len": n}
    for k in (1, 2, 3, 5):
        kk = min(k, n)
        tot = _comb(n, kk)
        p_in = kk / n                                   # one given service in a random top-k
        p_none = _comb(n - t, kk) / tot
        p_both = (_comb(n - 2, kk - 2) / tot) if t == 2 else 0.0
        out["svc_ac%d" % k] = t * p_in / 2.0
        out["svc_both%d" % k] = p_both
        out["svc_any%d" % k] = 1 - p_none
    return out


def clopper_pearson(k, n, conf=0.95):
    from scipy.stats import beta
    a = 1 - conf
    lo = 0.0 if k == 0 else float(beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a / 2, k + 1, n - k))
    return [lo, hi]


# ------------------------------------------------------------------ the clustering stage (released code)
def graph_hops(graph, svc_a, svc_b):
    if svc_a == svc_b:
        return 0
    try:
        return nx.shortest_path_length(graph, svc_a, svc_b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return graph.number_of_nodes()


def cluster_candidates_v2(ranked_list, deviation_scores, graph, alpha=0.5, eps=0.3, min_samples=2,
                          svc_fn=svc_paper):
    """Verbatim cluster_candidates_v2 except that service_of is the injectable svc_fn."""
    from sklearn.cluster import DBSCAN
    n = len(ranked_list)
    if n < 2:
        return {0: ranked_list}
    max_hops = graph.number_of_nodes()
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            dev_term = abs(deviation_scores.get(ranked_list[i], 0) - deviation_scores.get(ranked_list[j], 0))
            svc_i, svc_j = svc_fn(ranked_list[i]), svc_fn(ranked_list[j])
            hops = graph_hops(graph, svc_i, svc_j)
            graph_term = hops / max_hops
            D[i][j] = alpha * dev_term + (1 - alpha) * graph_term
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed").fit_predict(D)
    groups = {}
    noise_counter = 1000
    for i, label in enumerate(labels):
        if label == -1:
            groups["noise_%d" % noise_counter] = [ranked_list[i]]
            noise_counter += 1
        else:
            groups.setdefault(label, []).append(ranked_list[i])
    return groups


def score_concurrent_case(groups, true_services):
    """Verbatim per-case logic of score_concurrent (run_crossval_parallel.py)."""
    svc_to_group = {}
    for label, entries in groups.items():
        for svc in true_services:
            if any(e.startswith(svc + "_") for e in entries) and svc not in svc_to_group:
                svc_to_group[svc] = label
    real_labels = {s: l for s, l in svc_to_group.items() if not str(l).startswith("noise_")}
    separated = len(real_labels) == 2 and len(set(real_labels.values())) == 2
    hits = 0
    for svc, label in svc_to_group.items():
        if str(label).startswith("noise_"):
            continue
        if groups[label] and groups[label][0].startswith(svc + "_"):
            hits += 1
    n_real = len([1 for l in groups if not str(l).startswith("noise_")])
    return {"separated": float(separated), "grouped_ac1": hits / 2.0, "n_groups_real": n_real}


def score_single_case(groups, true_service):
    """Verbatim per-case logic of score_single_fault (run_crossval_parallel.py)."""
    real_groups = [g for label, g in groups.items() if not str(label).startswith("noise_")]
    single_group = len(real_groups) <= 1
    hit = 0
    for label, entries in groups.items():
        if str(label).startswith("noise_"):
            continue
        if entries and entries[0].startswith(true_service + "_"):
            hit = 1
            break
    return {"single_group": float(single_group), "hit": float(hit), "n_groups_real": len(real_groups)}


def single_fault_graph(namespace, services):
    """Paper graph plus isolated nodes for instrumented services the paper graph omits (PageRank only)."""
    G = GRAPHS[namespace].copy()
    for s in services:
        if s not in G:
            G.add_node(s)
    return G
