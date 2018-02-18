
import os
from adsb.sbs import json_utils, message
import unittest


# TEST_MSG_STR = 'MSG,3,1,1,7C79B7,1,2017/03/25,10:41:45.365,2017/03/25,10:41:45.384,,2850,,,-34.84658,138.67962,,,,,,'
# TEST_MSG = message.fromString(TEST_MSG_STR)
MESSAGES_LOG_FILE = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'messages-log.txt')


class JsonUtilsTestCase(unittest.TestCase):

    # def test_json_utils(self):
    #     ''' check JSON encoding and decoding works as expected '''
    #     self.assertEqual(json_utils.loads(json_utils.dumps(TEST_MSG)), TEST_MSG)

    def test_json_roundtrip(self):
        ''' Check json utils can rountrip message without data loss '''
        with open(MESSAGES_LOG_FILE, 'rb') as fd:
            for line in fd:
                timestamp, msg_data = line.split(b',', 1)
                assert msg_data.endswith(b'\r\n')
                msg = message.fromString(msg_data)
                json_msg = json_utils.dumps(msg)
                recovered_msg = json_utils.loads(json_msg)
                self.assertEqual(recovered_msg, msg)
