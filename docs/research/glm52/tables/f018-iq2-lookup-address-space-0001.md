# Feature 018 IQ2 Lookup Address-Space Experiment

| Variant | Samples | Median (s) | Mean (s) | Std dev (s) | Min (s) | Max (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| device | 100 | 0.000718312 | 0.000814096 | 0.000330819 | 0.000555250 | 0.002392834 |
| constant | 100 | 0.000927521 | 0.001015683 | 0.000259922 | 0.000838375 | 0.002168333 |

Constant/device median ratio: `1.291250`.
Exact candidate output identity was preserved. The device address space remains in the scaffold because the constant experiment showed no bounded benefit.

Two sequential 100-sample synthetic populations on one M1 Ultra; not a counterbalanced hardware benchmark or real-matrix result.
