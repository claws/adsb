"""
This module implements a protocol for receiving messages in the SBS
format.
"""

import asyncio
import logging

from asyncio import AbstractEventLoop
from typing import Callable, Tuple

MessageType = str
MessageHandlerType = Callable[[MessageType], None]


logger = logging.getLogger(__name__)


DELIMITER = b"\r\n"


class SBSProtocol(asyncio.Protocol):
    """
    A simple line based protocol to extract SBS messages from a stream.
    """

    def __init__(
        self, on_msg_callback: MessageHandlerType = None, loop: AbstractEventLoop = None
    ):
        """
        :param on_msg_callback: a function that will be called whenever
          a new message line is received. The callback is expected to
          take one argument which is the message text.

        :param loop: The event loop to run in.
        """
        self.loop = loop or asyncio.get_event_loop()
        self.on_message_received = on_msg_callback
        self.transport = None
        self.buf = None  # type: bytearray
        self.wait_connected = self.loop.create_future()
        self.wait_closed = self.loop.create_future()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """ React to a new connection being made """
        self.remote_addr = transport.get_extra_info("peername")
        self.transport = transport
        self.buf = bytearray()
        logger.debug("SBSProtocol connected to {}".format(self.remote_addr))
        self.wait_connected.set_result(None)

    def connection_lost(self, reason: str) -> None:
        """ React to an existing connection being lost """
        logger.debug(
            "SBSProtocol disconnected from {}.{}".format(
                self.remote_addr, " Reason: {}".format(reason) if reason else ""
            )
        )
        self.buf = None
        self.wait_closed.set_result(None)

    def data_received(self, data: bytes) -> None:
        """
        Process a raw data stream. Accumulate message chunks until a complete
        message can be extracted from the buffer. Messages are delimited by
        the characters \\r\\n.

        Sources such as mutability/dump1090 also send a heartbeat message,
        containing only \\r\\n, if there is no ADSB activity. These need
        to be handled gracefully.

        Each SBS message has the trailing \\r\\n delimiter discarded and is
        converted to a string before being passed to the message handler.
        """
        self.buf.extend(data)
        while self.buf:
            msg, sep, remainder = self.buf.partition(DELIMITER)
            # If sep contains a delimiter then we may have extracted a msg,
            # otherwise we only have a chunk and need to accumulate more
            # bytes until a complete message can be extracted.
            if not sep:
                break
            self.buf = remainder
            if msg and self.on_message_received:
                self.on_message_received(bytes(msg))

    def close(self) -> None:
        """ Close the connection """
        if self.transport:
            self.transport.abort()  # don't wait for unsent buffered data


class SBSServerProtocol(asyncio.Protocol):
    """ A SBSProtocol instance specifically for use in a SBS server.

    The main use for this class is in unit tests.
    """

    def __init__(self, server: "SBSServer"):
        self.server = server

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport
        self.peer = transport.get_extra_info("peername")  # type: Tuple[str, int]
        logger.debug(f"{self.__class__.__name__} connected to {self.peer}")
        self.server.register_protocol(self.peer, self)

    def connection_lost(self, reason: str) -> None:
        logger.debug(
            f"{self.__class__.__name__} disconnected from {self.peer}. "
            f"Reason: {reason}"
            if reason
            else ""
        )
        self.server.deregister_protocol(self.peer)

    def close(self) -> None:
        """ Close the connection """
        if self.transport:
            self.transport.abort()  # don't wait for unsent buffered data

    def data_received(self, data: bytes) -> None:
        """
        The server does not expect to receive data from clients. It is
        effectively a one-way publisher socket.
        """
        logger.warning(
            "Received unexpected data from client %s: %s".format(
                self.peer, data.decode()
            )
        )

    def send_message(self, data: bytes, add_delimiter: bool = False) -> None:
        """ Send message to client.

        :param bytes: A SBS format message string encoded into bytes to send
          to clients.

        :param add_delimiter: A boolean flag that determines if a message
          delimiter should be added to the message bytes. By default this
          is False.
        """
        if add_delimiter:
            data = data + DELIMITER
        self.transport.write(data)
