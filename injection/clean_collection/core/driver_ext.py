#!/usr/bin/env python3
"""Fault-injection driver for the concurrent cases. Resumable; one stream per application, run in parallel.

Mirrors the fault commands of the first collection:
CPU = busy loop for 60 s; memory = 60 MB written to /dev/shm, held 60 s, removed;
second fault 15 s after the first; 100 s wait after each case. Distroless boutique services (cartservice,
checkoutservice, productcatalogservice) are faulted via the per-node debug pods + crictl exec + busybox, as in the
original; their CPU loop is bounded with `timeout 60` (the original never put a CPU fault on a distroless service).

CPU command fix (made after the smoke test, before any counted case): the Sock Shop images ship BusyBox
v1.24.2, whose `timeout` only accepts `timeout -t SECS`; the original `timeout 60 sh -c ...` exits 127 there and the
CPU fault never runs. The CPU command now picks the syntax the container supports (PORTABLE_TIMEOUT). Each fault's
output goes to fault_logs/ and its exit code is stored in state.json, so a silent no-op can no longer pass unnoticed.

Usage:  python driver_ext.py run [--only CASE_ID ...] [--smoke]
State:  state.json (atomic writes) and ground_truth_ext.csv in this folder. Re-running skips DONE/EXCLUDED cases.
"""
import json, os, subprocess, sys, threading, time, datetime, random

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
GT = os.path.join(HERE, "ground_truth_ext.csv")
CASES = os.path.join(HERE, "cases_ext.json")
LOG = os.path.join(HERE, "driver.log")
FAULT_LOGS = os.path.join(HERE, "fault_logs")
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
DISTROLESS = {"cartservice", "checkoutservice", "productcatalogservice"}
DURATION, STAGGER, WAIT = 60, 15, 300  # clean re-run: 300 s wait so no two cases share an export window
BUSYBOX = "https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox"
LOCK = threading.Lock()
# BusyBox < 1.30 needs `timeout -t N`; coreutils and newer BusyBox reject -t and take `timeout N`.
PORTABLE_TIMEOUT = (f"if timeout -t 1 true 2>/dev/null; then T='timeout -t {DURATION}'; else T='timeout {DURATION}'; fi;"
                    f" $T sh -c 'while true; do :; done'")


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    with LOCK:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n"); f.flush(); os.fsync(f.fileno())


def atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def set_state(cid, **kw):
    with LOCK:
        st = load_state(); st.setdefault(cid, {}).update(kw); atomic_json(STATE, st)


def gt_append(line):
    with LOCK:
        with open(GT, "a", encoding="utf-8") as f:
            f.write(line + "\n"); f.flush(); os.fsync(f.fileno())


def kc(args, timeout=60):
    r = subprocess.run(["kubectl"] + args, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def pod_of(ns, svc):
    for sel in (f"app={svc}", f"name={svc}"):
        rc, out, _ = kc(["get", "pod", "-n", ns, "-l", sel, "--field-selector=status.phase=Running",
                         "-o", "jsonpath={.items[0].metadata.name}"])
        if rc == 0 and out:
            return out
    return ""


def ready(ns, svc):
    for sel in (f"app={svc}", f"name={svc}"):
        rc, out, _ = kc(["get", "pod", "-n", ns, "-l", sel, "-o",
                         "jsonpath={.items[*].status.containerStatuses[*].ready}"])
        if rc == 0 and out:
            return all(x == "true" for x in out.split())
    return False


def wait_ready(ns, svcs, limit=240):
    t0 = time.time()
    while time.time() - t0 < limit:
        if all(ready(ns, s) for s in svcs):
            return True
        time.sleep(10)
    return False


def debug_pod_for(node):
    rc, out, _ = kc(["get", "pods", "-n", "default", "-o",
                     "jsonpath={range .items[*]}{.metadata.name} {.spec.nodeName} {.status.phase}{\"\\n\"}{end}"])
    for line in out.splitlines():
        p = line.split()
        if len(p) == 3 and p[0].startswith("node-debugger") and p[1] == node and p[2] == "Running":
            return p[0]
    return ""


def distroless_target(ns, svc):
    rc, node, _ = kc(["get", "pod", "-n", ns, "-l", f"app={svc}", "-o", "jsonpath={.items[0].spec.nodeName}"])
    rc2, cid, _ = kc(["get", "pod", "-n", ns, "-l", f"app={svc}", "-o",
                      "jsonpath={.items[0].status.containerStatuses[0].containerID}"])
    cid = cid.replace("containerd://", "")
    dbg = debug_pod_for(node)
    if not (node and cid and dbg):
        raise RuntimeError(f"distroless target unresolved: {svc} node={node} dbg={dbg} cid={bool(cid)}")
    rootfs = f"/run/containerd/io.containerd.runtime.v2.task/k8s.io/{cid}/rootfs"
    rc, _, err = kc(["exec", dbg, "--", "chroot", "/host", "sh", "-c",
                     f"[ -f {rootfs}/busybox ] || (curl -sL {BUSYBOX} -o {rootfs}/busybox && chmod +x {rootfs}/busybox)"],
                    timeout=120)
    if rc != 0:
        raise RuntimeError(f"busybox prep failed for {svc}: {err[:200]}")
    return dbg, cid


def fire(ns, svc, fault, container, cid_case):
    """Start one fault; returns the background Popen (not waited)."""
    if ns == "boutique" and svc in DISTROLESS:
        dbg, cid = distroless_target(ns, svc)
        if fault == "cpu":
            inner = f"/busybox timeout {DURATION} /busybox sh -c 'while true; do :; done'"
        else:
            inner = (f"/busybox rm -f /dev/shm/fill_*; /busybox dd if=/dev/zero of=/dev/shm/fill_{cid_case} bs=1M count=60;"
                     f" /busybox sleep {DURATION}; /busybox rm -f /dev/shm/fill_{cid_case}")
        cmd = ["kubectl", "exec", dbg, "--", "chroot", "/host", "crictl", "exec", cid, "/busybox", "sh", "-c", inner]
    else:
        pod = pod_of(ns, svc)
        if not pod:
            raise RuntimeError(f"no running pod for {ns}/{svc}")
        if fault == "cpu":
            inner = PORTABLE_TIMEOUT
        else:
            inner = (f"rm -f /dev/shm/fill_*; dd if=/dev/zero of=/dev/shm/fill_{cid_case} bs=1M count=60 2>/dev/null;"
                     f" sleep {DURATION}; rm -f /dev/shm/fill_{cid_case}")
        cmd = ["kubectl", "exec", "-n", ns, pod, "-c", container, "--", "sh", "-c", inner]
    os.makedirs(FAULT_LOGS, exist_ok=True)
    out = open(os.path.join(FAULT_LOGS, f"{cid_case}__{svc}_{fault}.log"), "w", encoding="utf-8")
    return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)


