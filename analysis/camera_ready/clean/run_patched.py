"""
run_patched.py -- runs an UNMODIFIED camera-ready script from R/analysis/camera_ready/folds_stats with a small,
listed set of in-memory text substitutions that remove the hard-coded published case count (28 usable concurrent
cases; the corrected set has 30, none excluded by the paper's rule) and, in make_tables.py, the published counts
typed as literals (Both@2 2/28, Both@5 9/28, separation 2/28, fold means 0.073/0.067), which are replaced by the
values read from the raw/*.csv files of this run. The script file on disk is never touched.
Every substitution must match exactly the stated number of times, otherwise the run aborts.

Usage: python run_patched.py grouped_cv
"""
import os
import sys

sys.dont_write_bytecode = True

FS = os.path.join(os.environ.get("CODS_REPO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")),
                  "analysis", "camera_ready", "folds_stats")

# (old text, new text, expected number of matches). Only case counts / hard-coded published counts change; every
# formula, seed, grid, selection rule and the pinned setting (alpha=0.7, eps=0.4) stay as written. The pinned setting
# is valid for the corrected set: grouped_cv.py (patched) selects (0.7, 0.4) in every fold of every design.
PATCHES = {
    # verify.py hard-fails (KeyError) because the published per-case CSVs lack the 2 cases the paper excluded
    # (sockshop pair1_rep2, pair3_rep4), which are usable in the corrected set. Strict .loc -> .reindex, so the
    # missing published rows become NaN and the affected per-case checks show MISMATCH instead of crashing.
    "verify": [
        ('stored_src.loc[sub["case_id"], m]', 'stored_src.reindex(sub["case_id"])[m]', 1),
        ('srr.loc[conc["case_id"], "both3"]', 'srr.reindex(conc["case_id"])["both3"]', 1),
        ('rq1.loc[conc["case_id"], col]', 'rq1.reindex(conc["case_id"])[col]', 1),
        ('srr.loc[conc["case_id"], col]', 'srr.reindex(conc["case_id"])[col]', 1),
        ('ft.loc[conc["case_id"], ["r_cpu", "r_mem", "n"]]', 'ft.reindex(conc["case_id"])[["r_cpu", "r_mem", "n"]]', 1),
        ('srn.loc[conc["case_id"], m[3:]]', 'srn.reindex(conc["case_id"])[m[3:]]', 1),
    ],
    "grouped_cv": [("assert len(conc) == 28, len(conc)", "assert len(conc) > 0, len(conc)", 1)],
    "stats_ci": [
        ("assert len(conc) == 28 and len(sf) == 200", "assert len(conc) > 0 and len(sf) == 200", 1),
        ('k_sep, 28, "fold-mean reported in paper = 0.073; pooled = k/28")',
         'k_sep, len(conc), "corrected set; pooled = k/30 (fold means: raw/cv_summary.csv)")', 1),
        ('"Both systems", k_lopo, 28)', '"Both systems", k_lopo, len(conc))', 1),
        ('"note": "no evidence that separation differs from Both@2; per-case sets differ"',
         '"note": "corrected set; see p_value"', 1),
    ],
    "stats_extra": [
        ("assert len(conc) == 28 and len(sf) == 200", "assert len(conc) > 0 and len(sf) == 200", 1),
        ('cc, "pair", 28)', 'cc, "pair", len(conc))', 2),
        ('{len(sep)}/28;', '{len(sep)}/{len(conc)};', 1),
        ("{int(pc['both_in_input'].sum())}/28 ", "{int(pc['both_in_input'].sum())}/{len(conc)} ", 1),
        ('"n": 28})', '"n": len(conc)})', 1),
        (".iloc[0])}/28; over 1000 seeds", ".iloc[0])}/{len(conc)}; over 1000 seeds", 1),
        ("max {lk.iloc[:, 1].max()} of 28", "max {lk.iloc[:, 1].max()} of {len(conc)}", 1),
    ],
    "make_tables": [
        ('    L = summ.loc["lopo"]\n', '    L = summ.loc["lopo"]\n    NC = int(L.conc_n)\n', 1),
        ("{int(L.sep_pooled_k)}/28 = {f3(L.sep_pooled_k / 28)}", "{int(L.sep_pooled_k)}/{NC} = {f3(L.sep_pooled_k / NC)}", 1),
        ("{L.gac_pooled * 28:g}/28 = ", "{L.gac_pooled * NC:g}/{NC} = ", 1),
        ("| 28/28 | 6/6 folds |", "| {int(lopo.k_both_in_stage_input.sum())}/{NC} | "
                                  "{int(lopo.prop21_holds_input.sum())}/{len(lopo)} folds |", 1),
        ("{int(s.sep_pooled_k)}/28, {s.gac_pooled * 28:g}/28,", "{int(s.sep_pooled_k)}/{NC}, {s.gac_pooled * NC:g}/{NC},", 1),
        ("| 2/28, 7.5/28, 182/200, 148/200 in 15/15 | ",
         "| {int(g15.sep_pooled_k.min())}-{int(g15.sep_pooled_k.max())}/{NC}, "
         "{g15.gac_pooled.min() * NC:g}-{g15.gac_pooled.max() * NC:g}/{NC}, "
         "{int(g15.single_kept_pooled_k.min())}-{int(g15.single_kept_pooled_k.max())}/200, "
         "{int(g15.hit_pooled_k.min())}-{int(g15.hit_pooled_k.max())}/200 (min-max over 15) | ", 1),
        ('("separation, published 5-fold (pooled held-out; fold mean 0.073)", 2, 28)',
         '(f"separation, reconstructed published 5-fold (pooled held-out; fold mean '
         '{summ.loc[\'orig_reconstructed\'].separation_mean:.3f})", int(summ.loc["orig_reconstructed"].sep_pooled_k), NC)', 1),
        ('("separation, LOPO (pooled held-out; fold mean 0.067)", int(L.sep_pooled_k), 28)',
         '(f"separation, LOPO (pooled held-out; fold mean {L.separation_mean:.3f})", int(L.sep_pooled_k), NC)', 1),
        ("int(round(L.gac_pooled * 56)), 56)", "int(round(L.gac_pooled * 2 * NC)), 2 * NC)", 1),
        ("& 2/28 & 0.071 & {cpr(2, 28)} &", "& {b2b.k:g}/{b2b.n:g} & {b2b.estimate:.3f} & {cpr(int(b2b.k), int(b2b.n))} &", 1),
        ("& 9/28 & 0.321 & {cpr(9, 28)} &", "& {b5b.k:g}/{b5b.n:g} & {b5b.estimate:.3f} & {cpr(int(b5b.k), int(b5b.n))} &", 1),
        ("& {ks}/28 & {ks / 28:.3f} & {cpr(ks, 28)} &", "& {ks}/{NC} & {ks / NC:.3f} & {cpr(ks, NC)} &", 1),
    ],
}


def main():
    name = sys.argv[1]
    path = os.path.join(FS, name + ".py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    for old, new, n in PATCHES[name]:
        got = src.count(old)
        if got != n:
            raise SystemExit(f"patch '{old}' matched {got} times, expected {n}")
        src = src.replace(old, new)
        print(f"[run_patched] {name}.py: replaced {n}x {old!r} -> {new!r}", flush=True)
    sys.path.insert(0, FS)
    g = {"__name__": "__main__", "__file__": path}
    exec(compile(src, path, "exec"), g)


if __name__ == "__main__":
    main()
