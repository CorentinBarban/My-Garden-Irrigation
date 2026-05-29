"""
Unit conversion functions.

:copyright: (c) 2015 by Mark Richards.
:license: BSD 3-Clause, see LICENSE.txt for more details.
"""

import math


def celsius2kelvin(celsius):
    return celsius + 273.15


def kelvin2celsius(kelvin):
    return kelvin - 273.15


def deg2rad(degrees):
    return degrees * (math.pi / 180.0)


def rad2deg(radians):
    return radians * (180.0 / math.pi)
