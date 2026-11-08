#!/usr/bin/env python3
"""Export per-case metrics for the network-delay cases: ../clean_collection/core/export_ext.py unchanged, plus one series.

Kept (export_ext.py): window = [start - 90 s, end + 180 s]; 5-s grid; the same PromQL per service
(cAdvisor cpu/memory/working set with rate[1m] on counters; Istio latency = rate(sum)/rate(count) and request rate,
reporter="destination", first returned series, as in the original); ffill/bfill; time column = seconds since window
start; epoch arithmetic; variants primary (Istio sampled every 30 s, held on the 5-s grid) and istio5s (native 5 s).
Targets = the paper's (core set): Boutique adservice, cartservice, checkoutservice, currencyservice,
productcatalogservice; Sock Shop catalogue, carts, payment.

Added: a sixth series per service, <svc>_istio_latency_src = caller-observed latency to the
service: sum(rate(istio_request_duration_milliseconds_sum{destination_service_name=svc,
destination_service_namespace=ns, reporter="source"}[1m])) / sum(rate(..._count{...}[1m])). It is summed over all
callers (the first-series rule would pick one arbitrary caller/response-code series). An egress delay on the faulted
pod is seen by its callers, not by the pod's own (destination-side) Envoy. Sampled like the other Istio series.
The column order is the five original series of each service followed by its _istio_latency_src, so dropping the
*_istio_latency_src columns gives exactly the original export layout.

Usage: python export_netdelay.py [--workdir DIR] [--force] [CASE_ID ...]   -> <workdir>/data_ext/{primary,istio5s}
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
PORT = 19094
SERVICES = {
    "boutique": ["adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice"],
    "sock-shop": ["catalogue", "carts", "payment"],
}
CONTAINER_METRICS = [
    ("container_cpu_usage_seconds_total", True),
    ("container_memory_usage_bytes", False),
    ("container_memory_working_set_bytes", False),
]
SUFFIXES = ["cpu_usage_seconds", "memory_usage_bytes", "memory_working_set_bytes", "istio_latency", "istio_requests",
            "istio_latency_src"]
MULTI = []


def query_range(q, start, end, step):
    u = f"http://127.0.0.1:{PORT}/api/v1/query_range?" + urllib.parse.urlencode(
        {"query": q, "start": start, "end": end, "step": step})
    for attempt in range(4):
        try:
            r = json.load(urllib.request.urlopen(u, timeout=60))
            res = r["data"]["result"]
            if not res:
                return None
            if len(res) > 1:
                MULTI.append(q[:90])
            vals = res[0]["values"]
            return pd.Series([float(v[1]) for v in vals], index=[int(round(float(v[0]))) - start for v in vals])
        except Exception as e:
            if attempt == 3:
                print(f"  QUERY FAILED: {q[:80]} -- {e}")
                return None
            time.sleep(2 + 3 * attempt)


def istio(q, start, end, variant):
    if variant == "istio5s":
        return query_range(q, start, end, 5)
    s = query_range(q, start, end, 30)
    if s is None:
        return None
    grid = list(range(0, end - start + 1, 5))
    return s.reindex(sorted(set(grid) | set(s.index))).ffill().reindex(grid)


def ratio(ls, lc):
    idx = ls.index.union(lc.index)
    lat = (ls.reindex(idx).ffill().bfill() / lc.reindex(idx).ffill().bfill()).replace([np.inf, -np.inf], np.nan)
    return lat.fillna(0)


def export_case(cid, info, variant, out_dir):
    ns = info["ns"]
    start, end = info["start"] - 90, info["end"] + 180
    cols = {}
    for svc in SERVICES[ns]:
        cname = "server" if ns == "boutique" else svc
        for m, counter in CONTAINER_METRICS:
            base = f'{m}{{namespace="{ns}", pod=~"{svc}.*", container="{cname}"}}'
            s = query_range(f"rate({base}[1m])" if counter else base, start, end, 5)
            if s is not None:
                cols[f"{svc}_{m.replace('container_', '').replace('_total', '')}"] = s
        ls = istio(f'rate(istio_request_duration_milliseconds_sum{{destination_service_name="{svc}", reporter="destination"}}[1m])', start, end, variant)
        lc = istio(f'rate(istio_request_duration_milliseconds_count{{destination_service_name="{svc}", reporter="destination"}}[1m])', start, end, variant)
        if ls is not None and lc is not None:
            cols[f"{svc}_istio_latency"] = ratio(ls, lc)
        rq = istio(f'rate(istio_requests_total{{destination_service_name="{svc}", reporter="destination"}}[1m])', start, end, variant)
        if rq is not None:
            cols[f"{svc}_istio_requests"] = rq
        sel = f'destination_service_name="{svc}", destination_service_namespace="{ns}", reporter="source"'
        ss = istio(f'sum(rate(istio_request_duration_milliseconds_sum{{{sel}}}[1m]))', start, end, variant)
        sc = istio(f'sum(rate(istio_request_duration_milliseconds_count{{{sel}}}[1m]))', start, end, variant)
        if ss is not None and sc is not None:
            cols[f"{svc}_istio_latency_src"] = ratio(ss, sc)
    if not cols:
        print(f"WARNING: no data for {cid}")
        return False
    idx = sorted(set().union(*[s.index for s in cols.values()]))
    rect = {}
    missing = []
    for svc in SERVICES[ns]:
        for suf in SUFFIXES:
            c = f"{svc}_{suf}"
            s = cols.get(c)
            if s is None:
                missing.append(c)
            rect[c] = pd.Series(0.0, index=idx) if s is None else s.reindex(idx).ffill().bfill().fillna(0.0)
    df = pd.DataFrame(rect).sort_index().ffill().bfill()
    df.insert(0, "time", df.index)
    df = df.reset_index(drop=True)
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, cid + ".csv.tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, os.path.join(out_dir, cid + ".csv"))
    return {"case": cid, "variant": variant, "rows": len(df), "missing": ";".join(missing)}


def parse_gt(path):
    cases = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.strip().split(",")
            if len(p) == 8 and p[0] != "case":
                cases.setdefault(p[0], {}).update({"ns": p[1], "start": int(p[7])})
            elif len(p) == 3 and p[1] == "end_time":
                cases.setdefault(p[0], {})["end"] = int(p[2])
    return cases


def main():
    args = sys.argv[1:]
    work = HERE
    if "--workdir" in args:
        i = args.index("--workdir"); work = os.path.abspath(args[i + 1]); del args[i:i + 2]
    force = "--force" in args
    only = set(a for a in args if a != "--force")
    with open(os.path.join(work, "cases_ext.json"), encoding="utf-8") as f:
        kinds = {c["id"]: c["kind"] for c in json.load(f)}
    with open(os.path.join(work, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    gt = parse_gt(os.path.join(work, "ground_truth_ext.csv"))
    todo = [(cid, info) for cid, info in gt.items()
            if "end" in info and state.get(cid, {}).get("status") == "DONE"
            and (cid in only if only else True)
            and time.time() > info["end"] + 200]
    pf = subprocess.Popen(["kubectl", "port-forward", "-n", "monitoring", "svc/prometheus-kube-prometheus-prometheus",
                           f"{PORT}:9090"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    log = []

    def one(item):
        cid, info = item
        res = []
        for variant in ("primary", "istio5s"):
            d = os.path.join(work, "data_ext", variant)
            if not force and os.path.exists(os.path.join(d, cid + ".csv")):
                continue
            r = export_case(cid, info, variant, d)
            if r:
                res.append(r)
        return cid, res

    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for i, (cid, res) in enumerate(ex.map(one, todo), 1):
                log.extend(res)
                print(f"[{i}/{len(todo)}] {cid} ({len(res)} written)", flush=True)
    finally:
        pf.terminate()
    out = os.path.join(work, "data_ext", f"export_log_{int(time.time())}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pd.DataFrame(log).to_csv(out, index=False)
    n_missing = sum(1 for r in log if r.get("missing"))
    print(f"exported {len(todo)} cases x 2 variants ({len(log)} files written, {n_missing} with a missing series); "
          f"queries with >1 series (first used, as in the original): {len(MULTI)}")


if __name__ == "__main__":
    main()
