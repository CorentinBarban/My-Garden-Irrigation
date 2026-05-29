"""
Library of functions for estimating reference evapotransporation (ETo) for
a grass reference crop using the FAO-56 Penman-Monteith and Hargreaves
equations. The library includes numerous functions for estimating missing
meteorological data.

:copyright: (c) 2015 by Mark Richards.
:license: BSD 3-Clause, see LICENSE.txt for more details.
"""

import math

from ._check import (
    check_day_hours as _check_day_hours,
    check_doy as _check_doy,
    check_latitude_rad as _check_latitude_rad,
    check_sol_dec_rad as _check_sol_dec_rad,
    check_sunset_hour_angle_rad as _check_sunset_hour_angle_rad,
)

#: Solar constant [ MJ m-2 min-1]
SOLAR_CONSTANT = 0.0820

# Stefan Boltzmann constant [MJ K-4 m-2 day-1]
STEFAN_BOLTZMANN_CONSTANT = 0.000000004903


def atm_pressure(altitude):
    tmp = (293.0 - (0.0065 * altitude)) / 293.0
    return math.pow(tmp, 5.26) * 101.3


def avp_from_tmin(tmin):
    return 0.611 * math.exp((17.27 * tmin) / (tmin + 237.3))


def avp_from_rhmin_rhmax(svp_tmin, svp_tmax, rh_min, rh_max):
    tmp1 = svp_tmin * (rh_max / 100.0)
    tmp2 = svp_tmax * (rh_min / 100.0)
    return (tmp1 + tmp2) / 2.0


def avp_from_rhmax(svp_tmin, rh_max):
    return svp_tmin * (rh_max / 100.0)


def avp_from_rhmean(svp_tmin, svp_tmax, rh_mean):
    return (rh_mean / 100.0) * ((svp_tmax + svp_tmin) / 2.0)


def avp_from_tdew(tdew):
    return 0.6108 * math.exp((17.27 * tdew) / (tdew + 237.3))


def avp_from_twet_tdry(twet, tdry, svp_twet, psy_const):
    return svp_twet - (psy_const * (tdry - twet))


def cs_rad(altitude, et_rad):
    return (0.00002 * altitude + 0.75) * et_rad


def daily_mean_t(tmin, tmax):
    return (tmax + tmin) / 2.0


def daylight_hours(sha):
    _check_sunset_hour_angle_rad(sha)
    return (24.0 / math.pi) * sha


def delta_svp(t):
    tmp = 4098 * (0.6108 * math.exp((17.27 * t) / (t + 237.3)))
    return tmp / math.pow((t + 237.3), 2)


def energy2evap(energy):
    return 0.408 * energy


def et_rad(latitude, sol_dec, sha, ird):
    _check_latitude_rad(latitude)
    _check_sol_dec_rad(sol_dec)
    _check_sunset_hour_angle_rad(sha)

    tmp1 = (24.0 * 60.0) / math.pi
    tmp2 = sha * math.sin(latitude) * math.sin(sol_dec)
    tmp3 = math.cos(latitude) * math.cos(sol_dec) * math.sin(sha)
    return tmp1 * SOLAR_CONSTANT * ird * (tmp2 + tmp3)


def fao56_penman_monteith(net_rad, t, ws, svp, avp, delta_svp, psy, shf=0.0):
    """
    :param t: Air temperature at 2 m height [deg Kelvin].
    """
    a1 = (0.408 * (net_rad - shf) * delta_svp /
          (delta_svp + (psy * (1 + 0.34 * ws))))
    a2 = (900 * ws / t * (svp - avp) * psy /
          (delta_svp + (psy * (1 + 0.34 * ws))))
    return a1 + a2


def hargreaves(tmin, tmax, tmean, et_rad):
    return 0.0023 * (tmean + 17.8) * (tmax - tmin) ** 0.5 * 0.408 * et_rad


def inv_rel_dist_earth_sun(day_of_year):
    _check_doy(day_of_year)
    return 1 + (0.033 * math.cos((2.0 * math.pi / 365.0) * day_of_year))


def mean_svp(tmin, tmax):
    return (svp_from_t(tmin) + svp_from_t(tmax)) / 2.0


def monthly_soil_heat_flux(t_month_prev, t_month_next):
    return 0.07 * (t_month_next - t_month_prev)


def monthly_soil_heat_flux2(t_month_prev, t_month_cur):
    return 0.14 * (t_month_cur - t_month_prev)


def net_in_sol_rad(sol_rad, albedo=0.23):
    return (1 - albedo) * sol_rad


def net_out_lw_rad(tmin, tmax, sol_rad, cs_rad, avp):
    tmp1 = (STEFAN_BOLTZMANN_CONSTANT *
        ((math.pow(tmax, 4) + math.pow(tmin, 4)) / 2))
    tmp2 = (0.34 - (0.14 * math.sqrt(avp)))
    tmp3 = 1.35 * (sol_rad / cs_rad) - 0.35
    return tmp1 * tmp2 * tmp3


def net_rad(ni_sw_rad, no_lw_rad):
    return ni_sw_rad - no_lw_rad


def psy_const(atmos_pres):
    return 0.000665 * atmos_pres


def psy_const_of_psychrometer(psychrometer, atmos_pres):
    if psychrometer == 1:
        psy_coeff = 0.000662
    elif psychrometer == 2:
        psy_coeff = 0.000800
    elif psychrometer == 3:
        psy_coeff = 0.001200
    else:
        raise ValueError(
            'psychrometer should be in range 1 to 3: {0!r}'.format(psychrometer))
    return psy_coeff * atmos_pres


def rh_from_avp_svp(avp, svp):
    return 100.0 * avp / svp


def sol_dec(day_of_year):
    _check_doy(day_of_year)
    return 0.409 * math.sin(((2.0 * math.pi / 365.0) * day_of_year - 1.39))


def sol_rad_from_sun_hours(daylight_hours, sunshine_hours, et_rad):
    _check_day_hours(sunshine_hours, 'sun_hours')
    _check_day_hours(daylight_hours, 'daylight_hours')
    return (0.5 * sunshine_hours / daylight_hours + 0.25) * et_rad


def sol_rad_from_t(et_rad, cs_rad, tmin, tmax, coastal):
    adj = 0.19 if coastal else 0.16
    sol_rad = adj * math.sqrt(tmax - tmin) * et_rad
    return min(sol_rad, cs_rad)


def sol_rad_island(et_rad):
    return (0.7 * et_rad) - 4.0


def sunset_hour_angle(latitude, sol_dec):
    _check_latitude_rad(latitude)
    _check_sol_dec_rad(sol_dec)
    cos_sha = -math.tan(latitude) * math.tan(sol_dec)
    return math.acos(min(max(cos_sha, -1.0), 1.0))


def svp_from_t(t):
    return 0.6108 * math.exp((17.27 * t) / (t + 237.3))


def wind_speed_2m(ws, z):
    return ws * (4.87 / math.log((67.8 * z) - 5.42))
