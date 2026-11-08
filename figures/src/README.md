# Figure sources

These are the TikZ / pgfplots sources of the paper's figures and of the body of Algorithm 1.
The paper's PDF includes each figure as a PDF that was typeset from exactly these sources.
The numbers drawn in the charts are typed into the sources; the table below says where each number comes from.
Paths are relative to the repository root.

| File | Paper | Kind | Numbers come from |
|---|---|---|---|
| `fig-problem.tikz` | Figure 1 | problem statement | case counts: 30 (`data/concurrent_clean/`), 138 (`data/larger_set/`), 200 single-fault cases (BARO) |
| `fig-pipeline.tikz` | Figure 2 | schematic | - |
| `alg-pipeline.tikz` | Algorithm 1 (body) | pseudocode | - |
| `fig-arch.tikz` | Figure 3 | schematic | - |
| `fig-rq1.tikz` | Figure 4 | bar chart | single-fault AC@1 0.70 / 0.85: `data/results/clean/folds_stats/raw/stats_ci.csv`; concurrent AC@2 0.300 / 0.467: `data/results/clean/folds_stats/raw/corrected_table1_nsigma.csv` (or `analysis/camera_ready/clean/case_numbers.py`) |
| `fig-bound.tikz` | Figure 5 | bar chart | Both@2 0.100, Both@3 0.467, Both@5 0.767, Any@5 0.967: `data/results/clean/folds_stats/raw/corrected_table1_nsigma.csv` (or `case_numbers.py`) |
| `fig-scale.tikz` | Figure 6 | line chart | `data/results/clean/scale_network/scale_plot_data.csv` (the coordinates are also written to `scale_fig_snippet.tex`) |
| `fig-rq3.tikz` | Figure 7 | bar chart | 0.0: `data/results/merged/core/folds_stats/raw/verification.csv` (first, rank-position design); 0.910: `data/results/merged/core/folds_stats/raw/cv_summary.csv` (cross-validation on the merged format, as in Table 3; single-fault cases only, so `data/results/clean/` gives the same values) |
| `fig-hero.tikz` | Figure 8 | summary graphic | numbers of Figures 4, 5 and 7 |
| `fig-case.tikz` | Figure 9 | case study | ranked list of case `boutique_cpu-mem_pair3_rep5`: field `ranked` of `data/results/clean/folds_stats/raw/cases/conc__boutique_cpu-mem_pair3_rep5.json` (printed by `case_numbers.py`) |

The sources match the figures of the published paper.

`preamble.tex` holds the packages, colours and styles that the sources need.

To typeset one figure on its own, put this in a file next to the sources and compile it with `pdflatex`:

```latex
\documentclass[sigconf]{acmart}
\input{preamble.tex}
\begin{document}
\input{fig-rq1.tikz}
\end{document}
```

`alg-pipeline.tikz` must be placed inside an `algorithm` environment. It refers to the paper's Equation `eq:dist`,
and `fig-problem.tikz` and `fig-arch.tikz` refer to the ranking bound (Proposition 3.1, label `prop:bound`), so on
their own they print `??` for those references.
