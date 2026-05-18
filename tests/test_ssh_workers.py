import unittest

from core.ssh_workers import PROMPT_READY_MARKER, full_path_prompt_command


class SshWorkersTest(unittest.TestCase):
    def test_full_path_prompt_command_uses_pwd_prompt(self):
        command = full_path_prompt_command()
        self.assertIn("$(pwd)", command)
        self.assertIn(PROMPT_READY_MARKER, command)
        self.assertIn("PS1", command)


if __name__ == "__main__":
    unittest.main()
