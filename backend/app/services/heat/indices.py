"""Heat-stress indices for the Ukraine heat-health MVP.

Every function here is deterministic, unit-explicit, and returns an
``IndexResult`` carrying the value, its unit, whether the inputs fell inside
the formula's validated range, and a short provenance note. We never silently
extrapolate a formula outside its published domain (spec section 3): out-of-range
inputs are computed but flagged ``in_valid_range=False`` so callers/UI can label
them.

Sources
-------
* Heat Index: Rothfusz, L.P. (1990), NWS Technical Attachment SR 90-23; the
  regression the U.S. National Weather Service publishes. Valid roughly for
  air temperature >= 80 degF (26.7 degC) and RH >= 40%.
* Humidex: Environment and Climate Change Canada (Masterton & Richardson 1979).
* Excess Heat Factor (EHF): Nairn, J.R. & Fawcett, R.J.B. (2015),
  "The Excess Heat Factor: A Metric for Heatwave Intensity...", IJERPH 12(1).
* Tropical night: WMO / ETCCDI convention (Tmin >= 20 degC) plus a local TN90
  trigger (spec section 2).

Units are SI (degrees Celsius) at the public interface. Fahrenheit is used only
inside the Heat Index intermediate math, matching the published formula.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class IndexResult:
    """A single computed index value with unit, validity flag and provenance."""

    value: Optional[float]
    unit: str
    in_valid_range: bool
    source: str
    note: str = ""


def _c_to_f(t_c: float) -> float:
    return t_c * 9.0 / 5.0 + 32.0


def _f_to_c(t_f: float) -> float:
    return (t_f - 32.0) * 5.0 / 9.0


def heat_index(t_c: float, rh_pct: float) -> IndexResult:
    """NWS Heat Index (apparent temperature in shade), returned in degrees C.

    Implements the Rothfusz regression with the two NWS correction terms and
    the low-heat fallback (the simple average form) used when conditions are
    mild. Inputs outside the validated domain (T < 26.7 degC or RH < 40%) are
    still computed via the simple form but flagged out-of-range.
    """
    if rh_pct < 0 or rh_pct > 100:
        raise ValueError(f"relative humidity must be 0-100%, got {rh_pct}")

    t_f = _c_to_f(t_c)
    # Simple form (Steadman-based) used by NWS as the first gate.
    hi_simple = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh_pct * 0.094))

    if (hi_simple + t_f) / 2.0 < 80.0:
        # Mild conditions: the full regression is not applicable; report the
        # simple estimate and flag as out of the "hot" validity domain.
        return IndexResult(
            value=round(_f_to_c(hi_simple), 2),
            unit="degC",
            in_valid_range=False,
            source="NWS Rothfusz 1990 (simple form)",
            note="Below Heat Index validity threshold (~26.7 degC); apparent temp ~ air temp.",
        )

    t, r = t_f, rh_pct
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )
    # NWS adjustments at the humidity extremes.
    if r < 13 and 80 <= t <= 112:
        hi -= ((13 - r) / 4.0) * math.sqrt((17 - abs(t - 95.0)) / 17.0)
    elif r > 85 and 80 <= t <= 87:
        hi += ((r - 85) / 10.0) * ((87 - t) / 5.0)

    in_range = t_c >= 26.7 and rh_pct >= 40
    return IndexResult(
        value=round(_f_to_c(hi), 2),
        unit="degC",
        in_valid_range=in_range,
        source="NWS Rothfusz 1990",
        note="Shade apparent temperature; not for direct-sun or occupational limits.",
    )


def humidex(t_c: float, dewpoint_c: float) -> IndexResult:
    """Environment Canada Humidex, returned as a dimensionless index (degC-like)."""
    dew_k = dewpoint_c + 273.16
    # Saturation vapour pressure at the dew point (hPa).
    e = 6.11 * math.exp(5417.7530 * ((1.0 / 273.16) - (1.0 / dew_k)))
    h = t_c + 0.5555 * (e - 10.0)
    # EC only reports humidex when it exceeds the air temperature meaningfully.
    in_range = t_c >= 20.0 and dewpoint_c <= t_c
    return IndexResult(
        value=round(h, 2),
        unit="index(degC-equivalent)",
        in_valid_range=in_range,
        source="Environment Canada (Masterton & Richardson 1979)",
        note="Comfort index; requires dew point <= air temperature.",
    )


def is_tropical_night(tmin_c: Optional[float], tn90_c: Optional[float] = None,
                      absolute_c: float = 20.0) -> Optional[bool]:
    """Tropical-night flag: Tmin >= absolute (default 20 degC) OR Tmin > local TN90.

    Returns None when Tmin is missing (never coerce missing to False).
    """
    if tmin_c is None:
        return None
    if tmin_c >= absolute_c:
        return True
    if tn90_c is not None and tmin_c > tn90_c:
        return True
    return False


def excess_heat_factor(
    daily_mean_series: Sequence[Optional[float]],
    index: int,
    t95_daily_mean: float,
) -> IndexResult:
    """Excess Heat Factor for the day at ``index`` (Nairn & Fawcett 2015).

    EHF = EHI_sig * max(1, EHI_accl), units degC^2, where:
      * EHI_sig  = (3-day mean of daily-mean T ending today) - T95
      * EHI_accl = (that 3-day mean) - (mean of the preceding 30 days)
      * T95 is the 95th percentile of daily-mean temperature over the baseline.

    Needs today plus the two prior days for the significance term and 30 prior
    days for the acclimatisation term. Returns value=None (flagged) when the
    required window contains missing data or runs off the start of the series.
    """
    if index < 32:
        return IndexResult(None, "degC^2", False, "Nairn & Fawcett 2015",
                           "Insufficient lead-in (need 32 prior days).")

    three = daily_mean_series[index - 2 : index + 1]
    thirty = daily_mean_series[index - 32 : index - 2]
    if any(v is None for v in three) or any(v is None for v in thirty):
        return IndexResult(None, "degC^2", False, "Nairn & Fawcett 2015",
                           "Missing values inside EHF window.")

    ehi_sig = (sum(three) / 3.0) - t95_daily_mean
    ehi_accl = (sum(three) / 3.0) - (sum(thirty) / 30.0)
    ehf = ehi_sig * max(1.0, ehi_accl)
    return IndexResult(
        value=round(ehf, 3),
        unit="degC^2",
        in_valid_range=True,
        source="Nairn & Fawcett 2015",
        note="Positive EHF indicates heatwave conditions relative to local climate.",
    )
