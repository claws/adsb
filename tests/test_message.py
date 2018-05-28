
import os
from adsb.sbs import message
import unittest


# TEST_MSG_STR = b'MSG,3,1,1,7C79B7,1,2017/03/25,10:41:45.365,2017/03/25,10:41:45.384,,2850,,,-34.84658,138.67962,,,,,,\r\n'
# TEST_MSG = message.fromString(TEST_MSG_STR)
MESSAGES_LOG_FILE = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "messages-log.txt"
)


class MessageTestCase(unittest.TestCase):

    # def test_message(self):
    #     ''' check message encoding and decoding works as expected '''
    #     self.assertEqual(message.toString(message.fromString(TEST_MSG_STR)), TEST_MSG)

    def test_message_roundtrip(self):
        """ Check json utils can rountrip message without data loss """
        with open(MESSAGES_LOG_FILE, "rb") as fd:
            for line in fd:
                timestamp, msg_data = line.split(b",", 1)
                assert msg_data.endswith(b"\r\n")
                msg = message.fromString(msg_data)
                recovered_msg_data = message.toString(msg)

                # Ideally, I would like to be able to check msg_data agsint
                # the recovered_msg_data but because of string stripping this
                # is not possible.
                # self.assertEqual(recovered_msg_data, msg_data)

                # Therefore convert the recovered string back into a message
                # object and compare that.
                recovered_msg = message.fromString(recovered_msg_data)
                self.assertEqual(recovered_msg, msg)
