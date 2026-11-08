"""make_tables.py -- build the report tables straight from the summary JSONs (no hand-copied numbers).

  python make_tables.py      (any python3 with the json module; reads data/results/camera_ready/rankers/summary_*.json)

Writes data/results/camera_ready/rankers/table_rankers.tex (compact one-column LaTeX table, % src lines) and tables_rankers.md.
"""
import json
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import OUT  # noqa: E402
NAMES = {"robust": "Robust (paper)", "nsigma": "N-Sigma", "pagerank": "PageRank (graph)",
         "circa": "CIRCA (causal)", "circa_rcaeval": "CIRCA, RCAEval defaults", "rcd": "RCD (causal)",
         "random": "Random ranking"}
TEX_ROWS = ["robust", "nsigma", "pagerank", "circa", "rcd", "random"]
TEX_NAMES = {"robust": "Robust (paper)", "nsigma": "N-Sigma", "pagerank": "PageRank",
             "circa": "CIRCA", "rcd": "RCD$^{\\dagger}$", "random": "Random$^{\\ddagger}$"}


def f3(x):
    return ("%.3f" % x).replace("0.", ".", 1) if x < 1 else "%.2f" % x


def ms(v, sd=False):
    m, s = v
    return "%.3f" % m + (" ± %.3f" % s if sd and s > 0 else "")


def ci(e, key):
    c = e.get("ci95", {}).get(key)
    return " [%.2f, %.2f]" % tuple(c["ci"]) if c else ""


