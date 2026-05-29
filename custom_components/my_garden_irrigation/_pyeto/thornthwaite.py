"""
Calculate potential evapotranspiration using the Thornthwaite (1948 method)

:copyright: (c) 2015 by Mark Richards.
:license: BSD 3-Clause, see LICENSE.txt for more details.
"""

import calendar

from . import fao
from ._check import check_latitude_rad as _check_latitude_rad

_MONTHDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_LEAP_MONTHDAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def thornthwaite(monthly_t, monthly_mean_dlh, year=None):
    if len(monthly_t) != 12:
        raise ValueError(
            'monthly_t should be length 12 but is length {0}.'.format(len(monthly_t)))
    if len(monthly_mean_dlh) != 12:
        raise ValueError(
            'monthly_mean_dlh should be length 12 but is length {0}.'.format(len(monthly_mean_dlh)))

    if year is None or not calendar.isleap(year):
        month_days = _MONTHDAYS
    else:
        month_days = _LEAP_MONTHDAYS

    adj_monthly_t = [t * (t >= 0) for t in monthly_t]

    I = 0.0
    for Tai in adj_monthly_t:
        if Tai / 5.0 > 0.0:
            I += (Tai / 5.0) ** 1.514

    a = (6.75e-07 * I ** 3) - (7.71e-05 * I ** 2) + (1.792e-02 * I) + 0.49239

    pet = []
    for Ta, L, N in zip(adj_monthly_t, monthly_mean_dlh, month_days):
        pet.append(1.6 * (L / 12.0) * (N / 30.0) * ((10.0 * Ta / I) ** a) * 10.0)

    return pet


def monthly_mean_daylight_hours(latitude, year=None):
    _check_latitude_rad(latitude)

    if year is None or not calendar.isleap(year):
        month_days = _MONTHDAYS
    else:
        month_days = _LEAP_MONTHDAYS

    monthly_mean_dlh = []
    doy = 1
    for mdays in month_days:
        dlh = 0.0
        for daynum in range(1, mdays + 1):
            sd = fao.sol_dec(doy)
            sha = fao.sunset_hour_angle(latitude, sd)
            dlh += fao.daylight_hours(sha)
            doy += 1
        monthly_mean_dlh.append(dlh / mdays)
    return monthly_mean_dlh
