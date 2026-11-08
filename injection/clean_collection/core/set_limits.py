#!/usr/bin/env python3
"""Set the 18 app deployments to their 19-Aug resources (--aug19) or back to their pre-run resources (default) (the "now" values in
health/restore_plan.json, taken from health/snapshot_before/), wait for rollouts, verify, and log.

Usage: python restore_after.py --dry-run    (server-side dry run only)
       python restore_after.py              (apply, wait, verify) -> health/restore_after_log.txt
"""
import datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KUBECONFIG", os.path.join(os.environ.get("TEMP", "/tmp"), "cods.kubeconfig"))
LOG = os.path.join(HERE, "health", "limits_log.txt")
DRY = "--dry-run" in sys.argv
TARGET = "aug19" if "--aug19" in sys.argv else "now"


def kc(args, timeout=300):
    r = subprocess.run(["kubectl"] + args, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line)
    if not DRY:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def res_arg(d):
    return ",".join(f"{k}={v}" for k, v in sorted(d.items()))


def main():
    with open(os.path.join(HERE, "health", "restore_plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    ok = True
    for e in plan:
        ns, dep, now = e["ns"], e["dep"], e[TARGET]
        rc, cname = kc(["get", "deployment", dep, "-n", ns, "-o", "jsonpath={.spec.template.spec.containers[0].name}"])
        args = ["set", "resources", f"deployment/{dep}", "-n", ns, "-c", cname]
        if now.get("limits"):
            args.append(f"--limits={res_arg(now['limits'])}")
        if now.get("requests"):
            args.append(f"--requests={res_arg(now['requests'])}")
        if DRY:
            args.append("--dry-run=server")
        rc, out = kc(args)
        log(f"{ns}/{dep} [{cname}] rc={rc} {out.splitlines()[-1] if out else ''}")
        ok &= rc == 0
    if DRY:
        print("dry run", "OK" if ok else "FAILED")
        return
    for e in plan:
        rc, out = kc(["rollout", "status", f"deployment/{e['dep']}", "-n", e["ns"], "--timeout=300s"], timeout=320)
        log(f"rollout {e['ns']}/{e['dep']} rc={rc}")
        ok &= rc == 0
    bad = []
    for e in plan:
        rc, out = kc(["get", "deployment", e["dep"], "-n", e["ns"], "-o", "jsonpath={.spec.template.spec.containers[0].resources}"])
        live = json.loads(out) if rc == 0 and out else {}
        if live != e[TARGET]:
            bad.append((e["ns"], e["dep"], live, e[TARGET]))
    log(f"verify: {len(plan) - len(bad)}/{len(plan)} deployments match their pre-run resources")
    for b in bad:
        log(f"  MISMATCH {b}")
    print("RESTORE", "OK" if ok and not bad else "CHECK LOG")


if __name__ == "__main__":
    main()
