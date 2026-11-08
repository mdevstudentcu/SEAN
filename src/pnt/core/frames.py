"""Coordinate frames (ADR-0008): WGS84 geodetic <-> ECEF <-> local ENU.

Angles in degrees at the API, metres everywhere. The only conversion point in the code base.
"""

from __future__ import annotations

import numpy as np

WGS84_A = 6_378_137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def llh_to_ecef(llh) -> np.ndarray:
    lat, lon, h = np.radians(llh[0]), np.radians(llh[1]), llh[2]
    n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
    return np.array(
        [
            (n + h) * np.cos(lat) * np.cos(lon),
            (n + h) * np.cos(lat) * np.sin(lon),
            (n * (1 - WGS84_E2) + h) * np.sin(lat),
        ]
    )


def ecef_to_llh(ecef) -> np.ndarray:
    x, y, z = ecef
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - WGS84_E2))
    for _ in range(6):  # converges to < 1 mm in a few iterations
        n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - WGS84_E2 * n / (n + h)))
    n = WGS84_A / np.sqrt(1 - WGS84_E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return np.array([np.degrees(lat), np.degrees(lon), h])


def _rot_ecef_to_enu(origin_llh) -> np.ndarray:
    lat, lon = np.radians(origin_llh[0]), np.radians(origin_llh[1])
    sl, cl, so, co = np.sin(lat), np.cos(lat), np.sin(lon), np.cos(lon)
    return np.array([[-so, co, 0.0], [-sl * co, -sl * so, cl], [cl * co, cl * so, sl]])


def ecef_to_enu(ecef, origin_llh) -> np.ndarray:
    return _rot_ecef_to_enu(origin_llh) @ (np.asarray(ecef) - llh_to_ecef(origin_llh))


def enu_to_ecef(enu, origin_llh) -> np.ndarray:
    return _rot_ecef_to_enu(origin_llh).T @ np.asarray(enu) + llh_to_ecef(origin_llh)


def llh_to_enu(llh, origin_llh) -> np.ndarray:
    return ecef_to_enu(llh_to_ecef(llh), origin_llh)


def enu_to_llh(enu, origin_llh) -> np.ndarray:
    return ecef_to_llh(enu_to_ecef(enu, origin_llh))
