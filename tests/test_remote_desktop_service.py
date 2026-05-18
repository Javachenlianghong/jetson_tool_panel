import unittest

from services import remote_desktop_service


class RemoteDesktopServiceTest(unittest.TestCase):
    def test_start_command_uses_localhost_x11vnc(self):
        command = remote_desktop_service.x11vnc_start_command(":0", "/home/jetson/.Xauthority", 5901)

        self.assertIn("x11vnc", command)
        self.assertIn("-localhost", command)
        self.assertIn("-nopw", command)
        self.assertIn("-rfbport \"$port\"", command)
        self.assertIn("5901", command)
        self.assertIn("/home/jetson/.Xauthority", command)

    def test_stop_command_targets_port(self):
        command = remote_desktop_service.x11vnc_stop_command(5902)

        self.assertIn("pkill", command)
        self.assertIn("5902", command)

    def test_install_command_is_apt_based(self):
        command = remote_desktop_service.x11vnc_install_command()

        self.assertIn("apt-get install -y x11vnc", command)


if __name__ == "__main__":
    unittest.main()
