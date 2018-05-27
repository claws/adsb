
import adsb
import unittest


class BasicTestCase(unittest.TestCase):
    """ Basic test cases """

    def test_basic(self):
        """ check True is True """
        self.assertTrue(True)

    def test_version(self):
        """ check adsb exposes a version attribute """
        self.assertTrue(hasattr(adsb, "__version__"))
        self.assertIsInstance(adsb.__version__, str)


if __name__ == "__main__":
    unittest.main()
