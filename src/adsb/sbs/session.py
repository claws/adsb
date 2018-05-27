"""
A session maintains information about the currently visible aircraft.
"""

import asyncio
import collections
import datetime
import logging
import os
import pickle

from . import client
from . import archive
from . import aircraft
from . import message
from asyncio import AbstractEventLoop
from ..mypy_types import PositionType


logger = logging.getLogger(__name__)


class Session(object):
    """
    A session maintains information about aircraft received from a SBS Client.

    A session is connected to a SBS source to receive a stream of messages or
    can operate in a replay mode where it is fed messages from a session log
    archive.
    """

    def __init__(
        self,
        record: bool = False,
        record_file: str = None,
        cache_enabled: bool = True,
        cache_file: str = "session_cache.pickle",
        session_threshold_minutes: int = 2,
        check_interval: float = 5.0,
        origin: PositionType = None,
        loop: AbstractEventLoop = None,
    ):
        """
        :param record: a boolean flag to enable recording messages to a
        session log file. By default this is False. The *record_file*
        argument must be supplied is this argument is True.

        :param record_file: The file name to use for recorded messages.
          By default this is None.

        :param cache_enabled: A boolean flag that determines whether
          the session aircraft should be cached into a pickle file.
          This allows the session to quickly recover state after a brief
          shutdown and restart. The default value is True.

        :param cache_file: A filename to use for the cache file. The
          default value is 'session_cache.pickle'.

        :param session_threshold_minutes: The number of minutes to retain
          an aircraft in the session after the last message received
          from the aircraft.

        :param check_interval: The number of seconds between checking
          if aircraft in the cache should be discarded.

        :param origin: a tuple of (lat, lon) representing a reference
          location to use as the origin for distance calculations.
        """
        self.loop = loop or asyncio.get_event_loop()

        self.origin = origin
        self.client = None  # type client.Client

        # `aircraft` is a dict of {'icao24': :class:`Aircraft`}
        self.aircraft = {}

        # Aircraft are considered lost after a period of time without
        # receiving any updates. When aircraft are lost they are removed
        # from the aircraft dict.
        self.expiry_threshold = datetime.timedelta(minutes=session_threshold_minutes)

        self.logfile = None  # type: archive.RotatingArchiveFileHandler
        if record and record_file is None:
            raise Exception("Record is enabled but no record_file is specified!")
        self.record_file = record_file
        self.archiving_enabled = False
        if record:
            self.start_recording(self.session_file)

        # Aircraft can be reloaded from a previous session cache (pickle)
        # to quickly re-establish aircraft details. This is useful in
        # situations where there is a brief period between application
        # stop and subsequent start. If the interval is longer than the
        # aircraft expiry threshold then all cache aircraft will be dropped.
        self.cache_enabled = cache_enabled
        self.cache_file = cache_file
        if self.cache_enabled and os.path.exists(self.cache_file):
            self.load_aircraft_cache()

        # A monitor function scans over the aircraft at periodic intervals
        # in order to discard aircraft that have not been updated recently.
        # The aircraft expiry threshold is configurable.
        # Start the monitor task to discard aircraft from the session
        # if they have not had an update in a while.
        self.cache_monitor_interval = check_interval
        self.session_monitor_task = asyncio.Task(self.manage_session())

    async def connect(self, host, port=30003):
        """ Connect the session to a SBS interface """
        self.client = client.Client(
            host=host, port=port, on_raw_msg_callback=self.on_sbs_message
        )
        await self.client.start()

    async def disconnect(self):
        """ Disconnect the session from a SBS interface """
        if self.client:
            await self.client.stop()
        self.client = None

    async def close(self):
        """ Stop the session """
        await self.disconnect()
        self.stop_recording()
        if self.cache_enabled:
            logger.info("Saving aircraft to session cache")
            with open(self.cache_file, "wb") as cache_fd:
                assert isinstance(self.aircraft, dict)
                pickle.dump(self.aircraft, cache_fd)
        self.session_monitor_task.cancel()

    # async def replay(self, session_file, replay_rate=1):
    #     '''
    #     Replay messages from a session log file.

    #     A session log file line contains a timestamp and then a raw SBS
    #     message line. Each line is terminated with a newline character.

    #     :param session_file: A session log file
    #     :param replay_rate: A time multiplier factor to adjust the
    #       message replay rate. Default is 1.
    #     '''
    #     previous_timestamp = None
    #     if os.path.exists(session_file):

    #         # Adjust the cache monitor interval so that planes expire out
    #         # of the cache at a duration appropriate for the replay rate.
    #         cache_monitor_interval_orig = self.cache_monitor_interval
    #         self.cache_monitor_interval = (
    #             self.cache_monitor_interval / replay_rate)

    #         with open(session_file, 'r') as f:
    #             for line in f:
    #                 line = line.rstrip()
    #                 timestamp, msg = line.split(',', 1)
    #                 timestamp = datetime.datetime.strptime(
    #                     timestamp, "%Y%m%dT%H%M%S.%f")

    #                 adjusted_delay = 0.01
    #                 if previous_timestamp:
    #                     interval = timestamp - previous_timestamp
    #                     delay = interval.total_seconds()
    #                     adjusted_delay = delay / replay_rate
    #                 previous_timestamp = timestamp

    #                 # Don't bother delaying for very small time intervals.
    #                 if adjusted_delay > 0.04:
    #                     await asyncio.sleep(adjusted_delay)

    #                 self.on_sbs_message(msg)

    #     self.cache_monitor_interval = cache_monitor_interval_orig

    def start_recording(
        self, record_file: str = None, maxBytes: int = 2 ** 23, backupCount: int = 3
    ):
        """
        Start recording session messages to log file.
        """
        record_file = record_file or self.record_file
        if record_file is None:
            raise Exception("No session log file specified")

        if not self.archiving_enabled:
            self.logfile = archive.RotatingArchiveFileHandler(
                record_file, maxBytes=maxBytes, backupCount=backupCount
            )
            self.archiving_enabled = True
        else:
            logger.warning(
                "Attempted to start session recording but session is "
                "already being recorded!"
            )

    def stop_recording(self):
        """
        Stop recording session messages to file.
        """
        if self.archiving_enabled:
            self.archiving_enabled = False
            if self.logfile:
                self.logfile.close()
                self.logfile = None

    def on_sbs_message(self, msg_str: str):
        """
        Process a SBS message line string.

        This method is typically called by a SBS client. However, it may
        also be called when replaying a session file.
        """
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        msg = message.fromString(msg_str)

        if msg.hex_ident == "000000":
            logger.warning("Invalid ICAO code detected: {}".format(msg.hex_ident))
            return

        if msg.message_type == message.MessageType.Transmission:

            if self.archiving_enabled:
                self.logfile.emit(msg_str)

            if msg.hex_ident not in self.aircraft:

                ac = aircraft.Aircraft(msg.hex_ident)
                # Add origin info to the aircraft so distance calculations can be
                # performed.
                ac.origin = self.origin

                self.aircraft[msg.hex_ident] = ac
                logger.info("New session aircraft: %s", msg.hex_ident)

            ac = self.aircraft[msg.hex_ident]
            ac.last_seen = now
            ac.msg_count += 1

            if (
                msg.transmission_type
                == message.TransmissionType.ES_IDENT_AND_CATEGORY.value
            ):

                if ac.callsign != msg.callsign:
                    timestamp = now
                    ac.update_ident(msg.callsign, timestamp)

            elif msg.transmission_type in [
                message.TransmissionType.ES_SURFACE_POS.value,
                message.TransmissionType.ES_AIRBORNE_POS.value,
            ]:
                timestamp = now
                ac.update_position(msg.altitude, msg.lat, msg.lon, timestamp)

            elif (
                msg.transmission_type == message.TransmissionType.ES_AIRBORNE_VEL.value
            ):
                timestamp = now
                ac.update_motion(
                    msg.ground_speed, msg.track, msg.vertical_rate, timestamp
                )

            elif msg.transmission_type in [
                message.TransmissionType.AIR_TO_AIR.value,
                message.TransmissionType.SURVEILLANCE_ALT.value,
            ]:
                timestamp = now
                ac.update_altitude(msg.altitude, timestamp)

    def load_aircraft_cache(self):
        """ Initialise the aircraft cache using the cache file. """
        with open(self.cache_file, "rb") as cache_fd:
            cached_aircraft = pickle.load(cache_fd)
            self.discard_lost_aircraft(cached_aircraft)
            if cached_aircraft:
                logger.info(
                    "Recovered {} aircraft from session cache".format(
                        len(cached_aircraft)
                    )
                )
                assert isinstance(cached_aircraft, dict)

                # for icao_id, ac in cached_aircraft.items():
                #     if not ac.details:
                #         self.enqueue_lookup(icao_id)

                self.aircraft = cached_aircraft

    def discard_lost_aircraft(self, aircraft_dict):
        """
        Remove aircraft that were last seen beyond the expiry threshold.
        The expiry threshold is a configurable session attribute.

        :param aircraft_dict: A dict of aircraft participating in this
          session.
        """
        lost_aircraft = []
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        for icao_id, aircraft_item in aircraft_dict.items():
            x = now - aircraft_item.last_seen
            if x > self.expiry_threshold:
                lost_aircraft.append(icao_id)

        if lost_aircraft:
            logger.debug(
                "dropping {} aircraft from session due to inactivity: "
                "{}".format(len(lost_aircraft), lost_aircraft)
            )
            for icao_id in lost_aircraft:
                del aircraft_dict[icao_id]

    async def manage_session(self):
        """ Perform periodic session management actions.

        """
        logger.debug("starting session management task")
        while True:
            self.discard_lost_aircraft(self.aircraft)
            await asyncio.sleep(self.cache_monitor_interval)