def main():
    S = json.load(open(os.path.join(OUT, "summary_concurrent.json")))
    R = S["rankers"]
    md = ["## Concurrent faults (n = %d cases; metric-level lists, paper definitions)\n" % S["n_cases"],
          "| Ranker | AC@1 | AC@2 | AC@3 | AC@5 | Both@2 [95% CI] | Both@5 [95% CI] | Any@5 [95% CI] "
          "| Both@all (list) | mean list length |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for rk in [k for k in NAMES if k in R]:
        r = R[rk]["ranking"]
        sd = R[rk]["n_seeds"] > 1
        md.append("| %s%s | %s | %s | %s | %s | %s%s | %s%s | %s%s | %s | %.1f |" % (
            NAMES[rk], " (%d seeds)" % R[rk]["n_seeds"] if sd else "",
            ms(r["ac1"], sd), ms(r["ac2"], sd), ms(r["ac3"], sd), ms(r["ac5"], sd),
            ms(r["both2"], sd), ci(R[rk], "both2"), ms(r["both5"], sd), ci(R[rk], "both5"),
            ms(r["any5"], sd), ci(R[rk], "any5"), ms(r["both_all"], sd), r["list_len"][0]))
    md += ["", "### Stage (released cluster_candidates_v2, alpha=0.7, eps=0.4, minPts=2) on each ranker's list\n",
           "k_in = entries the stage partitions; Prop. 2.1 bound = Both@k_in (fraction of cases with both causes "
           "among those entries); violations = cases separated although a cause is missing from the input.\n",
           "| Ranker | input | k_in | separation [95% CI] | bound Both@k_in | ≤ Both@2? | violations | grouped AC@1 "
           "| separation, suffix-aware svc mapping | oracle-grid max sep. (α,ε) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for rk in [k for k in NAMES if k in R]:
        for mode in ("full", "top10", "top5"):
            st = R[rk]["stage"]["paper/%s" % mode]
            fx = R[rk]["stage"]["fixed/%s" % mode]
            gb = R[rk]["grid_best"].get("paper/%s" % mode)
            c = st.get("separation_ci95")
            sd = R[rk]["n_seeds"] > 1
            md.append("| %s | %s | %.1f | %s%s | %s | %s | %d | %s | %s | %s |" % (
                NAMES[rk], mode, st["k_in_mean"], ms(st["separation"], sd),
                " [%.2f, %.2f]" % tuple(c["ci"]) if c else "", ms(st["both_in"], sd),
                "yes" if st["sep_le_both2"] else "NO", st["case_level_violations"], ms(st["grouped_ac1"], sd),
                ms(fx["separation"], sd),
                ("%.3f (%.1f, %.2f); %d/15 settings > Both@2" % (gb["separation"], gb["alpha"], gb["eps"],
                                                               gb["n_settings_sep_gt_both2"])) if gb else "–"))
    md += ["", "### Below chance? P(X ≤ observed) under a uniformly random ranking of the same candidates "
               "(Poisson-binomial over the 28 exact per-case probabilities)\n",
           "| Ranker | Both@2 obs / E_random (p) | Both@5 obs / E_random (p) | Any@5 obs / E_random (p) |",
           "|---|---|---|---|"]
    for rk, e in S["below_chance"].items():
        cells = []
        for m in ("both2", "both5", "any5"):
            o, p = e[m]["observed_cases"], e[m]["p_le_observed"]
            if isinstance(o, list):
                cells.append("%.1f (seeds %d–%d) / %.1f (median p %.3g)" % (
                    sum(o) / len(o), min(o), max(o), e[m]["expected_cases_random"], sorted(p)[len(p) // 2]))
            else:
                cells.append("%d / %.1f (p = %.3g)" % (o, e[m]["expected_cases_random"], p))
        md.append("| %s | %s |" % (NAMES[rk], " | ".join(cells)))
    md += ["", "### Service-level lists (each service once, first occurrence)\n",
           "| Ranker | svc AC@1 | svc AC@2 | svc Both@2 | svc Both@3 | svc Both@5 | svc Any@1 | svc Any@2 | svc Any@5 |", "|---|---|---|---|---|---|---|---|---|"]
    for rk in [k for k in NAMES if k in R]:
        v = R[rk]["svc"]
        sd = R[rk]["n_seeds"] > 1
        md.append("| %s | %s |" % (NAMES[rk], " | ".join(ms(v[m], sd) for m in (
            "svc_ac1", "svc_ac2", "svc_both2", "svc_both3", "svc_both5", "svc_any1", "svc_any2", "svc_any5"))))
    for name, v in S["service_level_only"].items():
        md.append("| %s (original run_graph_ranker.py design) | %s |" % (name, " | ".join("%.3f" % v[m] for m in (
            "svc_ac1", "svc_ac2", "svc_both2", "svc_both3", "svc_both5", "svc_any1", "svc_any2", "svc_any5"))))
    md += ["", "### Per system (AC@2 / Both@2 / Both@5 / Any@5)\n", "| Ranker | Online Boutique (15) | Sock Shop (13) |",
           "|---|---|---|"]
    for rk in [k for k in NAMES if k in R]:
        b = R[rk]["ranking_by_ns"]
        md.append("| %s | %s | %s |" % (NAMES[rk], *[" / ".join("%.3f" % b[ns][m][0] for m in ("ac2", "both2", "both5", "any5"))
                                                     for ns in ("boutique", "sock-shop")]))
    md += ["", "Runtime per case (s, mean): " + ", ".join(
        "%s %.2f" % (NAMES[rk], R[rk]["runtime_s_per_case"][0]) for rk in R if "runtime_s_per_case" in R[rk])
        + "; bocpd %.2f." % S["runtime_bocpd_s_per_case"][0]]

    # ---------------- LaTeX (one column)
    tex = [
        "% src: data/results/camera_ready/rankers/summary_concurrent.json",
        "%      (scripts/step1_precompute_baro.py, step2_causal.py, step3_evaluate.py; table by scripts/make_tables.py)",
        "% 28 concurrent cases, same bocpd change point and candidate metrics for every ranker;",
        "% metric-level lists, AC@k/Both@k/Any@k as Eqs. (ack)-(anyk); Sep. = released stage, alpha=0.7, eps=0.4.",
        "\\begin{table}[t]",
        "\\centering\\footnotesize",
        "\\setlength{\\tabcolsep}{3.2pt}",
        "\\caption{The bound holds for every ranker. Five rankers on the same 28 concurrent cases (same change point and "
        "candidate metrics). Sep.\\ is the fraction of cases the corrected stage ($\\alpha{=}0.7$, $\\varepsilon{=}0.4$) "
        "separates when fed that ranker's list; no case is separated unless both causes are among the entries it "
        "partitions (Proposition~\\ref{prop:bound}).}",
        "\\label{tab:rankers}",
        "\\begin{tabular}{@{}lccccccc@{}}",
        "\\toprule",
        "\\textbf{Ranker} & \\textbf{AC@1} & \\textbf{AC@2} & \\textbf{AC@5} & \\textbf{Both@2} & \\textbf{Both@5} & "
        "\\textbf{Any@5} & \\textbf{Sep.}\\\\",
        "\\midrule",
    ]
    for rk in TEX_ROWS:
        if rk not in R:
            continue
        if rk == "random":
            tex.append("\\midrule")
        r = R[rk]["ranking"]
        sep = R[rk]["stage"]["paper/full"]["separation"][0]
        tex.append("%s & %s \\\\" % (TEX_NAMES[rk], " & ".join(
            f3(r[m][0]) for m in ("ac1", "ac2", "ac5", "both2", "both5", "any5")) + " & " + f3(sep)))
    nseed = R.get("rcd", {}).get("n_seeds", 0)
    tex += ["\\bottomrule", "\\end{tabular}",
            "\\par\\smallskip\\raggedright\\scriptsize $^{\\dagger}$Mean of %d seeds; RCD returns a short list "
            "(%.1f entries on average). $^{\\ddagger}$Exact expectation over random orderings of the same candidates "
            "(Sep.\\ by Monte Carlo)." % (nseed, R["rcd"]["ranking"]["list_len"][0]) if "rcd" in R else "",
            "\\end{table}"]

    # ---------------- single-fault (if available)
    p1 = os.path.join(OUT, "summary_single.json")
    if os.path.exists(p1):
        T = json.load(open(p1))
        P = T["paired_subset"]["rankers"]
        md += ["", "## Collapse per ranker: single-fault AC@1 (paired subset, %d cases) vs concurrent AC@2 (28 cases)\n"
               % T["paired_subset"]["n_cases"],
               "Skill = (AC − AC_random)/(1 − AC_random): 0 = chance level, 1 = perfect, < 0 = below chance; the two "
               "settings have very different chance levels, so skill is the like-for-like comparison.\n",
               "| Ranker | single AC@1 | single skill | concurrent AC@2 | concurrent skill | concurrent Both@2 |",
               "|---|---|---|---|---|---|"]
        rs1, rc2 = P["random"]["ranking"]["ac1"][0], R["random"]["ranking"]["ac2"][0]
        for rk in [k for k in NAMES if k in P and k in R]:
            a1, a2 = P[rk]["ranking"]["ac1"][0], R[rk]["ranking"]["ac2"][0]
            md.append("| %s | %.3f | %+.2f | %.3f | %+.2f | %.3f |" % (
                NAMES[rk], a1, (a1 - rs1) / (1 - rs1), a2, (a2 - rc2) / (1 - rc2), R[rk]["ranking"]["both2"][0]))
        for label, block in (("all %d cases" % T["n_cases"], T["rankers"]),
                             ("paired subset, %d cases (reps %s of every service x fault)" % (
                                 T["paired_subset"]["n_cases"], ",".join(T["paired_subset"]["reps"])),
                              T["paired_subset"]["rankers"])):
            md += ["", "## Single fault — %s\n" % label,
                   "| Ranker | n | AC@1 [95% CI] | AC@3 | AC@5 | Boutique AC@1 | Sock Shop AC@1 | stage: kept one group "
                   "| stage: hit |", "|---|---|---|---|---|---|---|---|---|"]
            for rk in [k for k in NAMES if k in block]:
                e = block[rk]
                r = e["ranking"]
                sd = e["n_seeds"] > 1
                st = e["stage"].get("full")
                md.append("| %s%s | %d | %s%s | %s | %s | %s | %s | %s | %s |" % (
                    NAMES[rk], " (%d seeds)" % e["n_seeds"] if sd else "", e["n_cases"], ms(r["ac1"], sd),
                    ci(e, "ac1"), ms(r["ac3"], sd), ms(r["ac5"], sd),
                    ms(e["ranking_by_ns"]["boutique"]["ac1"], sd), ms(e["ranking_by_ns"]["sock-shop"]["ac1"], sd),
                    ms(st["kept_one_group"], sd) if st else "–", ms(st["hit"], sd) if st else "–"))
    with open(os.path.join(OUT, "tables_rankers.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(OUT, "table_rankers.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(tex) + "\n")
    print("\n".join(tex))


if __name__ == "__main__":
    main()
