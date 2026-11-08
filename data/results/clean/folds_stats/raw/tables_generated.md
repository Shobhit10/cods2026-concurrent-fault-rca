| Fold (held-out pair) | services | chosen (alpha, eps) | separation k/n | grouped AC@1 (sum/n) | single kept k/n | hit k/n | Both@2 k | Both@5 k | both causes in stage input k | Prop. 2.1: sep <= Both@|pi| |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 (boutique:pair1) | adservice (CPU) + cartservice (mem) | (0.7, 0.4) | 4/5 = 0.800 | 3.5/5 = 0.700 | 32/35 = 0.914 | 28/35 = 0.800 | 0 | 2 | 5/5 | holds (4 <= 5) |
| 2 (boutique:pair2) | currencyservice (CPU) + cartservice (mem) | (0.7, 0.4) | 2/5 = 0.400 | 3/5 = 0.600 | 34/35 = 0.971 | 19/35 = 0.543 | 0 | 3 | 5/5 | holds (2 <= 5) |
| 3 (boutique:pair3) | currencyservice (CPU) + productcatalogservice (mem) | (0.7, 0.4) | 3/5 = 0.600 | 1.5/5 = 0.300 | 32/35 = 0.914 | 33/35 = 0.943 | 0 | 3 | 5/5 | holds (3 <= 5) |
| 4 (sockshop:pair1) | catalogue (CPU) + carts (mem) | (0.7, 0.4) | 0/5 = 0.000 | 2.5/5 = 0.500 | 34/35 = 0.971 | 20/35 = 0.571 | 3 | 5 | 5/5 | holds (0 <= 5) |
| 5 (sockshop:pair2) | catalogue (CPU) + payment (mem) | (0.7, 0.4) | 5/5 = 1.000 | 5/5 = 1.000 | 24/30 = 0.800 | 23/30 = 0.767 | 0 | 5 | 5/5 | holds (5 <= 5) |
| 6 (sockshop:pair3) | carts (CPU) + payment (mem) | (0.7, 0.4) | 3/5 = 0.600 | 3.5/5 = 0.700 | 26/30 = 0.867 | 25/30 = 0.833 | 0 | 5 | 5/5 | holds (3 <= 5) |
| **Mean +/- SD (6 folds)** | | 6/6 (0.7, 0.4) | 0.567 +/- 0.344 | 0.633 +/- 0.234 | 0.906 +/- 0.066 | 0.743 +/- 0.156 | | | | |
| **Pooled held-out** | | | 17/30 = 0.567 | 19/30 = 0.633 | 182/200 = 0.910 | 148/200 = 0.740 | 3 | 23 | 30/30 | 6/6 folds |

Design comparison (same grid, same selection rule, same per-case scoring):

| design | folds | separation mean +/- SD | grouped AC@1 mean +/- SD | single kept mean +/- SD | hit mean +/- SD | pooled sep / gAC / kept / hit | params |
|---|---|---|---|---|---|---|---|
| published (crossval_results.csv) | 5 case-random | 0.073 +/- 0.101 | 0.277 +/- 0.132 | 0.910 +/- 0.034 | 0.740 +/- 0.055 | 2/28, 7.5/28, 182/200, 148/200 (implied) | 5/5 (0.7, 0.4) |
| published design re-run (seed 42, GT order) | 5 | 0.567 +/- 0.253 | 0.633 +/- 0.095 | 0.910 +/- 0.042 | 0.740 +/- 0.084 | 17/30, 19/30, 182/200, 148/200 | all (0.7, 0.4) |
| **LOPO (primary)**: pairs held out; single-fault scenarios grouped | 6 | 0.567 +/- 0.344 | 0.633 +/- 0.234 | 0.906 +/- 0.066 | 0.743 +/- 0.156 | 17/30, 19/30, 182/200, 148/200 | all (0.7, 0.4) |
| LOPO, single-fault split by case | 6 | 0.567 +/- 0.344 | 0.633 +/- 0.234 | 0.910 +/- 0.072 | 0.740 +/- 0.049 | 17/30, 19/30, 182/200, 148/200 | all (0.7, 0.4) |
| grouped 5-fold (pairs kept together, seed 42) | 5 | 0.620 +/- 0.286 | 0.640 +/- 0.251 | 0.910 +/- 0.052 | 0.740 +/- 0.063 | 17/30, 19/30, 182/200, 148/200 | all (0.7, 0.4) |
| grouped 5-fold, all 15 pair-merge choices | 5 each | 0.500-0.640 (means) | 0.590-0.680 | 0.910 | 0.740 | 17-17/30, 19-19/30, 182-182/200, 148-148/200 (min-max over 15) | all (0.7, 0.4) in 15/15 |

