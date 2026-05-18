import unittest

from core.resource_monitor import parse_monitor_line


class ResourceMonitorTest(unittest.TestCase):
    def test_parse_tegrastats_line(self):
        line = (
            "RAM 1476/3956MB (lfb 128x4MB) SWAP 0/1978MB "
            "CPU [5%@1479,off,6%@1479,7%@1479] "
            "GR3D_FREQ 12% CPU@45.5C GPU@44C"
        )

        result = parse_monitor_line(line)

        self.assertEqual(result["memory"], "1476/3956 MB (37.3%)")
        self.assertEqual(result["cpu"], "6.0%")
        self.assertEqual(result["gpu"], "12%")
        self.assertEqual(result["temperature"], "CPU 45.5C")

    def test_parse_fallback_monitor_line(self):
        result = parse_monitor_line(
            "MON|cpu=1.0%|memory=10/100 MB (10.0%)|gpu=2.0%|temperature=cpu 50.0C"
        )

        self.assertEqual(result["cpu"], "1.0%")
        self.assertEqual(result["memory"], "10/100 MB (10.0%)")
        self.assertEqual(result["gpu"], "2.0%")
        self.assertEqual(result["temperature"], "cpu 50.0C")

    def test_ignores_unrecognized_status_line(self):
        self.assertIsNone(parse_monitor_line("ssh: connect to host 192.168.55.1 port 22: timed out"))


if __name__ == "__main__":
    unittest.main()
