#!/usr/bin/env python3
"""Network-delay driver. Resumable; one stream per application,
run in parallel.

Built on ../clean_collection/core/driver_ext.py (portable CPU command, fault logs and exit codes, 300-s wait); the CPU and memory
faults are fired by the same code and the same commands:
  CPU    = busy loop for 60 s (BusyBox `timeout` syntax picked per container);
  memory = 60 MB written to /dev/shm, held 60 s, removed;
  distroless Boutique services (cartservice, checkoutservice, productcatalogservice) via the node debug pods,
  crictl exec and a pre-placed BusyBox.
New fault `delay`: tc netem egress delay of DELAY_MS on eth0 of the faulted pod's network
namespace, held 60 s, then removed. Injected from the node debug pod (nicolaka/netshoot, sysadmin profile) with
netem.sh: sandbox PID from `crictl inspect`/`crictl inspectp`, then `nsenter -t PID -n tc ...`. Istio agent/Envoy
ports 15020/15021/15090 bypass the delay (probes and metric scrapes stay undelayed). The driver removes the qdisc at
+60 s and reads it back; a watchdog in the debug pod removes it at +75 s if the driver could not; every case also
removes it in a `finally` block. Every netem command, its exit code and its read-back go to
fault_logs/<case>__<svc>_delay.log. A delay whose removal is not verified excludes its case (pre-declared).

Second fault 15 s after the first; 300-s wait after each case.

Usage:  python driver_netdelay.py run [--workdir DIR] [--only CASE_ID ...] [--smoke] [--wait S] [--delay-ms MS]
        python driver_netdelay.py sweep [--workdir DIR]     (remove any netem qdisc left on the target services)
State:  <workdir>/state.json (atomic writes) and ground_truth_ext.csv. Re-running skips DONE/EXCLUDED cases.
--wait and --delay-ms are accepted only with --smoke (uncounted pilot).
"""
import json, os, subprocess, sys, threading, time, datetime, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = HERE
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
DISTROLESS = {"cartservice", "checkoutservice", "productcatalogservice"}
DURATION, STAGGER, WAIT = 60, 15, 300  # 300-s wait as in the clean re-run: no two cases share an export window
DELAY_MS = 300                          # fixed before the counted cases, after an uncounted pilot
WD_SLACK = 15                           # the debug-pod watchdog removes the qdisc at DURATION + WD_SLACK if needed
ARM_EST = 4.0                           # pilot: netem.sh needs about 4-8 s from exec start to ARMED
BUSYBOX = "https://busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox"
NETEM_SH = os.path.join(HERE, "netem.sh")
LOCK = threading.Lock()
# BusyBox < 1.30 needs `timeout -t N`; coreutils and newer BusyBox reject -t and take `timeout N`.
PORTABLE_TIMEOUT = (f"if timeout -t 1 true 2>/dev/null; then T='timeout -t {DURATION}'; else T='timeout {DURATION}'; fi;"
                    f" $T sh -c 'while true; do :; done'")
DELAY_TARGETS = {"boutique": ["adservice", "cartservice", "currencyservice", "productcatalogservice"],
                 "sock-shop": ["catalogue", "carts", "payment"]}


def paths():
    return {k: os.path.join(WORK, v) for k, v in dict(STATE="state.json", GT="ground_truth_ext.csv",
                                                      CASES="cases_ext.json", LOG="driver.log",
                                                      FAULT_LOGS="fault_logs").items()}


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    with LOCK:
        with open(paths()["LOG"], "a", encoding="utf-8") as f:
            f.write(line + "\n"); f.flush(); os.fsync(f.fileno())


def atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def load_state():
    if os.path.exists(paths()["STATE"]):
        with open(paths()["STATE"], encoding="utf-8") as f:
            return json.load(f)
    return {}


def set_state(cid, **kw):
    with LOCK:
        st = load_state(); st.setdefault(cid, {}).update(kw); atomic_json(paths()["STATE"], st)


def gt_append(line):
    with LOCK:
        with open(paths()["GT"], "a", encoding="utf-8") as f:
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


