## Concurrent faults (n = 30 cases; metric-level lists, paper definitions)

| Ranker | AC@1 | AC@2 | AC@3 | AC@5 | Both@2 [95% CI] | Both@5 [95% CI] | Any@5 [95% CI] | Both@all (list) | mean list length |
|---|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 0.317 | 0.717 | 0.833 | 0.950 | 0.467 [0.28, 0.66] | 0.900 [0.73, 0.98] | 1.000 [0.88, 1.00] | 1.000 | 15.5 |
| N-Sigma | 0.133 | 0.400 | 0.617 | 0.800 | 0.100 [0.02, 0.27] | 0.633 [0.44, 0.80] | 0.967 [0.83, 1.00] | 1.000 | 15.5 |
| PageRank (graph) | 0.250 | 0.250 | 0.250 | 0.517 | 0.000 [0.00, 0.12] | 0.200 [0.08, 0.39] | 0.833 [0.65, 0.94] | 1.000 | 15.5 |
| CIRCA (causal) | 0.217 | 0.450 | 0.567 | 0.800 | 0.133 [0.04, 0.31] | 0.667 [0.47, 0.83] | 0.933 [0.78, 0.99] | 1.000 | 15.5 |
| CIRCA, RCAEval defaults | 0.200 | 0.400 | 0.567 | 0.800 | 0.100 [0.02, 0.27] | 0.600 [0.41, 0.77] | 1.000 [0.88, 1.00] | 1.000 | 13.7 |
| RCD (causal) (10 seeds) | 0.198 ± 0.024 | 0.373 ± 0.038 | 0.483 ± 0.036 | 0.553 ± 0.036 | 0.097 ± 0.040 | 0.287 ± 0.063 | 0.820 ± 0.042 | 0.317 ± 0.067 | 3.1 |
| Random ranking | 0.268 | 0.475 | 0.631 | 0.829 | 0.165 | 0.681 | 0.976 | 1.000 | 15.5 |

### Stage (released cluster_candidates_v2, alpha=0.7, eps=0.4, minPts=2) on each ranker's list

k_in = entries the stage partitions; Prop. 2.1 bound = Both@k_in (fraction of cases with both causes among those entries); violations = cases separated although a cause is missing from the input.

| Ranker | input | k_in | separation [95% CI] | bound Both@k_in | ≤ Both@2? | violations | grouped AC@1 | separation, suffix-aware svc mapping | oracle-grid max sep. (α,ε) |
|---|---|---|---|---|---|---|---|---|---|
| Robust (paper) | full | 15.5 | 0.067 [0.01, 0.22] | 1.000 | yes | 0 | 0.350 | 0.033 | 0.067 (0.7, 0.40); 0/15 settings > Both@2 |
| Robust (paper) | top10 | 10.0 | 0.067 [0.01, 0.22] | 0.967 | yes | 0 | 0.333 | 0.033 | 0.067 (0.7, 0.40); 0/15 settings > Both@2 |
| Robust (paper) | top5 | 5.0 | 0.033 [0.00, 0.17] | 0.900 | yes | 0 | 0.333 | 0.033 | 0.033 (0.7, 0.40); 0/15 settings > Both@2 |
| N-Sigma | full | 15.5 | 0.033 [0.00, 0.17] | 1.000 | yes | 0 | 0.150 | 0.033 | 0.467 (0.3, 0.30); 14/15 settings > Both@2 |
| N-Sigma | top10 | 10.0 | 0.033 [0.00, 0.17] | 1.000 | yes | 0 | 0.150 | 0.033 | 0.033 (0.3, 0.10); 0/15 settings > Both@2 |
| N-Sigma | top5 | 5.0 | 0.033 [0.00, 0.17] | 0.633 | yes | 0 | 0.133 | 0.033 | 0.033 (0.7, 0.40); 0/15 settings > Both@2 |
| PageRank (graph) | full | 15.5 | 0.067 [0.01, 0.22] | 1.000 | NO | 0 | 0.017 | 0.033 | 0.067 (0.7, 0.40); 14/15 settings > Both@2 |
| PageRank (graph) | top10 | 10.0 | 0.033 [0.00, 0.17] | 0.633 | NO | 0 | 0.017 | 0.033 | 0.033 (0.7, 0.40); 1/15 settings > Both@2 |
| PageRank (graph) | top5 | 5.0 | 0.000 [0.00, 0.12] | 0.200 | yes | 0 | 0.017 | 0.000 | 0.000 (0.3, 0.10); 0/15 settings > Both@2 |
| CIRCA (causal) | full | 15.5 | 0.000 [0.00, 0.12] | 1.000 | yes | 0 | 0.233 | 0.000 | 0.433 (0.3, 0.30); 14/15 settings > Both@2 |
| CIRCA (causal) | top10 | 10.0 | 0.000 [0.00, 0.12] | 1.000 | yes | 0 | 0.233 | 0.000 | 0.133 (0.3, 0.30); 0/15 settings > Both@2 |
| CIRCA (causal) | top5 | 5.0 | 0.000 [0.00, 0.12] | 0.667 | yes | 0 | 0.217 | 0.033 | 0.033 (0.3, 0.30); 0/15 settings > Both@2 |
| CIRCA, RCAEval defaults | full | 13.7 | 0.033 [0.00, 0.17] | 1.000 | yes | 0 | 0.233 | 0.000 | 0.633 (0.3, 0.30); 14/15 settings > Both@2 |
| CIRCA, RCAEval defaults | top10 | 9.8 | 0.067 [0.01, 0.22] | 0.933 | yes | 0 | 0.233 | 0.000 | 0.300 (0.3, 0.10); 14/15 settings > Both@2 |
| CIRCA, RCAEval defaults | top5 | 5.0 | 0.000 [0.00, 0.12] | 0.600 | yes | 0 | 0.233 | 0.000 | 0.067 (0.3, 0.10); 0/15 settings > Both@2 |
| RCD (causal) | full | 3.1 | 0.007 ± 0.014 | 0.317 ± 0.067 | yes | 0 | 0.175 ± 0.024 | 0.007 ± 0.014 | 0.007 (0.7, 0.40); 0/15 settings > Both@2 |
| RCD (causal) | top10 | 3.1 | 0.007 ± 0.014 | 0.317 ± 0.067 | yes | 0 | 0.175 ± 0.024 | 0.007 ± 0.014 | 0.007 (0.7, 0.40); 0/15 settings > Both@2 |
| RCD (causal) | top5 | 2.9 | 0.007 ± 0.014 | 0.287 ± 0.063 | yes | 0 | 0.175 ± 0.024 | 0.007 ± 0.014 | 0.007 (0.7, 0.40); 0/15 settings > Both@2 |
| Random ranking | full | 15.5 | 0.027 | 1.000 | yes | 0 | 0.264 | 0.005 | – |
| Random ranking | top10 | 10.0 | 0.027 | 0.962 | yes | 0 | 0.264 | 0.004 | – |
| Random ranking | top5 | 5.0 | 0.010 | 0.673 | yes | 0 | 0.259 | 0.003 | – |

