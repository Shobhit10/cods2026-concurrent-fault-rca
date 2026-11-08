"""
make_tables.py -- builds the report tables for RESULTS_FOLDS_STATS.md and the compact LaTeX table from raw/*.csv.

Outputs: raw/tables_generated.md, table_folds_stats.tex (in OUT)
"""
import sys
sys.dont_write_bytecode = True
import os

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
from stats_ci import cp, cp_upper1, wilson  # noqa: E402

R = C.RAW


def f3(x):
    return f"{x:.3f}"


def ci(lo, hi, d=3):
    return f"[{lo:.{d}f}, {hi:.{d}f}]"


def main():
    sc = pd.read_csv(os.path.join(R, "stats_ci.csv"))
    sx = pd.read_csv(os.path.join(R, "stats_extra.csv"))
    st = pd.read_csv(os.path.join(R, "stats_tests.csv"))
    lopo = pd.read_csv(os.path.join(R, "cv_lopo_folds.csv"))
    summ = pd.read_csv(os.path.join(R, "cv_summary.csv")).set_index("design")
    pub = pd.read_csv(os.path.join(C.PUB, "crossval_results.csv"))
    out = []

    def get(df, q, scope, method_prefix):
        r = df[(df["quantity"].str.startswith(q)) & (df["scope"] == scope) & (df["method"].str.startswith(method_prefix))]
        assert len(r) == 1, (q, scope, method_prefix, len(r))
        return r.iloc[0]

    # ---------------- grouped CV table ----------------
    pairs = {
        "boutique:pair1": "adservice (CPU) + cartservice (mem)",
        "boutique:pair2": "currencyservice (CPU) + cartservice (mem)",
        "boutique:pair3": "currencyservice (CPU) + productcatalogservice (mem)",
        "sockshop:pair1": "catalogue (CPU) + carts (mem)",
        "sockshop:pair2": "catalogue (CPU) + payment (mem)",
        "sockshop:pair3": "carts (CPU) + payment (mem)",
    }
    out.append("| Fold (held-out pair) | services | chosen (alpha, eps) | separation k/n | grouped AC@1 (sum/n) | "
               "single kept k/n | hit k/n | Both@2 k | Both@5 k | both causes in stage input k | Prop. 2.1: sep <= Both@|pi| |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in lopo.iterrows():
        out.append(
            f"| {r.fold} ({r.held_out}) | {pairs[r.held_out]} | ({r.alpha}, {r.eps}) | {r.k_separated}/{r.n_conc_test} = "
            f"{f3(r.separation)} | {r.grouped_ac1_sum:g}/{r.n_conc_test} = {f3(r.grouped_ac1)} | "
            f"{r.k_single_kept}/{r.n_sf_test} = {f3(r.single_kept)} | {r.k_hit}/{r.n_sf_test} = {f3(r.hit_rate)} | "
            f"{r.k_both2} | {r.k_both5} | {r.k_both_in_stage_input}/{r.n_conc_test} | "
            f"{'holds' if r.prop21_holds_input else 'VIOLATED'} ({r.k_separated} <= {r.k_both_in_stage_input}) |")
    L = summ.loc["lopo"]
    out.append(f"| **Mean +/- SD (6 folds)** | | 6/6 (0.7, 0.4) | {f3(L.separation_mean)} +/- {f3(L.separation_sd)} | "
               f"{f3(L.grouped_ac1_mean)} +/- {f3(L.grouped_ac1_sd)} | {f3(L.single_kept_mean)} +/- {f3(L.single_kept_sd)} | "
               f"{f3(L.hit_rate_mean)} +/- {f3(L.hit_rate_sd)} | | | | |")
    out.append(f"| **Pooled held-out** | | | {int(L.sep_pooled_k)}/28 = {f3(L.sep_pooled_k / 28)} | "
               f"{L.gac_pooled * 28:g}/28 = {f3(L.gac_pooled)} | {int(L.single_kept_pooled_k)}/200 = "
               f"{f3(L.single_kept_pooled_k / 200)} | {int(L.hit_pooled_k)}/200 = {f3(L.hit_pooled_k / 200)} | "
               f"{int(L.both2_pooled_k)} | {int(L.both5_pooled_k)} | 28/28 | 6/6 folds |")
    out.append("")
    out.append("Design comparison (same grid, same selection rule, same per-case scoring):")
    out.append("")
    out.append("| design | folds | separation mean +/- SD | grouped AC@1 mean +/- SD | single kept mean +/- SD | "
               "hit mean +/- SD | pooled sep / gAC / kept / hit | params |")
    out.append("|---|---|---|---|---|---|---|---|")
    out.append(f"| published (crossval_results.csv) | 5 case-random | {f3(pub.concurrent_separation.mean())} +/- "
               f"{f3(pub.concurrent_separation.std())} | {f3(pub.concurrent_grouped_ac1.mean())} +/- "
               f"{f3(pub.concurrent_grouped_ac1.std())} | {f3(pub.single_fault_single_group.mean())} +/- "
               f"{f3(pub.single_fault_single_group.std())} | {f3(pub.single_fault_hit_rate.mean())} +/- "
               f"{f3(pub.single_fault_hit_rate.std())} | 2/28, 7.5/28, 182/200, 148/200 (implied) | 5/5 (0.7, 0.4) |")
    for d, lab in [("orig_reconstructed", "published design re-run (seed 42, GT order)"),
                   ("lopo", "**LOPO (primary)**: pairs held out; single-fault scenarios grouped"),
                   ("lopo_sfcase", "LOPO, single-fault split by case"),
                   ("g5", "grouped 5-fold (pairs kept together, seed 42)")]:
        s = summ.loc[d]
        out.append(f"| {lab} | {s.n_folds} | {f3(s.separation_mean)} +/- {f3(s.separation_sd)} | "
                   f"{f3(s.grouped_ac1_mean)} +/- {f3(s.grouped_ac1_sd)} | {f3(s.single_kept_mean)} +/- "
                   f"{f3(s.single_kept_sd)} | {f3(s.hit_rate_mean)} +/- {f3(s.hit_rate_sd)} | "
                   f"{int(s.sep_pooled_k)}/28, {s.gac_pooled * 28:g}/28, {int(s.single_kept_pooled_k)}/200, "
                   f"{int(s.hit_pooled_k)}/200 | {'all (0.7, 0.4)' if s['all_folds_0.7_0.4'] else s.params} |")
    g15 = summ[summ.index.str.startswith("g5_all15")]
    out.append(f"| grouped 5-fold, all 15 pair-merge choices | 5 each | {f3(g15.separation_mean.min())}-"
               f"{f3(g15.separation_mean.max())} (means) | {f3(g15.grouped_ac1_mean.min())}-{f3(g15.grouped_ac1_mean.max())} | "
               f"{f3(g15.single_kept_mean.min())} | {f3(g15.hit_rate_mean.min())} | 2/28, 7.5/28, 182/200, 148/200 in 15/15 | "
               f"all (0.7, 0.4) in 15/15 |")
    out.append("")

    # ---------------- CI table ----------------
    out.append("| quantity | scope | k / n | estimate | exact (Clopper-Pearson) 95% | Wilson 95% | bootstrap 95% | other |")
    out.append("|---|---|---|---|---|---|---|---|")
    for scope in ["Online Boutique", "Sock Shop", "Both systems"]:
        a = get(sc, "single-fault AC@1", scope, "Clopper-Pearson exact")
        w = get(sc, "single-fault AC@1", scope, "Wilson")
        b = get(sc, "single-fault AC@1", scope, "scenario-clustered")
        out.append(f"| single-fault AC@1 | {scope} | {a.k:g}/{a.n:g} | {f3(a.estimate)} | {ci(a.lo, a.hi)} | {ci(w.lo, w.hi)} | "
                   f"{ci(b.lo, b.hi)} (scenario-clustered) | |")
    for scope in ["Online Boutique", "Sock Shop", "Both systems"]:
        a = get(sc, "concurrent AC@2", scope, "Clopper")
        w = get(sc, "concurrent AC@2", scope, "Wilson")
        b = get(sc, "concurrent AC@2", scope, "pair-clustered")
        bc = get(sc, "concurrent AC@2", scope, "case bootstrap")
        br = get(sx, "concurrent AC@2", scope, "conservative exact")
        t = get(sx, "concurrent AC@2", scope, "cluster-robust")
        out.append(f"| concurrent AC@2 | {scope} | {a.k:g}/{a.n:g} cause slots ({int(a.n / 2)} cases) | {f3(a.estimate)} | "
                   f"{ci(a.lo, a.hi)} (slots, approx.); conservative exact bracket {ci(br.lo, br.hi)} | {ci(w.lo, w.hi)} (slots) | "
                   f"{ci(b.lo, b.hi)} (pair-clustered); {ci(bc.lo, bc.hi)} (case) | cluster-robust t {ci(t.lo, t.hi)} |")
    for scope in ["Online Boutique", "Sock Shop", "Both systems"]:
        b = get(sc, "drop: single", scope, "cluster bootstrap")
        nw = get(sx, "drop: single", scope, "Newcombe")
        lb = get(sx, "drop: single", scope, "conservative exact")
        t = get(sx, "drop: single", scope, "cluster-robust")
        out.append(f"| **drop** single AC@1 - concurrent AC@2 | {scope} | {nw.k} | {f3(b.estimate)} | "
                   f"lower bound {lb.lo:.3f} (conservative exact) | {ci(nw.lo, nw.hi)} (Newcombe, slots) | "
                   f"{ci(b.lo, b.hi)} (pair/scenario-clustered) | cluster-robust t {ci(t.lo, t.hi)}; {b.note} |")
    for q in ["Both@2", "Both@3", "Both@5", "Any@5"]:
        for scope in ["Online Boutique", "Sock Shop", "Both systems"]:
            a = get(sc, q, scope, "Clopper-Pearson exact")
            w = get(sc, q, scope, "Wilson")
            u = get(sc, q, scope, "Clopper-Pearson one-sided")
            bs = ""
            if scope == "Both systems":
                b = get(sc, q, scope, "pair-clustered")
                bs = f"{ci(b.lo, b.hi)} (pair-clustered)"
            out.append(f"| {q} | {scope} | {a.k:g}/{a.n:g} | {f3(a.estimate)} | {ci(a.lo, a.hi)} | {ci(w.lo, w.hi)} | {bs} | "
                       f"one-sided 95% upper {u.hi:.3f} |")
    for scope in ["Online Boutique", "Sock Shop", "Both systems"]:
        a = get(sx, "Any@2", scope, "Clopper")
        w = get(sx, "Any@2", scope, "Wilson")
        out.append(f"| Any@2 (post hoc helper) | {scope} | {int(float(a.k))}/{int(float(a.n))} | {f3(a.estimate)} | {ci(a.lo, a.hi)} | "
                   f"{ci(w.lo, w.hi)} | | |")
    for lab, k, n in [("separation, published 5-fold (pooled held-out; fold mean 0.073)", 2, 28),
                      ("separation, LOPO (pooled held-out; fold mean 0.067)", int(L.sep_pooled_k), 28),
                      ("single kept, LOPO pooled", int(L.single_kept_pooled_k), 200),
                      ("hit rate, LOPO pooled", int(L.hit_pooled_k), 200),
                      ("grouped AC@1, LOPO pooled (cause slots, approx.)", int(round(L.gac_pooled * 56)), 56)]:
        lo, hi = cp(k, n)
        wl, wh = wilson(k, n)
        out.append(f"| {lab} | Both systems | {k}/{n} | {f3(k / n)} | {ci(lo, hi)} | {ci(wl, wh)} | | "
                   f"one-sided 95% upper {cp_upper1(k, n):.3f} |")
    out.append("")
    out.append("| exact / permutation test | scope | table | statistic | p (one-sided) |")
    out.append("|---|---|---|---|---|")
    for _, r in st.iterrows():
        out.append(f"| {r.test} | {r.scope} | {r.table} | {r.statistic:.3f} | {r.p_value:.2g} |")
    out.append("")
    C.atomic_write_text(os.path.join(R, "tables_generated.md"), "\n".join(out) + "\n")
    print("\n".join(out))

    # ---------------- compact one-column LaTeX table ----------------
    def cpr(k, n):
        lo, hi = cp(k, n)
        return f"{lo:.2f}--{hi:.2f}"

    def r2(r):
        return f"{r.lo:.2f}--{r.hi:.2f}"

    def sci(p):
        m, e = f"{p:.1e}".split("e")
        return rf"{m}{{\times}}10^{{{int(e)}}}"

    s_ob = get(sc, "single-fault AC@1", "Online Boutique", "Clopper-Pearson exact")
    s_ss = get(sc, "single-fault AC@1", "Sock Shop", "Clopper-Pearson exact")
    sb_ob = get(sc, "single-fault AC@1", "Online Boutique", "scenario-clustered")
    sb_ss = get(sc, "single-fault AC@1", "Sock Shop", "scenario-clustered")
    cb = {s: get(sc, "concurrent AC@2", s, "pair-clustered") for s in ["Online Boutique", "Sock Shop", "Both systems"]}
    cw = {s: get(sc, "concurrent AC@2", s, "Wilson") for s in ["Online Boutique", "Sock Shop", "Both systems"]}
    d_b = get(sc, "drop: single", "Both systems", "cluster bootstrap")
    d_n = get(sx, "drop: single", "Both systems", "Newcombe")
    b2b = get(sc, "Both@2", "Both systems", "pair-clustered")
    b5b = get(sc, "Both@5", "Both systems", "pair-clustered")
    sepb = get(sx, "separation (pooled", "Both systems", "pair-clustered")
    keepb = get(sx, "single kept (pooled", "Both systems", "scenario-clustered")
    hitb = get(sx, "hit rate (pooled", "Both systems", "scenario-clustered")
    perm = st[st["test"].str.startswith("exact stratified cluster-permutation")].iloc[0]
    fish = st[(st["test"].str.contains("case level")) & (st["scope"] == "Both systems")].iloc[0]
    ks, kk, kh = int(L.sep_pooled_k), int(L.single_kept_pooled_k), int(L.hit_pooled_k)
    tex = rf"""% src: analysis/camera_ready/folds_stats/ -- stats_ci.py, stats_extra.py, grouped_cv.py, make_tables.py;
% data raw/stats_ci.csv, raw/stats_extra.csv, raw/stats_tests.csv, raw/cv_lopo_folds.csv, raw/cv_summary.csv.
% POST HOC (camera-ready) analysis; no published number changes. Exact = Clopper-Pearson for binary counts;
% for AC@2 k/n counts cause slots (2 per case) and the interval is Wilson on slots (approximate); drop = Newcombe
% (Wilson) on slots. Clustered bootstrap: pairs (concurrent) / (service, fault) scenarios (single-fault), resampled
% within system, B=20000, percentile; only 3 pairs per system, so it is coarse. Separation/kept/hit are pooled held-out
% outcomes of leave-one-pair-out CV (alpha=0.7, eps=0.4 chosen in 6/6 folds; identical pooled counts in the published
% 5-fold design). Exact test = stratified cluster-permutation test over all within-system relabelings (one-sided).
\begin{{table}}[t]
\centering\small
\caption{{Uncertainty of the main results (post hoc). For $\mathrm{{AC}}@2$, $k/n$ counts cause slots (two per case).
95\% intervals: exact (Clopper--Pearson) or Wilson, and a bootstrap that resamples whole service pairs or fault
scenarios. LOPO = leave-one-pair-out cross-validation.}}
\label{{tab:uncertainty}}
\setlength{{\tabcolsep}}{{2.5pt}}
\begin{{tabular}}{{@{{}}lcccc@{{}}}}
\toprule
\textbf{{Quantity}} & $k/n$ & \textbf{{Est.}} & \textbf{{Exact/Wilson}} & \textbf{{Clust.\ boot.}}\\
\midrule
Single $\mathrm{{AC}}@1$, Boutique & {s_ob.k:g}/{s_ob.n:g} & {s_ob.estimate:.2f} & {r2(s_ob)} & {r2(sb_ob)}\\
Single $\mathrm{{AC}}@1$, Sock Shop & {s_ss.k:g}/{s_ss.n:g} & {s_ss.estimate:.2f} & {r2(s_ss)} & {r2(sb_ss)}\\
Conc.\ $\mathrm{{AC}}@2$, Boutique & {cb['Online Boutique'].k:g}/{cb['Online Boutique'].n:g} & {cb['Online Boutique'].estimate:.3f} & {r2(cw['Online Boutique'])} & {r2(cb['Online Boutique'])}\\
Conc.\ $\mathrm{{AC}}@2$, Sock Shop & {cb['Sock Shop'].k:g}/{cb['Sock Shop'].n:g} & {cb['Sock Shop'].estimate:.3f} & {r2(cw['Sock Shop'])} & {r2(cb['Sock Shop'])}\\
Conc.\ $\mathrm{{AC}}@2$, overall & {cb['Both systems'].k:g}/{cb['Both systems'].n:g} & {cb['Both systems'].estimate:.3f} & {r2(cw['Both systems'])} & {r2(cb['Both systems'])}\\
Drop, single $-$ conc. & --- & {d_b.estimate:.2f} & {r2(d_n)} & {r2(d_b)}\\
\multicolumn{{5}}{{@{{}}l}}{{\quad exact tests: cluster perm.\ $p={sci(perm.p_value)}$; Fisher $p={sci(fish.p_value)}$}}\\
\midrule
$\mathrm{{Both}}@2$ & 2/28 & 0.071 & {cpr(2, 28)} & {r2(b2b)}\\
$\mathrm{{Both}}@5$ & 9/28 & 0.321 & {cpr(9, 28)} & {r2(b5b)}\\
Separation, LOPO & {ks}/28 & {ks / 28:.3f} & {cpr(ks, 28)} & {r2(sepb)}\\
Single kept, LOPO & {kk}/200 & {kk / 200:.2f} & {cpr(kk, 200)} & {r2(keepb)}\\
Hit rate, LOPO & {kh}/200 & {kh / 200:.2f} & {cpr(kh, 200)} & {r2(hitb)}\\
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    C.atomic_write_text(os.path.join(C.OUT, "table_folds_stats.tex"), tex)
    print(tex)


if __name__ == "__main__":
    main()
