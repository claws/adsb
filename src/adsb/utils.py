
import math

from .constants import EARTH_RADIUS
from .mypy_types import PositionType


def haversine_distance(origin: PositionType, destination: PositionType) -> float:
    """ Haversine distance calculation.

    :param origin: a (lat, lon) tuple.
    :param destination: a (lat, lon) tuple.
    :returns: a distance in meters.
    """

    if origin is None or destination is None:
        raise Exception(f"origin {origin} or destination {destination} was None")

    lat1, lon1 = origin
    lat2, lon2 = destination

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.pow(math.sin(dlat / 2), 2) + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.pow(math.sin(dlon / 2), 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    d = EARTH_RADIUS * c

    return d


def feet_to_meters(feet: float) -> float:
    """ Convert feet to meters.

    :param feet: a measurement in feet.
    :returns: measurement in meters
    """
    return feet / 0.3048


def knots_to_kmh(knots: float) -> float:
    """ Convert velocity in knots to km/h

    1 knot (i.e. 1 nm/h or 1 nautical mile per hour) is 1.852 km/h.

    :param knots: velocity in knots
    :returns: velocity in km/h
    """
    return knots * 1.852


def knots_to_mps(knots: float) -> float:
    """ Convert velocity in knots to m/s

    1 knot (i.e. 1 nm/h or 1 nautical mile per hour) is 6.667 m/s.

    :param knots: velocity in knots
    :returns: velocity in m/s
    """
    return knots_to_kmh(knots) * 3.6


def make_geodesic_circle(center: PositionType, radius: float, num_points: int = 40):
    """ Return a list of num_points (lat,lon) items that represent a
    closed circle on the Earth such that the great circle distance from
    'center' to each point is 'radius' meters.

    :param center: a (lat,lon) tuple representing the center.
    :param radius: the radius of the circle.
    :param num_points: the number of points to use to represent the circle.
    """
    angularDistance = radius / EARTH_RADIUS
    lon_r = math.radians(lon)
    lat_r = math.radians(lat)
    coords = []
    for point in range(num_points):
        bearing = i * 2 * math.pi / num_points

        lat2 = math.asin(
            math.sin(lat_r) * math.cos(angularDistance)
            + math.cos(lat_r) * math.sin(angularDistance) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angularDistance) * math.cos(lat_r),
            math.cos(angularDistance) - math.sin(lat_r) * math.sin(lat_r),
        )

        lat_d = math.degrees(lat2)
        lon_d = math.degrees(lon2)
        coords.append((lat2, lon2))

    return coords