### Below chance? P(X ≤ observed) under a uniformly random ranking of the same candidates (Poisson-binomial over the 28 exact per-case probabilities)

| Ranker | Both@2 obs / E_random (p) | Both@5 obs / E_random (p) | Any@5 obs / E_random (p) |
|---|---|---|---|
| Robust (paper) | 14 / 4.9 (p = 1) | 27 / 20.4 (p = 0.999) | 30 / 29.3 (p = 1) |
| N-Sigma | 3 / 4.9 (p = 0.242) | 19 / 20.4 (p = 0.34) | 29 / 29.3 (p = 0.515) |
| PageRank (graph) | 0 / 4.9 (p = 0.00397) | 6 / 20.4 (p = 4.41e-09) | 25 / 29.3 (p = 0.000447) |
| CIRCA (causal) | 4 / 4.9 (p = 0.432) | 20 / 20.4 (p = 0.505) | 28 / 29.3 (p = 0.155) |
| CIRCA, RCAEval defaults | 3 / 4.9 (p = 0.242) | 18 / 20.4 (p = 0.203) | 30 / 29.3 (p = 1) |
| RCD (causal) | 2.9 (seeds 1–4) / 4.9 (median p 0.432) | 8.6 (seeds 5–11) / 20.4 (median p 3.31e-06) | 24.6 (seeds 23–26) / 29.3 (median p 0.000447) |

### Service-level lists (each service once, first occurrence)

| Ranker | svc AC@1 | svc AC@2 | svc Both@2 | svc Both@3 | svc Both@5 | svc Any@1 | svc Any@2 | svc Any@5 |
|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 0.317 | 0.733 | 0.500 | 0.767 | 1.000 | 0.633 | 0.967 | 1.000 |
| N-Sigma | 0.133 | 0.483 | 0.167 | 0.600 | 1.000 | 0.267 | 0.800 | 1.000 |
| PageRank (graph) | 0.250 | 0.500 | 0.200 | 0.600 | 1.000 | 0.500 | 0.800 | 1.000 |
| CIRCA (causal) | 0.217 | 0.500 | 0.200 | 0.667 | 1.000 | 0.433 | 0.800 | 1.000 |
| CIRCA, RCAEval defaults | 0.200 | 0.417 | 0.100 | 0.600 | 1.000 | 0.400 | 0.733 | 1.000 |
| RCD (causal) | 0.198 ± 0.024 | 0.418 ± 0.024 | 0.107 ± 0.038 | 0.253 ± 0.067 | 0.317 ± 0.067 | 0.397 ± 0.048 | 0.730 ± 0.043 | 0.827 ± 0.041 |
| Random ranking | 0.267 | 0.533 | 0.217 | 0.650 | 1.000 | 0.533 | 0.850 | 1.000 |
| pagerank_all_graph_nodes (original run_graph_ranker.py design) | 0.000 | 0.183 | 0.000 | 0.000 | 0.533 | 0.000 | 0.367 | 1.000 |
| deviation_service_max (original run_graph_ranker.py design) | 0.333 | 0.733 | 0.500 | 0.767 | 1.000 | 0.667 | 0.967 | 1.000 |