def container_of(ns, svc):
    return "server" if ns == "boutique" else svc


def run_case(c, smoke=False):
    cid, ns = c["id"], c["ns"]
    targets = [c["svc_a"]] + ([c["svc_b"]] if c.get("svc_b") else [])
    if not wait_ready(ns, targets):
        set_state(cid, status="EXCLUDED", note="target pod not Ready before the case")
        log(f"{cid} EXCLUDED (not ready)"); return
    set_state(cid, status="FIRING")
    start = int(time.time())
    if c.get("svc_b"):
        gt_append(f"{cid},{ns},{c['svc_a']},{c['fault_a']},{c['svc_b']},{c['fault_b']},{STAGGER},{start}")
    else:
        gt_append(f"{cid},{ns},{c['svc_a']},{c['fault_a']},,,0,{start}")
    try:
        p1 = fire(ns, c["svc_a"], c["fault_a"], container_of(ns, c["svc_a"]), cid)
        log(f"{cid} fired {c['svc_a']} ({c['fault_a']})")
        p2 = None
        if c.get("svc_b"):
            time.sleep(STAGGER)
            p2 = fire(ns, c["svc_b"], c["fault_b"], container_of(ns, c["svc_b"]), cid)
            log(f"{cid} fired {c['svc_b']} ({c['fault_b']})")
    except Exception as e:  # failed injection -> excluded (pre-declared)
        set_state(cid, status="EXCLUDED", start=start, note=f"injection failed: {e}"[:300])
        log(f"{cid} EXCLUDED injection failed: {e}"); return
    end = int(time.time())
    gt_append(f"{cid},end_time,{end}")
    set_state(cid, status="FIRED", start=start, end=end)
    # let both faults run out (60 s) and the system recover, as in the original (100 s wait)
    t_wait = WAIT if not smoke else 90
    time.sleep(t_wait)
    for p in (p1, p2):
        if p is not None and p.poll() is None:
            p.terminate()
    rcs = [p.wait(timeout=30) if p is not None else None for p in (p1, p2)]
    set_state(cid, status="DONE", done_at=int(time.time()), rc_a=rcs[0], rc_b=rcs[1])
    log(f"{cid} DONE")


def stream(cases, smoke):
    for c in cases:
        st = load_state().get(c["id"], {})
        if st.get("status") in ("DONE", "EXCLUDED"):
            continue
        if st.get("status") in ("FIRING", "FIRED"):
            # interrupted mid-case: faults self-terminate after 60 s; wait out the window, then record as excluded
            log(f"{c['id']} was interrupted in state {st.get('status')}; marking EXCLUDED (interrupted)")
            set_state(c["id"], status="EXCLUDED", note="interrupted mid-case (driver restart)")
            time.sleep(WAIT)
            continue
        run_case(c, smoke)


def main():
    args = sys.argv[1:]
    with open(CASES, encoding="utf-8") as f:
        cases = json.load(f)
    only = set(args[args.index("--only") + 1:]) if "--only" in args else None
    smoke = "--smoke" in args
    if only:
        cases = [c for c in cases if c["id"] in only]
    by_app = {}
    for c in cases:
        by_app.setdefault(c["ns"], []).append(c)
    log(f"driver start: {len(cases)} cases, streams={ {k: len(v) for k, v in by_app.items()} } smoke={smoke}")
    th = [threading.Thread(target=stream, args=(v, smoke), daemon=False) for v in by_app.values()]
    for t in th:
        t.start()
    for t in th:
        t.join()
    log("driver finished")


if __name__ == "__main__":
    main()
