import unittest

from core.ssh_workers import PROMPT_READY_MARKER, SshTerminalWorker, full_path_prompt_command


class SshWorkersTest(unittest.TestCase):
    def test_full_path_prompt_command_uses_pwd_prompt(self):
        command = full_path_prompt_command()
        self.assertIn("$(pwd)", command)
        self.assertIn(PROMPT_READY_MARKER, command)
        self.assertIn("PS1", command)
        self.assertIn("history -d", command)

    def test_bootstrap_filter_ignores_marker_in_echoed_command(self):
        worker = SshTerminalWorker("jetson@example")
        worker._suppress_until_marker = PROMPT_READY_MARKER
        output = (
            "printf '\\n{}\\n'\r\n"
            "\r\n{}\r\n"
            "jetson@ubuntu:/home/jetson$ "
        ).format(PROMPT_READY_MARKER, PROMPT_READY_MARKER)
        self.assertEqual(
            worker._filter_bootstrap_output(output),
            "jetson@ubuntu:/home/jetson$ ",
        )

    def test_bootstrap_filter_handles_split_marker(self):
        worker = SshTerminalWorker("jetson@example")
        worker._suppress_until_marker = PROMPT_READY_MARKER
        split = len(PROMPT_READY_MARKER) // 2
        self.assertEqual(worker._filter_bootstrap_output("\r\n" + PROMPT_READY_MARKER[:split]), "")
        self.assertEqual(
            worker._filter_bootstrap_output(PROMPT_READY_MARKER[split:] + "\r\nready"),
            "ready",
        )


if __name__ == "__main__":
    unittest.main()
