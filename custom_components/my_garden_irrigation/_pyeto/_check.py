"""
Internal validation functions.

:copyright: (c) 2015 by Mark Richards.
:license: BSD 3-Clause, see LICENSE.txt for more details.
"""
from .convert import deg2rad

_MINLAT_RADIANS = deg2rad(-90.0)
_MAXLAT_RADIANS = deg2rad(90.0)
_MINSOLDEC_RADIANS = deg2rad(-23.5)
_MAXSOLDEC_RADIANS = deg2rad(23.5)
_MINSHA_RADIANS = 0.0
_MAXSHA_RADIANS = deg2rad(180)


def check_day_hours(hours, arg_name):
    if not 0 <= hours <= 24:
        raise ValueError(
            '{0} should be in range 0-24: {1!r}'.format(arg_name, hours))


def check_doy(doy):
    if not 1 <= doy <= 366:
        raise ValueError(
            'Day of the year (doy) must be in range 1-366: {0!r}'.format(doy))


def check_latitude_rad(latitude):
    if not _MINLAT_RADIANS <= latitude <= _MAXLAT_RADIANS:
        raise ValueError(
            'latitude outside valid range {0!r} to {1!r} rad: {2!r}'
            .format(_MINLAT_RADIANS, _MAXLAT_RADIANS, latitude))


def check_sol_dec_rad(sd):
    if not _MINSOLDEC_RADIANS <= sd <= _MAXSOLDEC_RADIANS:
        raise ValueError(
            'solar declination outside valid range {0!r} to {1!r} rad: {2!r}'
            .format(_MINSOLDEC_RADIANS, _MAXSOLDEC_RADIANS, sd))


def check_sunset_hour_angle_rad(sha):
    if not _MINSHA_RADIANS <= sha <= _MAXSHA_RADIANS:
        raise ValueError(
            'sunset hour angle outside valid range {0!r} to {1!r} rad: {2!r}'
            .format(_MINSHA_RADIANS, _MAXSHA_RADIANS, sha))