| quantity | scope | k / n | estimate | exact (Clopper-Pearson) 95% | Wilson 95% | bootstrap 95% | other |
|---|---|---|---|---|---|---|---|
| single-fault AC@1 | Online Boutique | 70/100 | 0.700 | [0.600, 0.788] | [0.604, 0.781] | [0.550, 0.840] (scenario-clustered) | |
| single-fault AC@1 | Sock Shop | 85/100 | 0.850 | [0.765, 0.914] | [0.767, 0.907] | [0.730, 0.950] (scenario-clustered) | |
| single-fault AC@1 | Both systems | 155/200 | 0.775 | [0.711, 0.831] | [0.712, 0.827] | [0.675, 0.865] (scenario-clustered) | |
| concurrent AC@2 | Online Boutique | 9/30 cause slots (15 cases) | 0.300 | [0.147, 0.494] (slots, approx.); conservative exact bracket [0.000, 0.837] | [0.167, 0.479] (slots) | [0.200, 0.400] (pair-clustered); [0.167, 0.433] (case) | cluster-robust t [0.052, 0.548] |
| concurrent AC@2 | Sock Shop | 14/30 cause slots (15 cases) | 0.467 | [0.283, 0.657] (slots, approx.); conservative exact bracket [0.043, 0.922] | [0.302, 0.639] (slots) | [0.200, 0.700] (pair-clustered); [0.300, 0.633] (case) | cluster-robust t [-0.158, 1.092] |
| concurrent AC@2 | Both systems | 23/60 cause slots (30 cases) | 0.383 | [0.261, 0.518] (slots, approx.); conservative exact bracket [0.021, 0.827] | [0.271, 0.510] (slots) | [0.250, 0.500] (pair-clustered); [0.283, 0.483] (case) | cluster-robust t [0.180, 0.587] |
| **drop** single AC@1 - concurrent AC@2 | Online Boutique | 70/100 vs 9/30 | 0.400 | lower bound -0.236 (conservative exact) | [0.197, 0.556] (Newcombe, slots) | [0.217, 0.567] (pair/scenario-clustered) | cluster-robust t [-0.016, 0.816]; bootstrap P(diff<=0) = 0.00000 |
| **drop** single AC@1 - concurrent AC@2 | Sock Shop | 85/100 vs 14/30 | 0.383 | lower bound -0.157 (conservative exact) | [0.193, 0.557] (Newcombe, slots) | [0.137, 0.650] (pair/scenario-clustered) | cluster-robust t [-0.292, 1.059]; bootstrap P(diff<=0) = 0.00050 |
| **drop** single AC@1 - concurrent AC@2 | Both systems | 155/200 vs 23/60 | 0.392 | lower bound -0.116 (conservative exact) | [0.250, 0.516] (Newcombe, slots) | [0.238, 0.547] (pair/scenario-clustered) | cluster-robust t [0.151, 0.632]; bootstrap P(diff<=0) = 0.00000 |
| Both@2 | Online Boutique | 0/15 | 0.000 | [0.000, 0.218] | [0.000, 0.204] |  | one-sided 95% upper 0.181 |
| Both@2 | Sock Shop | 3/15 | 0.200 | [0.043, 0.481] | [0.070, 0.452] |  | one-sided 95% upper 0.440 |
| Both@2 | Both systems | 3/30 | 0.100 | [0.021, 0.265] | [0.035, 0.256] | [0.000, 0.300] (pair-clustered) | one-sided 95% upper 0.239 |
| Both@3 | Online Boutique | 3/15 | 0.200 | [0.043, 0.481] | [0.070, 0.452] |  | one-sided 95% upper 0.440 |
| Both@3 | Sock Shop | 11/15 | 0.733 | [0.449, 0.922] | [0.480, 0.891] |  | one-sided 95% upper 0.903 |
| Both@3 | Both systems | 14/30 | 0.467 | [0.283, 0.657] | [0.302, 0.639] | [0.300, 0.600] (pair-clustered) | one-sided 95% upper 0.630 |
| Both@5 | Online Boutique | 8/15 | 0.533 | [0.266, 0.787] | [0.301, 0.752] |  | one-sided 95% upper 0.756 |
| Both@5 | Sock Shop | 15/15 | 1.000 | [0.782, 1.000] | [0.796, 1.000] |  | one-sided 95% upper 1.000 |
| Both@5 | Both systems | 23/30 | 0.767 | [0.577, 0.901] | [0.591, 0.882] | [0.700, 0.800] (pair-clustered) | one-sided 95% upper 0.885 |
| Any@5 | Online Boutique | 14/15 | 0.933 | [0.681, 0.998] | [0.702, 0.988] |  | one-sided 95% upper 0.997 |
| Any@5 | Sock Shop | 15/15 | 1.000 | [0.782, 1.000] | [0.796, 1.000] |  | one-sided 95% upper 1.000 |
| Any@5 | Both systems | 29/30 | 0.967 | [0.828, 0.999] | [0.833, 0.994] | [0.900, 1.000] (pair-clustered) | one-sided 95% upper 0.998 |
| Any@2 (post hoc helper) | Online Boutique | 9/15 | 0.600 | [0.323, 0.837] | [0.357, 0.802] | | |
| Any@2 (post hoc helper) | Sock Shop | 11/15 | 0.733 | [0.449, 0.922] | [0.480, 0.891] | | |
| Any@2 (post hoc helper) | Both systems | 20/30 | 0.667 | [0.472, 0.827] | [0.488, 0.808] | | |
| separation, reconstructed published 5-fold (pooled held-out; fold mean 0.567) | Both systems | 17/30 | 0.567 | [0.374, 0.745] | [0.392, 0.726] | | one-sided 95% upper 0.721 |
| separation, LOPO (pooled held-out; fold mean 0.567) | Both systems | 17/30 | 0.567 | [0.374, 0.745] | [0.392, 0.726] | | one-sided 95% upper 0.721 |
| single kept, LOPO pooled | Both systems | 182/200 | 0.910 | [0.861, 0.946] | [0.862, 0.942] | | one-sided 95% upper 0.941 |
| hit rate, LOPO pooled | Both systems | 148/200 | 0.740 | [0.673, 0.799] | [0.675, 0.796] | | one-sided 95% upper 0.791 |
| grouped AC@1, LOPO pooled (cause slots, approx.) | Both systems | 38/60 | 0.633 | [0.499, 0.754] | [0.507, 0.744] | | one-sided 95% upper 0.737 |

