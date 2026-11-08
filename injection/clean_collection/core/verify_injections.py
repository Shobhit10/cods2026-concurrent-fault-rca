#!/usr/bin/env python3
"""Pre-declared post-run check: is every injected fault visible in Prometheus?

CPU fault visible  : rate(cpu[1m]) at t+50 s exceeds the floor by >= 0.05 cores.
Memory fault visible: working set at t+40 s exceeds the floor by >= 40 MiB.
Floor = minimum of the values at t-35, t-20, t-5, t+130 and t+150 s (neighbouring cases can overlap single points).
t = fault start: start (from ground_truth_ext.csv) for fault A, start + 15 s for fault B.

Usage: python verify_injections.py            -> writes injection_check.csv and prints a summary
Needs KUBECONFIG; opens its own port-forward to the in-cluster Prometheus.
"""
import csv, json, os, subprocess, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
PORT = 19091
CPU_MIN, MEM_MIN_MIB = 0.05, 40.0


def q(expr, t):
    u = f"http://127.0.0.1:{PORT}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": t})
    r = json.load(urllib.request.urlopen(u, timeout=30))
    v = [float(x["value"][1]) for x in r["data"]["result"]]
    return sum(v) if v else None


def expr(ns, svc, fault):
    c = "server" if ns == "boutique" else svc
    sel = f'namespace="{ns}",container="{c}",pod=~"{svc}-.*"'
    if fault == "cpu":
        return f"sum(rate(container_cpu_usage_seconds_total{{{sel}}}[1m]))"
    return f"sum(container_memory_working_set_bytes{{{sel}}})/1048576"


def check(ns, svc, fault, t0):
    e = expr(ns, svc, fault)
    during = q(e, t0 + (50 if fault == "cpu" else 40))
    base = [x for x in (q(e, t0 + d) for d in (-35, -20, -5, 130, 150)) if x is not None]
    if during is None or not base:
        return None, during, None
    b = min(base)
    delta = during - b
    return delta >= (CPU_MIN if fault == "cpu" else MEM_MIN_MIB), during, b


def main():
    with open(os.path.join(HERE, "cases_ext.json"), encoding="utf-8") as f:
        cases = {c["id"]: c for c in json.load(f)}
    with open(os.path.join(HERE, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    now = time.time()
    pf = subprocess.Popen(["kubectl", "port-forward", "-n", "monitoring", "svc/prometheus-kube-prometheus-prometheus",
                           f"{PORT}:9090"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)
    rows = []
    todo = []
    for cid, st in state.items():
        c = cases.get(cid)
        if not c or st.get("status") != "DONE" or "start" not in st or now - st["start"] < 200:
            continue
        todo.append((cid, c, st))

    def one(item):
        cid, c, st = item
        faults = [(c["svc_a"], c["fault_a"], st["start"])]
        if c.get("svc_b"):
            faults.append((c["svc_b"], c["fault_b"], st["start"] + 15))
        res = [check(c["ns"], s, f, t) for s, f, t in faults]
        ok = all(r[0] for r in res)
        row = {"case": cid, "kind": c["kind"], "ns": c["ns"], "visible_all": ok}
        for tag, (s, f, _), (v, d, b) in zip("ab", faults, res):
            row.update({f"svc_{tag}": s, f"fault_{tag}": f, f"visible_{tag}": v,
                        f"during_{tag}": None if d is None else round(d, 4),
                        f"base_{tag}": None if b is None else round(b, 4)})
        return row

    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            rows = list(ex.map(one, todo))
    finally:
        pf.terminate()
    keys = ["case", "kind", "ns", "visible_all", "svc_a", "fault_a", "visible_a", "during_a", "base_a",
            "svc_b", "fault_b", "visible_b", "during_b", "base_b"]
    out = os.path.join(HERE, "injection_check.csv")
    with open(out + ".tmp", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})
    os.replace(out + ".tmp", out)
    real = [r for r in rows if r["kind"] != "smoke"]
    bad = [r["case"] for r in real if not r["visible_all"]]
    print(f"checked {len(real)} non-smoke cases; all faults visible in {len(real) - len(bad)}; not visible: {len(bad)}")
    for b in bad:
        print("  NOT VISIBLE:", b)


if __name__ == "__main__":
    main()