class DelayFault:
    """netem egress delay on one pod; Popen-like (poll/terminate/wait) so run_case treats it like the other faults."""

    def __init__(self, ns, svc, case_id, ms):
        self.ns, self.svc, self.case, self.ms = ns, svc, case_id, ms
        self.nonce = f"{case_id[-24:]}-{uuid.uuid4().hex[:6]}".replace("_", "-")
        self.lock = threading.Lock()
        self.removed, self.rc, self.t_on, self.timer, self.attempted, self.held = False, None, None, None, False, None
        os.makedirs(paths()["FAULT_LOGS"], exist_ok=True)
        self.logpath = os.path.join(paths()["FAULT_LOGS"], f"{case_id}__{svc}_delay.log")
        with open(NETEM_SH, encoding="utf-8") as f:
            self.script = f.read().replace("\r\n", "\n")
        self.resolve()

    def _log(self, text):
        with open(self.logpath, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S.%f} {text}\n"); f.flush(); os.fsync(f.fileno())

    def resolve(self):
        self.pod = pod_of(self.ns, self.svc)
        if not self.pod:
            raise RuntimeError(f"no running pod for {self.ns}/{self.svc}")
        rc, self.node, _ = kc(["get", "pod", "-n", self.ns, self.pod, "-o", "jsonpath={.spec.nodeName}"])
        rc2, cid, _ = kc(["get", "pod", "-n", self.ns, self.pod, "-o",
                          "jsonpath={.status.containerStatuses[0].containerID}"])
        self.cid = cid.replace("containerd://", "")
        self.dbg = debug_pod_for(self.node)
        self._log(f"resolve pod={self.pod} node={self.node} cid={self.cid[:16]} debug_pod={self.dbg}")
        if not (self.node and self.cid and self.dbg):
            raise RuntimeError(f"delay target unresolved: {self.svc} node={self.node} dbg={self.dbg} cid={bool(self.cid)}")

    def _exec(self, op, *args, timeout=60):
        cmd = ["kubectl", "exec", "-i", "-n", "default", self.dbg, "--", "sh", "-s", "--", op, self.cid, self.pod, *args]
        t0 = time.time()
        try:
            # bytes, not text: on Windows text-mode stdin turns "\n" into "\r\n", which breaks the sh script
            r = subprocess.run(cmd, input=self.script.encode("utf-8"), capture_output=True, timeout=timeout)
            rc = r.returncode
            out = (r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")).strip()
        except subprocess.TimeoutExpired as e:
            rc, out = 124, f"TIMEOUT after {timeout} s: {e}"
        self._log(f"$ {' '.join(cmd[:6])} ... {' '.join(cmd[8:])}  rc={rc} ({time.time() - t0:.1f} s)\n    "
                  + "\n    ".join(out.splitlines()))
        return rc, out

    def state(self):
        rc, out = self._exec("state")
        q = next((l for l in out.splitlines() if l.startswith("RB_QDISC:")), "")
        return rc, ("netem" in q or "prio" in q), out

    def on(self):
        self.attempted = True
        rc, out = self._exec("on", self.nonce, str(DURATION + WD_SLACK), str(self.ms))
        if rc != 0 or "ARMED" not in out:
            raise RuntimeError(f"netem on failed rc={rc}: {out[-200:]}")
        self.t_on = time.time()
        self.timer = threading.Thread(target=self._hold_then_off, daemon=True)
        self.timer.start()
        return self

    def _hold_then_off(self):
        time.sleep(max(0.0, self.t_on + DURATION - time.time()))
        self.off()

    def off(self):
        with self.lock:
            if self.removed or self.t_on is None:
                return self.rc
            for attempt in range(4):
                rc, out = self._exec("off")
                rc2, present, _ = self.state()
                if rc == 0 and "REMOVED" in out and rc2 == 0 and not present:
                    self.removed, self.rc = True, 0
                    self.held = round(time.time() - self.t_on, 1)
                    self._log(f"removal verified after {self.held:.1f} s")
                    log(f"{self.case} removed delay on {self.svc} after {self.held:.0f} s (verified)")
                    return 0
                time.sleep(5 * (attempt + 1))
            self.rc = 3
            self._log("REMOVAL NOT VERIFIED after 4 attempts (the debug-pod watchdog is the backstop)")
            log(f"{self.case} REMOVAL NOT VERIFIED for delay on {self.svc}")
            return 3

    # Popen-like interface
    def poll(self):
        return self.rc

    def terminate(self):
        self.off()

    def wait(self, timeout=None):
        if self.timer is not None:
            self.timer.join(timeout)
        return self.off() if not self.removed else self.rc


def fire(ns, svc, fault, container, cid_case, prepared=None):
    """Start one fault; returns a background handle (not waited)."""
    if fault == "delay":
        return prepared.on()
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
    os.makedirs(paths()["FAULT_LOGS"], exist_ok=True)
    out = open(os.path.join(paths()["FAULT_LOGS"], f"{cid_case}__{svc}_{fault}.log"), "w", encoding="utf-8")
    return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)


