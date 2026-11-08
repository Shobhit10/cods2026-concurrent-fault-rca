"""Shared helpers: paths, crash-safe writes, BARO-identical scoring with scores exposed."""
import os
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
DATA = os.environ.get("CODS_DATA_DIR", os.path.join(REPO, "data"))
OUT = os.environ.get("CODS_SCALE_OUT", os.path.join(DATA, "results", "camera_ready", "scale_network"))

# Read-only inputs (never written).
CONC_DIR = os.environ.get("CODS_CONCURRENT_DIR", os.path.join(DATA, "concurrent"))
GT_PATH = os.environ.get("CODS_GROUND_TRUTH", os.path.join(DATA, "ground_truth_log.csv"))
PUB = os.environ.get("CODS_PUBLISHED_RESULTS", os.path.join(DATA, "results", "original"))


def atomic_write_text(path, text):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=os.path.basename(path))
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_csv(df, path):
    atomic_write_text(path, df.to_csv(index=False, lineterminator="\n"))


def baro_scores(data, split_row=None, inject_time=None):
    """Re-implements baro.root_cause_analysis.robust_scorer (DataFrame path) line for line,
    but returns (entry, score) pairs instead of names only. Caller verifies the order
    against BARO's own output."""
    from baro.root_cause_analysis import preprocess
    from sklearn.preprocessing import RobustScaler

    if split_row is not None:
        normal_df = data.head(split_row)
        anomal_df = data.tail(len(data) - split_row)
    else:
        normal_df = data[data["time"] < inject_time]
        anomal_df = data[data["time"] >= inject_time]
    normal_df = preprocess(data=normal_df, dataset=None, dk_select_useful=False)
    anomal_df = preprocess(data=anomal_df, dataset=None, dk_select_useful=False)
    inter = [x for x in normal_df.columns if x in anomal_df.columns]
    normal_df, anomal_df = normal_df[inter], anomal_df[inter]
    out = []
    for col in normal_df.columns:
        a = normal_df[col].to_numpy()
        b = anomal_df[col].to_numpy()
        sc = RobustScaler().fit(a.reshape(-1, 1))
        z = sc.transform(b.reshape(-1, 1))[:, 0]
        out.append((col, float(max(z))))
    return sorted(out, key=lambda x: x[1], reverse=True)


def entry_service(entry, services):
    best = None
    for s in services:
        if entry == s or entry.startswith(s + "_"):
            if best is None or len(s) > len(best):
                best = s
    return best


def first_rank(ranked_entries, svc, services):
    for i, e in enumerate(ranked_entries):
        if entry_service(e, services) == svc:
            return i + 1
    return None


def entry_metrics(ranked_entries, causes, services):
    """Paper convention (Eq. 2-4): pi is the metric-entry list, svc(pi_1:k) its services."""
    def svc_topk(k):
        return {entry_service(e, services) for e in ranked_entries[:k]}
    r = {}
    for k in (1, 2, 3, 5):
        top = svc_topk(k)
        h = sum(1 for c in causes if c in top)
        r[f"ac{k}"] = h / len(causes)
        r[f"both{k}"] = float(h == len(causes))
    r["any5"] = float(sum(1 for c in causes if c in svc_topk(5)) >= 1)
    return r


def service_ranking(ranked_entries, services):
    seen = []
    for e in ranked_entries:
        s = entry_service(e, services)
        if s and s not in seen:
            seen.append(s)
    return seen


def comb_ratio_both(N, k):
    """Random service ranking: P(both of 2 causes in top k of N) = C(N-2,k-2)/C(N,k) = k(k-1)/(N(N-1))."""
    if k < 2 or N < 2:
        return 0.0
    if k >= N:
        return 1.0
    return k * (k - 1) / (N * (N - 1))


def random_entry_both(N, m, k):
    """Random metric-entry ranking, m entries per service: P(each cause has >=1 entry in top k of mN)."""
    from math import comb
    T = m * N
    if k >= T:
        return 1.0
    tot = comb(T, k)
    none_a = comb(T - m, k)
    none_ab = comb(T - 2 * m, k) if T - 2 * m >= k else 0
    return 1 - 2 * none_a / tot + none_ab / tot


SERVICE_SUFFIXES = [
    "cpu_usage_seconds", "memory_usage_bytes", "memory_working_set_bytes", "cpu_throttling",
    "latency_p50", "latency_p90", "latency_p95", "latency_p99",
    "istio_requests", "istio_errors", "istio_latency", "tcp_received", "tcp_sent", "tcp_connections",
    "fs_writes_bytes", "net_pkt_dropped",
]


def services_from_cols(cols):
    svcs = set()
    for c in cols:
        for suf in SERVICE_SUFFIXES:
            if c.endswith("_" + suf):
                svcs.add(c[: -(len(suf) + 1)])
                break
    return svcs


def parse_gt_pairs(path):
    """8-field rows: case_id, ns, svc_a, fault_a, svc_b, fault_b, stagger, start."""
    cases = {}
    with open(path) as f:
        for line in f:
            p = line.strip().split(",")
            if len(p) == 8 and p[1] != "end_time":
                cid, ns, sa, fa, sb, fb, stg, st = p
                cases[cid] = {"ns": ns, "svc_a": sa, "fault_a": fa, "svc_b": sb, "fault_b": fb,
                              "stagger": stg, "start": st}
    return cases


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))