### Per system (AC@2 / Both@2 / Both@5 / Any@5)

| Ranker | Online Boutique (15) | Sock Shop (13) |
|---|---|---|
| Robust (paper) | 0.567 / 0.200 / 0.800 / 1.000 | 0.867 / 0.733 / 1.000 / 1.000 |
| N-Sigma | 0.267 / 0.000 / 0.267 / 0.933 | 0.533 / 0.200 / 1.000 / 1.000 |
| PageRank (graph) | 0.100 / 0.000 / 0.000 / 0.667 | 0.400 / 0.000 / 0.400 / 1.000 |
| CIRCA (causal) | 0.333 / 0.067 / 0.467 / 0.867 | 0.567 / 0.200 / 0.867 / 1.000 |
| CIRCA, RCAEval defaults | 0.267 / 0.067 / 0.333 / 1.000 | 0.533 / 0.133 / 0.867 / 1.000 |
| RCD (causal) | 0.250 / 0.007 / 0.120 / 0.693 | 0.497 / 0.187 / 0.453 / 0.947 |
| Random ranking | 0.373 / 0.087 / 0.504 / 0.953 | 0.576 / 0.242 / 0.859 / 1.000 |

Runtime per case (s, mean): Robust (paper) 0.02, N-Sigma 0.01, PageRank (graph) 0.01, CIRCA (causal) 0.74, CIRCA, RCAEval defaults 0.73, RCD (causal) 2.88; bocpd 0.11.

## Collapse per ranker: single-fault AC@1 (paired subset, 80 cases) vs concurrent AC@2 (28 cases)

Skill = (AC − AC_random)/(1 − AC_random): 0 = chance level, 1 = perfect, < 0 = below chance; the two settings have very different chance levels, so skill is the like-for-like comparison.

| Ranker | single AC@1 | single skill | concurrent AC@2 | concurrent skill | concurrent Both@2 |
|---|---|---|---|---|---|
| Robust (paper) | 0.762 | +0.74 | 0.717 | +0.46 | 0.467 |
| N-Sigma | 0.700 | +0.67 | 0.400 | -0.14 | 0.100 |
| PageRank (graph) | 0.075 | -0.02 | 0.250 | -0.43 | 0.000 |
| CIRCA (causal) | 0.550 | +0.50 | 0.450 | -0.05 | 0.133 |
| RCD (causal) | 0.237 | +0.16 | 0.373 | -0.19 | 0.097 |
| Random ranking | 0.095 | +0.00 | 0.475 | +0.00 | 0.165 |

## Single fault — all 200 cases

| Ranker | n | AC@1 [95% CI] | AC@3 | AC@5 | Boutique AC@1 | Sock Shop AC@1 | stage: kept one group | stage: hit |
|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 200 | 0.775 [0.71, 0.83] | 0.935 | 0.970 | 0.700 | 0.850 | 0.910 | 0.740 |
| N-Sigma | 200 | 0.605 [0.53, 0.67] | 0.860 | 0.910 | 0.520 | 0.690 | 0.910 | 0.590 |
| PageRank (graph) | 200 | 0.105 [0.07, 0.16] | 0.155 | 0.160 | 0.100 | 0.110 | 0.910 | 0.150 |
| CIRCA (causal) | 80 | 0.550 [0.43, 0.66] | 0.875 | 0.925 | 0.375 | 0.725 | 0.938 | 0.487 |
| RCD (causal) | 80 | 0.237 [0.15, 0.35] | 0.425 | 0.487 | 0.150 | 0.325 | 1.000 | 0.225 |
| Random ranking | 200 | 0.095 | 0.264 | 0.406 | 0.092 | 0.099 | – | – |

## Single fault — paired subset, 80 cases (reps 1,2 of every service x fault)

| Ranker | n | AC@1 [95% CI] | AC@3 | AC@5 | Boutique AC@1 | Sock Shop AC@1 | stage: kept one group | stage: hit |
|---|---|---|---|---|---|---|---|---|
| Robust (paper) | 80 | 0.762 [0.65, 0.85] | 0.925 | 0.950 | 0.650 | 0.875 | 0.938 | 0.713 |
| N-Sigma | 80 | 0.700 [0.59, 0.80] | 0.887 | 0.912 | 0.575 | 0.825 | 0.938 | 0.650 |
| PageRank (graph) | 80 | 0.075 [0.03, 0.16] | 0.138 | 0.138 | 0.050 | 0.100 | 0.938 | 0.113 |
| CIRCA (causal) | 80 | 0.550 [0.43, 0.66] | 0.875 | 0.925 | 0.375 | 0.725 | 0.938 | 0.487 |
| RCD (causal) | 80 | 0.237 [0.15, 0.35] | 0.425 | 0.487 | 0.150 | 0.325 | 1.000 | 0.225 |
| Random ranking | 80 | 0.095 | 0.264 | 0.406 | 0.091 | 0.099 | – | – |
