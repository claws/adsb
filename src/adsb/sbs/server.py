
import asyncio
import datetime
import logging
import socket

from . import protocol

from typing import Tuple
from asyncio import AbstractEventLoop


logger = logging.getLogger(__name__)


class Server(object):

    def __init__(
        self,
        host: str = "localhost",
        port: int = 30003,
        backlog=100,
        loop: AbstractEventLoop = None,
    ) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self.host = host
        self._requested_port = port
        self.port = None
        self.backlog = backlog
        self.listener = None
        self.protocols = {}

    async def start(self) -> None:
        """ Start the server """
        try:
            self.listener = await self.loop.create_server(
                lambda: protocol.SBSServerProtocol(self),
                self.host,
                self._requested_port,
                family=socket.AF_INET,
                backlog=self.backlog,
            )  # type: asyncio.Server
            # Fetch actual port in use. This can be different from the
            # specified port if the port was passed as 0 which means use
            # an ephemeral port.
            assert len(self.listener.sockets) == 1
            _, self.port = self.listener.sockets[0].getsockname()
        except asyncio.CancelledError:
            logger.exception("Connection waiter Future was cancelled")
        except Exception:
            logger.exception("An error occurred in start")

    async def stop(self) -> None:
        """ Stop the server """
        if self.listener:
            # Avoid iterating over the protocols dict which may change size
            # while it is being iterating over.
            peers = list(self.protocols)
            for peer in peers:
                prot = self.protocols.get(peer)
                if prot:
                    prot.close()
            self.listener.close()

    def register_protocol(
        self, peer: Tuple[str, int], prot: "SBSServerProtocol"
    ) -> None:
        """ Register a protocol instance with the server.

        :param peer: Tuple of (host:str, port:int).
        :param prot: a SBSServerProtocol instance.
        """
        self.protocols[peer] = prot

    def deregister_protocol(self, peer: Tuple[str, int]) -> None:
        """ De-register a protocol instance from the server.

        This peer will no longer receive messages.

        :param peer: Tuple of (host:str, port:int).
        """
        del self.protocols[peer]

    def send_message(self, msg: bytes, peer: Tuple[str, int] = None) -> None:
        """ Send a message.

        :param msg: A bytes object representing the SBS format message to
          send to peers. The message is assumed to include the end of
          message delimiter.
        :param peer: A specific peer to send the message to. Peer is a
          Tuple of (host:str, port:int). If not specified then the message
          is broadcast to all peers.
        """
        if self.protocols:
            if peer:
                prot = self.protocols.get(peer)
                if prot:
                    prot.send_message(msg)
                else:
                    raise Exception(
                        f"Server can't send msg to non-existant peer: {peer}"
                    )
            else:
                # broadcast message to all peers
                for peer, prot in self.protocols.items():
                    prot.send_message(msg)
        else:
            raise Exception("Server can't send msg, no peers available")