def container_of(ns, svc):
    return "server" if ns == "boutique" else svc


def run_case(c, smoke=False, wait=WAIT, ms=DELAY_MS):
    cid, ns = c["id"], c["ns"]
    targets = [c["svc_a"], c["svc_b"]]
    if not wait_ready(ns, targets):
        set_state(cid, status="EXCLUDED", note="target pod not Ready before the case")
        log(f"{cid} EXCLUDED (not ready)"); return
    delays = {}
    try:  # resolve the delay target before the clock starts, so the delay fires with a single exec
        for s, f in ((c["svc_a"], c["fault_a"]), (c["svc_b"], c["fault_b"])):
            if f == "delay":
                d = DelayFault(ns, s, cid, ms)
                rc, present, out = d.state()
                if rc != 0 or present:
                    raise RuntimeError(f"pre-case read-back of {s}: rc={rc} qdisc_present={present}")
                delays[s] = d
    except Exception as e:  # noqa: BLE001
        set_state(cid, status="EXCLUDED", note=f"delay target not ready: {e}"[:300])
        log(f"{cid} EXCLUDED delay target not ready: {e}"); return
    set_state(cid, status="FIRING")
    start = int(time.time())  # replaced by the first fault's onset once it is active
    p1 = p2 = None
    try:
        try:
            # Schedule (timing fix after the uncounted pilot): the second fault becomes active STAGGER s
            # after the first is active. A delay is active when netem.sh reports ARMED (about 8 s after its exec
            # starts), so a delay used as the second fault is started ARM_EST s early.
            t_exec_a = time.time()
            p1 = fire(ns, c["svc_a"], c["fault_a"], container_of(ns, c["svc_a"]), cid, delays.get(c["svc_a"]))
            onset_a = delays[c["svc_a"]].t_on if c["fault_a"] == "delay" else time.time()
            start = int(onset_a)
            gt_append(f"{cid},{ns},{c['svc_a']},{c['fault_a']},{c['svc_b']},{c['fault_b']},{STAGGER},{start}")
            log(f"{cid} fired {c['svc_a']} ({c['fault_a']})")
            lead = ARM_EST if c["fault_b"] == "delay" else 0.0
            time.sleep(max(0.0, onset_a + STAGGER - lead - time.time()))
            t_exec_b = time.time()
            p2 = fire(ns, c["svc_b"], c["fault_b"], container_of(ns, c["svc_b"]), cid, delays.get(c["svc_b"]))
            onset_b = delays[c["svc_b"]].t_on if c["fault_b"] == "delay" else time.time()
            set_state(cid, stagger_s=round(onset_b - onset_a, 1))
            log(f"{cid} fired {c['svc_b']} ({c['fault_b']}); stagger {onset_b - onset_a:.1f} s")
        except Exception as e:  # failed injection -> excluded (pre-declared); wait so no window holds its faults
            set_state(cid, status="EXCLUDED", start=start, note=f"injection failed: {e}"[:300])
            log(f"{cid} EXCLUDED injection failed: {e}")
            for d in delays.values():
                if d.attempted and not d.removed:
                    d.t_on = d.t_on or time.time()
                    d.off()
            time.sleep(wait)
            return
        end = int(time.time())
        gt_append(f"{cid},end_time,{end}")
        set_state(cid, status="FIRED", start=start, end=end)
        time.sleep(wait)
        for p in (p1, p2):
            if p is not None and p.poll() is None:
                p.terminate()
        rcs = [p.wait(timeout=30) if p is not None else None for p in (p1, p2)]
        removal_ok = all(d.removed for d in delays.values())
        if not removal_ok:
            set_state(cid, status="EXCLUDED", done_at=int(time.time()), rc_a=rcs[0], rc_b=rcs[1],
                      note="delay removal not verified")
            log(f"{cid} EXCLUDED (delay removal not verified)")
        else:
            set_state(cid, status="DONE", done_at=int(time.time()), rc_a=rcs[0], rc_b=rcs[1], delay_ms=ms,
                      delay_on={s: round(d.t_on, 1) for s, d in delays.items()},
                      delay_held_s={s: d.held for s, d in delays.items()})
            log(f"{cid} DONE")
    finally:
        for d in delays.values():  # never leave a qdisc behind
            if d.attempted and not d.removed:
                d.t_on = d.t_on or time.time()
                d.off()


