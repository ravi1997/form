"""
stats_utils.py
--------------
Pure-Python implementations of advanced statistical distributions
(Chi-Squared and Student-t) to compute p-values without scipy.
"""

from __future__ import annotations
import math

def normal_cdf(z: float) -> float:
    """Standard Normal Cumulative Distribution Function (CDF)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def chi2_p_value(chi2: float, df: int) -> float:
    """
    Returns the p-value (right-tailed probability) for a Chi-Squared distribution.
    Uses the Wilson-Hilferty approximation for high accuracy.
    """
    if chi2 <= 0:
        return 1.0
    if df <= 0:
        return 1.0

    # Wilson-Hilferty transformation: converts Chi-Squared variable to Standard Normal
    tmp_a = chi2 / df
    tmp_b = 2.0 / (9.0 * df)
    
    # Wilson-Hilferty formula
    numerator = (tmp_a ** (1.0/3.0)) - (1.0 - tmp_b)
    denominator = math.sqrt(tmp_b)
    
    if denominator == 0:
        return 1.0
        
    z = numerator / denominator
    
    # Return 1 - normal_cdf(z) for right-tail p-value
    return 1.0 - normal_cdf(z)


def student_t_p_value(t: float, df: float) -> float:
    """
    Returns the two-tailed p-value for Student's t-distribution.
    Uses the Hill-Davis standard normal approximation.
    """
    t_abs = abs(t)
    if df <= 0:
        return 1.0

    # Hill-Davis approximation for Student's t to Standard Normal
    # Ref: Hill (1970) / Davis (1973)
    a = 1.0 - 1.0 / (4.0 * df)
    b = t_abs / math.sqrt(df)
    
    # Check for division safety
    denom = 1.0 + (b ** 2) / (2.0 * df)
    if denom <= 0:
        return 1.0
        
    z = b * a * math.sqrt(1.0 / denom)
    
    # Two-tailed probability
    p_one_tail = 1.0 - normal_cdf(z)
    return min(1.0, p_one_tail * 2.0)


def f_p_value(f: float, df1: int, df2: int) -> float:
    """
    Returns the right-tailed p-value for the F-distribution using the Li-Chen (2012) normal approximation.
    """
    if f <= 0 or df1 <= 0 or df2 <= 0:
        return 1.0

    # Li-Chen transformation parameters
    term_a = 2.0 / (9.0 * df1)
    term_b = 2.0 / (9.0 * df2)
    
    # Calculate transform
    val_a = f ** (1.0 / 3.0)
    numerator = val_a * (1.0 - term_b) - (1.0 - term_a)
    denominator = math.sqrt(term_a + (val_a ** 2) * term_b)
    
    if denominator == 0:
        return 1.0
        
    z = numerator / denominator
    return 1.0 - normal_cdf(z)

