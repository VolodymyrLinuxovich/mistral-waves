"""Heat-hazard scientific core: thresholds, indices, event detection.

This package is intentionally dependency-free (standard library only) so the
scientifically defensible core can be tested and reviewed before any heavy
geospatial stack is installed.
"""
from .detection import (
    DayRecord,
    DetectionResult,
    HeatwaveEvent,
    detect_early_signal,
    detect_events,
    detect_primary,
    detect_sensitivity_2day,
)
from .indices import (
    IndexResult,
    excess_heat_factor,
    heat_index,
    humidex,
    is_tropical_night,
)
from .thresholds import (
    ClimatologyThresholds,
    compute_thresholds,
    day_of_year_365,
    percentile_linear,
    smooth_circular,
)

__all__ = [
    "DayRecord", "DetectionResult", "HeatwaveEvent",
    "detect_events", "detect_primary", "detect_early_signal", "detect_sensitivity_2day",
    "IndexResult", "heat_index", "humidex", "is_tropical_night", "excess_heat_factor",
    "ClimatologyThresholds", "compute_thresholds", "day_of_year_365",
    "percentile_linear", "smooth_circular",
]
