
import asyncio
import logging

from asyncio import AbstractEventLoop
from . import archive, message, protocol
from typing import Callable

RawMessageType = bytes
RawMessageHandlerType = Callable[[RawMessageType], None]
MessageType = message.SBSMessage
MessageHandlerType = Callable[[MessageType], None]


logger = logging.getLogger(__name__)


class Client(object):
    """ A SBS message client.

    A Client connects to a SBS server to obtain ADSB messages in the
    SBS format. A Client can record messages to a file if configured
    to do so.

    Users of the Client would typically provide a callback function
    to receive either raw message string or SBSMessage objects.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 30003,
        on_raw_msg_callback: RawMessageHandlerType = None,
        on_msg_callback: MessageHandlerType = None,
        record: bool = False,
        record_file: str = None,
        loop: AbstractEventLoop = None,
    ):
        """
        :param host: The SBS server host to connect to.

        :param port: The SBS server port to connect to.

        :param on_raw_msg_callback: a function that will be called whenever
          a new SBS message is received. The callback is expected to
          take one argument which is the message text.

        :param on_msg_callback: a user function that will be called whenever
          a new SBS message is received. The callback is expected to
          take one argument which is a SBSMessage object.

        :param record: a boolean flag to enable recording messages to a file.
          By default this is False. The *record_file* argument must be
          supplied is this argument is True.

        :param record_file: The file name to use for recorded messages.
          By default this is sbs_messages.txt.

        :param loop: The event loop to run in.
        """
        self.loop = loop or asyncio.get_event_loop()
        self.host = host
        self.port = port
        self._on_message_received = on_msg_callback
        self._on_raw_message_received = on_raw_msg_callback
        self.record = record
        if record and record_file is None:
            raise Exception("Record is enabled but no record_file is specified!")
        self.record_file = record_file
        self.archiving_enabled = False
        self.logfile = None
        self.protocol = None

    async def start(self) -> None:
        """ Start the client """
        if self.protocol:
            raise Exception("Client is already running!")

        if self.record:
            self.start_recording(self.record_file)
        await self.connect(self.host, self.port)

    async def stop(self) -> None:
        """ Stop the client """
        self.stop_recording()
        await self.disconnect()

    async def connect(self, host: str, port=30003) -> None:
        """ Connect to a SBS interface.

        :param host: The SBS server host to connect to.

        :param port: The SBS server port to connect to.
        """
        self.protocol = protocol.SBSProtocol(on_msg_callback=self._on_sbs_message)
        t, p = await self.loop.create_connection(lambda: self.protocol, host, port)
        await p.wait_connected

    async def disconnect(self) -> None:
        """ Disconnect from a SBS interface """
        if self.protocol:
            self.protocol.close()
            await self.protocol.wait_closed
        self.protocol = None

    def start_recording(
        self, record_file: str = None, maxBytes: int = 2 ** 23, backupCount: int = 3
    ) -> None:
        """ Start recording messages to a log file """
        record_file = record_file or self.record_file
        if record_file is None:
            raise Exception("No recording log file specified")

        if not self.archiving_enabled:
            self.logfile = archive.RotatingArchiveFileHandler(
                record_file, maxBytes=maxBytes, backupCount=backupCount
            )
            self.archiving_enabled = True
        else:
            logger.warning(
                "Attempted to start recording messages but session is "
                "already being recorded!"
            )

    def stop_recording(self) -> None:
        """ Stop recording messages to file """
        if self.archiving_enabled:
            self.archiving_enabled = False
            if self.logfile:
                self.logfile.close()
                self.logfile = None

    def _on_sbs_message(self, msg_data: bytes) -> None:
        """ Handle a raw SBS message line from the protocol.

        This callback function is provided to the protocol so it can
        provide messages to the client.

        :param msg_data: A bytes object representing the raw SBS format ADSB
          message line which has had the trailing '\r\n' delimiter discarded.
        """
        msg_str = msg_data.decode()

        if self.archiving_enabled:
            self.logfile.emit(msg_str)

        if self._on_raw_message_received:
            self._on_raw_message_received(msg_data)

        if self._on_message_received:
            try:
                msg = message.fromString(msg_str)
            except Exception:
                logger.exception("Error parsing message string")
                return

            if msg.hex_ident == "000000":
                logger.warning("Invalid ICAO code detected: {}".format(msg.hex_ident))
                return

            self._on_message_received(msg)
