"""
This unit test checks client and server interactions.
"""

import asyncio
import asynctest
import os
import shutil
import tempfile
import unittest
import unittest.mock
from unittest.mock import patch

from adsb.sbs.client import Client
from adsb.sbs.server import Server, logger as server_logger
from adsb.sbs.message import SBSMessage


MESSAGES_LOG_FILE = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "messages-log.txt"
)

SYS_TMP_DIR = os.environ.get("TMPDIR", tempfile.gettempdir())


class TestSBSClientServerTestCase(asynctest.TestCase):

    async def setUp(self):
        self.server = Server(host="localhost", port=0, loop=self.loop)
        await self.server.start()
        self.server_port = self.server.port

    async def tearDown(self):
        await self.server.stop()

    async def test_message_interface(self):

        mock_handler = unittest.mock.Mock()
        client = Client(
            host="localhost", port=self.server.port, on_msg_callback=mock_handler
        )
        await client.start()

        # allow time for server to register connection
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.server.protocols), 1)

        sent = 0
        received = 0
        with open(MESSAGES_LOG_FILE, "rb") as fd:
            for line in fd:
                timestamp, msg_str = line.split(b",", 1)
                assert msg_str.endswith(b"\r\n")
                self.server.send_message(msg_str)
                sent += 1

        # Provide some grace period over which to receive the messages
        # into the client. Break out early if all expected messages are
        # received.
        wait_count = 10
        while wait_count > 0:
            wait_count -= 1
            await asyncio.sleep(0.01)
            if mock_handler.call_count >= sent:
                break
        self.assertEqual(mock_handler.call_count, sent)

        await client.stop()

    async def test_message_archiving(self):
        """ Check client message archiving """
        # Check that an error is raise when no record file is provided
        with self.assertRaises(Exception) as cm:
            client = Client(host="localhost", port=self.server.port, record=True)
        self.assertIn(
            "Record is enabled but no record_file is specified", str(cm.exception)
        )

        tempdir = tempfile.mkdtemp(dir=SYS_TMP_DIR)
        record_file = os.path.join(tempdir, "messages.txt")
        try:
            client = Client(
                host="localhost",
                port=self.server.port,
                record=True,
                record_file=record_file,
            )
            await client.start()

            # allow time for server to register connection
            await asyncio.sleep(0.01)
            self.assertEqual(len(self.server.protocols), 1)

            sent = 0
            received = 0
            with open(MESSAGES_LOG_FILE, "rb") as fd:
                for line in fd:
                    timestamp, msg_str = line.split(b",", 1)
                    assert msg_str.endswith(b"\r\n")
                    self.server.send_message(msg_str)
                    sent += 1

            # Provide some time for client to receive the messages
            await asyncio.sleep(0.1)

            await client.stop()

            self.assertTrue(os.path.exists(record_file))
            statinfo = os.stat(record_file)
            self.assertGreater(statinfo.st_size, 0)

        finally:
            if os.path.isdir(tempdir):
                shutil.rmtree(tempdir)
