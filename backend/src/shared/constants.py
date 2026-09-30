"""Bounds and defaults that more than one feature slice needs.

Per the feature-slice rules, a bound that is not specific to one slice is
imported from here rather than restated in a feature's `constants.py`, and
slices never import each other's `constants.py`. A feature that owns a value
re-exports it only when an existing import site must keep working.
"""

# Geofence coordinates. Classroom anchors (course, session) and the
# student-reported position (attendance) are the same physical limits, so all
# three slices read them from here.
LATITUDE_MIN: float = -90.0
LATITUDE_MAX: float = 90.0
LONGITUDE_MIN: float = -180.0
LONGITUDE_MAX: float = 180.0

# Attendance windows, mirrored by `core.config.Settings`
# (`default_present_window_minutes` / `default_late_window_minutes`), which
# supplies the runtime fallback when a session omits its own value. Keep the
# two in step.
DEFAULT_PRESENT_WINDOW_MINUTES: int = 5
DEFAULT_LATE_WINDOW_MINUTES: int = 10

# Term label, bounded identically by the offering create/update bodies (course)
# and the student history `?semester=` filter (attendance).
SEMESTER_MIN_LENGTH: int = 1
SEMESTER_MAX_LENGTH: int = 20