| exact / permutation test | scope | table | statistic | p (one-sided) |
|---|---|---|---|---|
| Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits) | Online Boutique | [[70,30],[9,21]] | 5.444 | 0.00011 |
| Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 (generous to concurrent) | Online Boutique | [[70,30],[9,6]] | 1.556 | 0.31 |
| Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits) | Sock Shop | [[85,15],[14,16]] | 6.476 | 5.1e-05 |
| Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 (generous to concurrent) | Sock Shop | [[85,15],[11,4]] | 2.061 | 0.22 |
| Fisher exact, one-sided (single AC@1 hits vs concurrent top-2 cause-slot hits) | Both systems | [[155,45],[23,37]] | 5.541 | 3e-08 |
| Fisher exact, one-sided, case level, concurrent success = at least one cause in top-2 (generous to concurrent) | Both systems | [[155,45],[20,10]] | 1.722 | 0.14 |
| exact cluster-permutation test, one-sided (all C(23,3) relabelings of 3 of 23 clusters as 'concurrent'); statistic = mean(single) - mean(concurrent) | Online Boutique | 20 scenario clusters + 3 pair clusters; 1771 relabelings | 0.400 | 0.044 |
| exact cluster-permutation test, one-sided (all C(23,3) relabelings of 3 of 23 clusters as 'concurrent'); statistic = mean(single) - mean(concurrent) | Sock Shop | 20 scenario clusters + 3 pair clusters; 1771 relabelings | 0.383 | 0.046 |
| exact stratified cluster-permutation test, one-sided (relabel within each system; statistic = pooled mean(single) - pooled mean(concurrent)) | Both systems | 3136441 relabelings | 0.392 | 0.0054 |
| case-level stratified permutation test, one-sided, Monte Carlo (200000 permutations) | Both systems | 200 single + 30 concurrent cases | 0.392 | 2e-05 |
| exact McNemar (separated vs Both@2, paired per case) | Both systems | separated-not-Both@2=17, Both@2-not-separated=3 | 14.000 | 0.0026 |

