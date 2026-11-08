#!/usr/bin/env python3
"""Pre-declared post-run check: is every injected fault visible in Prometheus?

CPU fault visible   : rate(cpu[1m]) at t+50 s exceeds the floor by >= 0.05 cores            (as in the core set)
Memory fault visible: working set at t+40 s exceeds the floor by >= 40 MiB                   (as in the core set)
Delay visible       : caller-observed latency to the faulted service (Istio reporter="source", all callers:
                      sum(rate(..._sum[1m])) / sum(rate(..._count[1m])), in ms) at t+50 s exceeds the floor by
                      >= DELAY_MIN_MS (100 ms, one third of the injected 300 ms).
Floor = minimum of the values at t-35, t-20, t-5, t+130 and t+150 s.
t = fault start: start (from ground_truth_ext.csv) for fault A, start + 15 s for fault B.
For the delay, the row also records the destination-reported latency (reporter="destination") at the same times and
the caller-observed latency at t+150 s (after removal), for the report; they do not decide visibility.

Usage: python verify_netdelay.py [--workdir DIR]   -> <workdir>/injection_check.csv and a printed summary
Needs KUBECONFIG; opens its own port-forward to the in-cluster Prometheus.
"""
import csv, json, os, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
PORT = 19093
CPU_MIN, MEM_MIN_MIB, DELAY_MIN_MS = 0.05, 40.0, 100.0
FLOOR_T = (-35, -20, -5, 130, 150)


def q(expr, t):
    u = f"http://127.0.0.1:{PORT}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": t})
    for attempt in range(3):
        try:
            r = json.load(urllib.request.urlopen(u, timeout=30))
            v = [float(x["value"][1]) for x in r["data"]["result"]]
            v = [x for x in v if x == x]  # drop NaN (0/0 when a service had no requests)
            return sum(v) if v else None
        except Exception:  # noqa: BLE001
            if attempt == 2:
                return None
            time.sleep(2)


def lat_expr(ns, svc, reporter):
    sel = f'destination_service_name="{svc}",destination_service_namespace="{ns}",reporter="{reporter}"'
    return (f"sum(rate(istio_request_duration_milliseconds_sum{{{sel}}}[1m]))"
            f" / sum(rate(istio_request_duration_milliseconds_count{{{sel}}}[1m]))")


def expr(ns, svc, fault):
    if fault == "delay":
        return lat_expr(ns, svc, "source")
    c = "server" if ns == "boutique" else svc
    sel = f'namespace="{ns}",container="{c}",pod=~"{svc}-.*"'
    if fault == "cpu":
        return f"sum(rate(container_cpu_usage_seconds_total{{{sel}}}[1m]))"
    return f"sum(container_memory_working_set_bytes{{{sel}}})/1048576"


def check(ns, svc, fault, t0):
    e = expr(ns, svc, fault)
    during = q(e, t0 + (40 if fault == "mem" else 50))
    base = [x for x in (q(e, t0 + d) for d in FLOOR_T) if x is not None]
    extra = {}
    if fault == "delay":
        d = lat_expr(ns, svc, "destination")
        dbase = [x for x in (q(d, t0 + k) for k in FLOOR_T) if x is not None]
        extra = {"after_150": q(e, t0 + 150), "pre_5": q(e, t0 - 5), "dest_during": q(d, t0 + 50),
                 "dest_floor": min(dbase) if dbase else None}
    if during is None or not base:
        return None, during, None, extra
    b = min(base)
    thr = {"cpu": CPU_MIN, "mem": MEM_MIN_MIB, "delay": DELAY_MIN_MS}[fault]
    return during - b >= thr, during, b, extra


def main():
    work = os.path.abspath(sys.argv[sys.argv.index("--workdir") + 1]) if "--workdir" in sys.argv else HERE
    with open(os.path.join(work, "cases_ext.json"), encoding="utf-8") as f:
        cases = {c["id"]: c for c in json.load(f)}
    with open(os.path.join(work, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    now = time.time()
    pf = subprocess.Popen(["kubectl", "port-forward", "-n", "monitoring", "svc/prometheus-kube-prometheus-prometheus",
                           f"{PORT}:9090"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    todo = []
    for cid, st in state.items():
        c = cases.get(cid)
        if not c or st.get("status") != "DONE" or "start" not in st or now - st["start"] < 200:
            continue
        todo.append((cid, c, st))

    def one(item):
        cid, c, st = item
        faults = [(c["svc_a"], c["fault_a"], st["start"]), (c["svc_b"], c["fault_b"], st["start"] + 15)]
        res = [check(c["ns"], s, f, t) for s, f, t in faults]
        ok = all(r[0] for r in res)
        row = {"case": cid, "kind": c["kind"], "arm": c.get("arm"), "ns": c["ns"], "visible_all": ok}
        for tag, (s, f, _), (v, d, b, ex) in zip("ab", faults, res):
            row.update({f"svc_{tag}": s, f"fault_{tag}": f, f"visible_{tag}": v,
                        f"during_{tag}": None if d is None else round(d, 4),
                        f"base_{tag}": None if b is None else round(b, 4)})
            if f == "delay":
                row.update({f"delay_{k}": None if v2 is None else round(v2, 3) for k, v2 in ex.items()})
        return row

    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            rows = list(ex.map(one, todo))
    finally:
        pf.terminate()
    keys = ["case", "kind", "arm", "ns", "visible_all", "svc_a", "fault_a", "visible_a", "during_a", "base_a",
            "svc_b", "fault_b", "visible_b", "during_b", "base_b",
            "delay_pre_5", "delay_after_150", "delay_dest_during", "delay_dest_floor"]
    out = os.path.join(work, "injection_check.csv")
    with open(out + ".tmp", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["case"]):
            w.writerow({k: r.get(k) for k in keys})
    os.replace(out + ".tmp", out)
    real = [r for r in rows if r["kind"] != "smoke"]
    bad = [r["case"] for r in real if not r["visible_all"]]
    print(f"checked {len(rows)} cases ({len(real)} non-smoke); all faults visible in {len(rows) - len([r for r in rows if not r['visible_all']])}"
          f"; non-smoke not visible: {len(bad)}")
    for r in rows:
        if not r["visible_all"]:
            print("  NOT VISIBLE:", r["case"], {k: r.get(k) for k in ("visible_a", "during_a", "base_a", "visible_b", "during_b", "base_b")})


if __name__ == "__main__":
    main()
