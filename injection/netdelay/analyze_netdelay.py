"""Analysis of the network-delay cases (pre-declared; see README). Unchanged paper pipeline.

Used cases = driver status DONE and every injected fault visible (injection_check.csv). For four series formats
  five      : the paper's five series per service (caller-observed latency dropped)
  five_mrg  : five series with the duplicated memory series merged (memory_usage_bytes dropped), as in the paper's RQ2
  six       : five series + caller-observed latency (<svc>_istio_latency_src)
  six_mrg   : six series, memory merged
it builds <fmt>/data/concurrent/*.csv + ground_truth_log.csv, runs the released precompute.py --only concurrent and
clean/case_numbers.py --csv, and aggregates per arm (D1 delay+memory, D2 CPU+delay) and overall:
AC@1/2/3/5, Both@2/3/5, Any@5, separated at (0.7, 0.4), Proposition 2.1 violations.
Writes analysis_out/RESULTS_NETDELAY_numbers.json and .md. No parameter is tuned.
"""
import csv
import json
import os
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "artifact_repo"))
OUT = os.path.join(HERE, "analysis_out")
PY = sys.executable
FORMATS = {"five": (True, False), "five_mrg": (True, True), "six": (False, False), "six_mrg": (False, True)}


def main():
    cases = {c["id"]: c for c in json.load(open(os.path.join(HERE, "cases_ext.json"), encoding="utf-8"))}
    state = json.load(open(os.path.join(HERE, "state.json"), encoding="utf-8"))
    vis = {r["case"]: r for r in csv.DictReader(open(os.path.join(HERE, "injection_check.csv"), encoding="utf-8"))}
    gt8, gtend = {}, {}
    for line in open(os.path.join(HERE, "ground_truth_ext.csv"), encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) == 8:
            gt8[p[0]] = line.strip()
        elif len(p) == 3 and p[1] == "end_time":
            gtend[p[0]] = line.strip()
    src_dir = os.path.join(HERE, "data_ext", "primary")
    used = sorted(cid for cid in cases if state.get(cid, {}).get("status") == "DONE"
                  and vis.get(cid, {}).get("visible_all") == "True" and cid in gt8
                  and os.path.exists(os.path.join(src_dir, cid + ".csv")))
    os.makedirs(OUT, exist_ok=True)
    summary = {"cases_total": len(cases), "done": sum(1 for c in cases if state.get(c, {}).get("status") == "DONE"),
               "used": len(used), "excluded": {c: state.get(c, {}).get("note", state.get(c, {}).get("status"))
                                               for c in cases if c not in used}, "formats": {}}
    for fmt, (drop_src, drop_mem) in FORMATS.items():
        d = os.path.join(OUT, fmt)
        dd = os.path.join(d, "data", "concurrent")
        os.makedirs(dd, exist_ok=True)
        for cid in used:
            df = pd.read_csv(os.path.join(src_dir, cid + ".csv"))
            cols = [c for c in df.columns if not ((drop_src and c.endswith("_istio_latency_src"))
                                                  or (drop_mem and c.endswith("_memory_usage_bytes")))]
            df[cols].to_csv(os.path.join(dd, cid + ".csv"), index=False)
        with open(os.path.join(d, "data", "ground_truth_log.csv"), "w", encoding="utf-8") as f:
            for cid in used:
                f.write(gt8[cid] + "\n")
                if cid in gtend:
                    f.write(gtend[cid] + "\n")
        env = dict(os.environ, CODS_CONCURRENT_DIR=dd, CODS_GROUND_TRUTH=os.path.join(d, "data", "ground_truth_log.csv"),
                   CODS_OUT=os.path.join(d, "results"), CODS_REPO=REPO, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONIOENCODING="utf-8")
        fs = os.path.join(REPO, "analysis", "camera_ready")
        with open(os.path.join(d, "pipeline_log.txt"), "w", encoding="utf-8") as lg:
            subprocess.run([PY, os.path.join(fs, "folds_stats", "precompute.py"), "--only", "concurrent", "--workers", "4"],
                           env=env, stdout=lg, stderr=subprocess.STDOUT)
            per = os.path.join(d, "per_case.csv")
            subprocess.run([PY, os.path.join(fs, "clean", "case_numbers.py"), "--csv", per], env=env, stdout=lg,
                           stderr=subprocess.STDOUT)
        if not os.path.exists(per):
            summary["formats"][fmt] = "pipeline failed (see pipeline_log.txt)"
            continue
        t = pd.read_csv(per)
        t["arm"] = t.case_id.map(lambda c: cases[c].get("arm"))
        res = {}
        for arm, sub in [("all", t)] + list(t.groupby("arm")):
            n = len(sub)
            res[arm] = {"n": n, **{m.upper().replace("AC", "AC@"): round(float(sub[m].mean()), 3)
                                   for m in ("ac1", "ac2", "ac3", "ac5")},
                        "Both@2": f"{int(sub.both2.sum())}/{n}", "Both@3": f"{int(sub.both3.sum())}/{n}",
                        "Both@5": f"{int(sub.both5.sum())}/{n}", "Any@5": f"{int(sub.any5.sum())}/{n}",
                        "separated": f"{int(sub.separated.sum())}/{n}", "Prop2.1_violations": int(sub.violation.sum()),
                        "by_app": {ns: {"n": len(g), "AC@2": round(float(g.ac2.mean()), 3),
                                        "Both@2": f"{int(g.both2.sum())}/{len(g)}", "Both@5": f"{int(g.both5.sum())}/{len(g)}"}
                                   for ns, g in sub.groupby("namespace")}}
        summary["formats"][fmt] = res
    json.dump(summary, open(os.path.join(OUT, "RESULTS_NETDELAY_numbers.json"), "w", encoding="utf-8"), indent=1)
    lines = [f"# Network-delay extension: numbers (auto-generated)\n", f"used {len(used)} of {len(cases)} cases\n"]
    for fmt, res in summary["formats"].items():
        lines.append(f"\n## {fmt}\n")
        if isinstance(res, str):
            lines.append(res + "\n")
            continue
        lines.append("| arm | n | AC@1 | AC@2 | AC@3 | AC@5 | Both@2 | Both@3 | Both@5 | Any@5 | separated | violations |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for arm, r in res.items():
            lines.append(f"| {arm} | {r['n']} | {r['AC@1']} | {r['AC@2']} | {r['AC@3']} | {r['AC@5']} | {r['Both@2']} | "
                         f"{r['Both@3']} | {r['Both@5']} | {r['Any@5']} | {r['separated']} | {r['Prop2.1_violations']} |")
    open(os.path.join(OUT, "RESULTS_NETDELAY_numbers.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
