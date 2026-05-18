import unittest

from services import proxy_service


class ProxyServiceTest(unittest.TestCase):
    def test_disable_jetson_proxy_command_clears_session_and_system_proxy(self):
        command = proxy_service.disable_jetson_proxy_command()

        self.assertIn("unset http_proxy", command)
        self.assertIn("git config --global --unset-all http.proxy", command)
        self.assertIn("sudo sh \"$tmp\"", command)
        self.assertIn("/etc/apt/apt.conf.d/*", command)
        self.assertIn("Acquire::.*Proxy", command)
        self.assertIn("/etc/environment", command)
        self.assertIn(".jtp-proxy-bak-", command)


if __name__ == "__main__":
    unittest.main()
