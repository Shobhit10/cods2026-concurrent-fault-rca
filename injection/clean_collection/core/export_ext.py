#!/usr/bin/env python3
"""Export per-case metrics from Prometheus: the export logic of the first collection, two variants.

Kept from the first collection's export script:
  window = [start - 90 s, end + 180 s]; 5-s grid; the same PromQL per service (cAdvisor cpu/memory/working set with
  rate[1m] on counters; Istio latency = rate(sum)/rate(count) and request rate, reporter="destination"); the first
  returned series is used, as in the original; the rectangular schema of 5 columns per service; ffill/bfill; time
  column = seconds since window start.
Changed:
  * epoch arithmetic instead of naive utcfromtimestamp(...).timestamp(), which is only correct when the local time
    zone is UTC (the original ran on Linux; this machine is IST);
  * Sock Shop exports the 5 services used by the extension pairs (the original exported 3: catalogue, carts, payment);
  * two variants: primary  = Istio series sampled every 30 s and held on the 5-s grid (Istio was scraped every 30 s on
    19 Aug and every 5 s now); istio5s = all series at the native 5-s step (sensitivity).
Usage: python export_ext.py [--force] [CASE_ID ...]  (KUBECONFIG set; opens its own port-forward)
       -> data_ext/primary, data_ext/istio5s. Existing files are skipped unless --force; 6 cases in parallel.
"""
import csv, json, os, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
PORT = 19092
SERVICES = {
    "boutique": ["adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice"],
    "sock-shop": ["catalogue", "carts", "payment", "user", "orders"],
}
CONTAINER_METRICS = [
    ("container_cpu_usage_seconds_total", True),
    ("container_memory_usage_bytes", False),
    ("container_memory_working_set_bytes", False),
]
SUFFIXES = ["cpu_usage_seconds", "memory_usage_bytes", "memory_working_set_bytes", "istio_latency", "istio_requests"]
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
            idx = ls.index.union(lc.index)
            lat = (ls.reindex(idx).ffill().bfill() / lc.reindex(idx).ffill().bfill()).replace([np.inf, -np.inf], np.nan)
            cols[f"{svc}_istio_latency"] = lat.fillna(0)
        rq = istio(f'rate(istio_requests_total{{destination_service_name="{svc}", reporter="destination"}}[1m])', start, end, variant)
        if rq is not None:
            cols[f"{svc}_istio_requests"] = rq
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
    force = "--force" in sys.argv
    only = set(a for a in sys.argv[1:] if a != "--force")
    with open(os.path.join(HERE, "cases_ext.json"), encoding="utf-8") as f:
        kinds = {c["id"]: c["kind"] for c in json.load(f)}
    with open(os.path.join(HERE, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    gt = parse_gt(os.path.join(HERE, "ground_truth_ext.csv"))
    todo = [(cid, info) for cid, info in gt.items()
            if "end" in info and state.get(cid, {}).get("status") == "DONE"
            and (cid in only if only else kinds.get(cid) != "smoke")
            and time.time() > info["end"] + 200]
    pf = subprocess.Popen(["kubectl", "port-forward", "-n", "monitoring", "svc/prometheus-kube-prometheus-prometheus",
                           f"{PORT}:9090"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)
    log = []

    def one(item):
        cid, info = item
        base = "data_ext_smoke" if kinds.get(cid) == "smoke" else "data_ext"
        res = []
        for variant in ("primary", "istio5s"):
            d = os.path.join(HERE, base, variant)
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
                print(f"[{i}/{len(todo)}] {cid} ({len(res)} written)")
    finally:
        pf.terminate()
    out = os.path.join(HERE, "data_ext_smoke" if only else "data_ext", f"export_log_{int(time.time())}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pd.DataFrame(log).to_csv(out, index=False)
    print(f"exported {len(todo)} cases x 2 variants; queries with >1 series (first used, as in the original): {len(MULTI)}")


if __name__ == "__main__":
    main()