def sweep(namespaces=("boutique", "sock-shop")):
    """Read back every delay target; remove any netem/prio root qdisc found (logged)."""
    ok = True
    for ns in namespaces:
        for svc in DELAY_TARGETS[ns]:
            try:
                d = DelayFault(ns, svc, f"sweep_{datetime.datetime.now():%Y%m%d_%H%M%S}", 0)
                rc, present, _ = d.state()
                if present:
                    d.t_on = time.time()
                    rcx = d.off()
                    log(f"sweep: {ns}/{svc} had a qdisc; removal rc={rcx}")
                    ok &= rcx == 0
                elif rc != 0:
                    log(f"sweep: {ns}/{svc} read-back rc={rc}")
                    ok = False
            except Exception as e:  # noqa: BLE001
                log(f"sweep: {ns}/{svc} failed: {e}")
                ok = False
    log(f"sweep finished: {'clean' if ok else 'CHECK fault_logs/sweep_*'}")
    return ok


def stream(cases, smoke, wait, ms):
    for c in cases:
        st = load_state().get(c["id"], {})
        if st.get("status") in ("DONE", "EXCLUDED"):
            continue
        if st.get("status") in ("FIRING", "FIRED"):
            # interrupted mid-case: faults self-terminate (watchdog for delays); record as excluded, wait out the window
            log(f"{c['id']} was interrupted in state {st.get('status')}; marking EXCLUDED (interrupted)")
            set_state(c["id"], status="EXCLUDED", note="interrupted mid-case (driver restart)")
            time.sleep(WAIT)
            continue
        run_case(c, smoke, wait, ms)


def main():
    global WORK
    args = sys.argv[1:]
    if "--workdir" in args:
        WORK = os.path.abspath(args[args.index("--workdir") + 1])
    os.makedirs(WORK, exist_ok=True)
    smoke = "--smoke" in args
    wait = int(args[args.index("--wait") + 1]) if (smoke and "--wait" in args) else (WAIT if not smoke else 200)
    ms = int(args[args.index("--delay-ms") + 1]) if (smoke and "--delay-ms" in args) else DELAY_MS
    if args and args[0] == "sweep":
        sys.exit(0 if sweep() else 1)
    with open(paths()["CASES"], encoding="utf-8") as f:
        cases = json.load(f)
    only = None
    if "--only" in args:
        only = set(a for a in args[args.index("--only") + 1:] if not a.startswith("--"))
    if only:
        cases = [c for c in cases if c["id"] in only]
    by_app = {}
    for c in cases:
        by_app.setdefault(c["ns"], []).append(c)
    log(f"driver start: {len(cases)} cases, streams={ {k: len(v) for k, v in by_app.items()} } smoke={smoke} "
        f"wait={wait} delay_ms={ms} workdir={WORK}")
    sweep(tuple(by_app))
    th = [threading.Thread(target=stream, args=(v, smoke, wait, ms), daemon=False) for v in by_app.values()]
    for t in th:
        t.start()
    for t in th:
        t.join()
    sweep(tuple(by_app))
    log("driver finished")


if __name__ == "__main__":
    main()
