"""
This unit test checks SBS server API.
"""

import asyncio
import asynctest
import unittest
import unittest.mock
from unittest.mock import patch

from adsb.sbs.client import Client
from adsb.sbs.server import Server
from adsb.sbs.protocol import logger as prot_logger
from adsb.sbs.message import SBSMessage


TEST_MSG = (
    b"MSG,3,1,1,7C79B7,1,2017/03/25,10:41:45.365,2017/03/25,10:41:45.384,,2850,,,-34.84658,138.67962,,,,,,\r\n"
)


class SBSServerTestCase(asynctest.TestCase):

    async def setUp(self):
        self.server = Server(host="localhost", port=0, loop=self.loop)
        await self.server.start()

    async def tearDown(self):
        await self.server.stop()

    async def test_server_send_message(self):
        # Check exception is raised when send is called and no peers are
        # present.
        with self.assertRaises(Exception) as cm:
            self.server.send_message(TEST_MSG)

        self.assertIn("Server can't send msg, no peers available", str(cm.exception))

    async def test_server_send_to_specific_peer(self):
        """ Check sending messages to specific peers """

        mock_handler = unittest.mock.Mock()
        client = Client(
            host="localhost", port=self.server.port, on_msg_callback=mock_handler
        )
        await client.start()

        # allow time for server to register connection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 1)

        # check msg can be sent to a specific peer
        remote_addr = None
        for _remote_addr in self.server.protocols:
            remote_addr = _remote_addr
        self.assertIsInstance(remote_addr, tuple)
        self.server.send_message(TEST_MSG, peer=remote_addr)

        # check an exception is raised when sending to an invalid peer
        # At least one peer must be present to test this case.
        with self.assertRaises(Exception) as cm:
            self.server.send_message(TEST_MSG, peer="invalid")
        self.assertIn("Server can't send msg to non-existant peer", str(cm.exception))

        # allow time for msg to propagate to client
        await asyncio.sleep(0.01)

        self.assertEqual(mock_handler.call_count, 1)
        name, args, kwargs = mock_handler.mock_calls[0]
        self.assertIsInstance(args[0], SBSMessage)

        await client.stop()

        # allow time for server to register disconnection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 0)

    async def test_server_broadcast(self):
        """ Check broadcasting messages to many peers """

        # check msg can be broadcast to all peers
        # This test requires multiple clients
        mock_handler_1 = unittest.mock.Mock()
        client1 = Client(
            host="localhost", port=self.server.port, on_msg_callback=mock_handler_1
        )
        await client1.start()

        mock_handler_2 = unittest.mock.Mock()
        client2 = Client(
            host="localhost", port=self.server.port, on_msg_callback=mock_handler_2
        )
        await client2.start()

        # allow time client and server to register connection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 2)

        self.server.send_message(TEST_MSG)

        # allow time for msg to propogate to client
        await asyncio.sleep(0.02)

        self.assertEqual(mock_handler_1.call_count, 1)
        name, args, kwargs = mock_handler_1.mock_calls[0]
        self.assertIsInstance(args[0], SBSMessage)

        self.assertEqual(mock_handler_2.call_count, 1)
        name, args, kwargs = mock_handler_2.mock_calls[0]
        self.assertIsInstance(args[0], SBSMessage)

        await client1.stop()
        await client2.stop()

        # allow time client and server to register disconnection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 0)

    async def test_server_receive_message(self):
        """ Check unexpected messages received from peers raise a warning """

        mock_handler = unittest.mock.Mock()
        client = Client(
            host="localhost", port=self.server.port, on_msg_callback=mock_handler
        )
        await client.start()

        # allow time client and server to register connection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 1)

        with patch.object(prot_logger, "warning") as mock_warn:
            client.protocol.transport.write(b"123")

            # allow time for msg to propagate from client to server
            await asyncio.sleep(0.01)

            self.assertEqual(mock_warn.call_count, 1)
            # confirm warning was emitted as expected
            name, args, kwargs = mock_warn.mock_calls[0]
            self.assertIn("Received unexpected data from client", args[0])

        await client.stop()
        # allow time client and server to register disconnection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 0)
