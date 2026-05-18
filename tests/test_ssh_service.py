import unittest

from services import ssh_service


class SshServiceTest(unittest.TestCase):
    def test_ssh_options_disable_stdin_for_noninteractive_commands(self):
        self.assertIn("-n", ssh_service.ssh_options(batch_mode=True))

    def test_remote_ssh_command_can_wrap_done_marker(self):
        command = ssh_service.remote_ssh_command(
            "jetson@192.168.55.1",
            "echo ok",
            done_marker=True,
        )

        self.assertEqual(command[0], "ssh")
        self.assertIn("jetson@192.168.55.1", command)
        self.assertIn("echo ok", command[-1])
        self.assertIn(ssh_service.DONE_MARKER, command[-1])
        self.assertIn("exit \"$__jtp_status\"", command[-1])

    def test_remote_ssh_command_keeps_long_running_commands_unwrapped(self):
        command = ssh_service.remote_ssh_command(
            "jetson@192.168.55.1",
            "tail -F run.log",
            done_marker=False,
        )

        self.assertNotIn(ssh_service.DONE_MARKER, command[-1])


if __name__ == "__main__":
    unittest.main()
