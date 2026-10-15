"""Numeric validation with named errors and finite bounds."""
from __future__ import annotations

import math
from numbers import Integral, Real


def finite(name: str, value: object, *, minimum: float | None = None,
           maximum: float | None = None) -> float:
    """Return a finite number within inclusive bounds; reject booleans and strings."""
    if type(value) not in (int, float) and (isinstance(value, bool) or not isinstance(value, Real)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return result


def positive(name: str, value: object) -> float:
    """Return a finite number greater than zero."""
    result = finite(name, value)
    if result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def nonnegative(name: str, value: object) -> float:
    """Return a finite number greater than or equal to zero."""
    return finite(name, value, minimum=0.0)


def fraction(name: str, value: object) -> float:
    """Return a finite fraction in the inclusive interval [0, 1]."""
    return finite(name, value, minimum=0.0, maximum=1.0)


def positive_int(name: str, value: object) -> int:
    """Return a positive integer; reject booleans and floating point values."""
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)
