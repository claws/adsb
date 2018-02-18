'''
This module implements an aircraft class to store details of aircraft
that are active during a session.
'''

import collections
import datetime
import logging

from ..mypy_types import (
    AltitudeType,
    LatitudeType,
    LongitudeType,
    PositionType,
    HistoryPointType,
)
from typing import List, Tuple


logger = logging.getLogger(__name__)


class Aircraft(object):
    '''
    The Aircraft class stores details for a specific aircraft observed during
    a session.
    '''

    def __init__(self,
                 hex_ident: str,
                 history_size: int = 50,
                 history_interval: int = 5) -> None:
        '''

        :param hex_ident: An ICAO hex identifier that uniquely identifies the
          aircraft.

        :param history_size: The maximum number of history points to record.
          By default this value is 50. Set this value to 0 is disable a
          maximum.

        :param history_interval: The minimum time interval, in seconds,
          that must elapse before creating a new history point. Any updates
          received within this window are discarded. By default the interval
          is 5 seconds. Set this argument to None to disable this feature
          which will add every update to the history list.

        '''
        self.icao = hex_ident
        self.callsign = None
        self.last_seen = None
        self.altitude = None
        self.latitude = None
        self.longitude = None
        self.ground_speed = None
        self.track = None
        self.vertical_rate = None

        self.msg_count = 0

        # If origin is set then
        self.origin = None

        # The 'details' attribute stores information such as manufacturer,
        # model, type, operator, etc.
        self.details = {}

        self.history_interval = None
        if history_interval:
            self.history_interval = datetime.timedelta(
                seconds=history_interval)
        self.history = collections.deque(maxlen=history_size)

    @property
    def position(self) -> PositionType:
        ''' Return the aircraft position as (lat, lon) tuple '''
        return (self.latitude, self.longitude)

    @property
    def distance(self) -> float:
        '''
        Return the distance in km between a location and this aircraft.
        '''
        dist = None
        if None not in self.position and None not in self.origin:
            dist = haversine_distance(self.origin, self.position)
        return dist

    def __str__(self):
        o = ['icao24={}'.format(self.icao)]
        o.append('last_seen={}'.format(self.last_seen))
        o.append('msgs={}'.format(self.msg_count))
        o.append('history={}'.format(len(self.history)))
        o.append('lat={}'.format(self.latitude))
        o.append('lon={}'.format(self.longitude))
        o.append('alt={}'.format(self.altitude))
        o.append('ground_speed={}'.format(self.ground_speed))
        o.append('track={}'.format(self.track))
        o.append('vertical_rate={}'.format(self.vertical_rate))
        o.append('callsign={}'.format(self.callsign))
        if self.details:
            o.append('details={}'.format(self.details))
        return ', '.join(o)

    def update_ident(self,
                     callsign: str,
                     timestamp: datetime.datetime):
        ''' Update the identity of the aircraft '''
        self.last_seen = timestamp
        self.callsign = callsign

    def update_motion(self,
                      ground_speed: float,
                      track: float,
                      vertical_rate: float,
                      timestamp: datetime.datetime):
        ''' Update the motion attributes of the aircraft '''
        self.ground_speed = ground_speed
        self.track = track
        self.vertical_rate = vertical_rate
        self.last_seen = timestamp

    def update_position(self,
                        alt: AltitudeType,
                        lat: LatitudeType,
                        lon: LongitudeType,
                        timestamp: datetime.datetime):
        ''' Update the position attributes of the aircraft '''
        self.last_seen = timestamp
        self.altitude = alt
        self.latitude = lat
        self.longitude = lon
        if self.history:
            if self.history_interval is not None:
                _timestamp, *others = self.history[-1]
                if timestamp > (_timestamp + self.history_interval):
                    self.history.append((timestamp, lat, lon, alt))
            else:
                self.history.append((timestamp, lat, lon, alt))
        else:
            self.history.append((timestamp, lat, lon, alt))

    def update_altitude(self,
                        alt: AltitudeType,
                        timestamp: datetime.datetime):
        ''' Update the altitude of the aircraft '''
        self.last_seen = timestamp
        self.altitude = alt

    def update_details(self,
                       details: dict):
        '''
        Associate aircraft details, such as model, type, operator, etc,
        with this aircraft.
        '''
        self.details = details

    def path(self) -> List[HistoryPointType]:
        ''' Return the travel path of this aircraft '''
        return list(self.history)
