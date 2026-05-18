import unittest

from core.command_runner import decode_process_output


class CommandRunnerDecodeTest(unittest.TestCase):
    def test_decodes_utf8_remote_output(self):
        line = "状态 正常 ✓\n".encode("utf-8")
        self.assertEqual(decode_process_output(line), "状态 正常 ✓")

    def test_falls_back_to_windows_code_page_output(self):
        line = "防火墙已启用\n".encode("gbk")
        self.assertEqual(decode_process_output(line), "防火墙已启用")

    def test_replaces_unknown_bytes_instead_of_raising(self):
        decoded = decode_process_output(b"\xff\xfe\xfa\n")
        self.assertIsInstance(decoded, str)


if __name__ == "__main__":
    unittest.main()
