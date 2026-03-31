"""NIST GUM uncertainty propagation.

Eight named components:
  u_fit, u_repeat, u_reprod, u_align, u_cal, u_ref, u_temp, u_bias_est

Combined: u_c = sqrt(sum of squares)
Expanded: U = k * u_c (k=2 default, 95% CI)
Coverage-adjusted: U_adj = f_cov * U

See spec Section 7.5.
"""
