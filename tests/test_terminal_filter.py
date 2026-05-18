import unittest

from core.terminal_filter import strip_ansi_sequences


class TerminalFilterTest(unittest.TestCase):
    def test_strips_erase_line_sequence(self):
        self.assertEqual(strip_ansi_sequences("abc\x1b[K"), "abc")

    def test_strips_cursor_sequences(self):
        self.assertEqual(strip_ansi_sequences("a\x1b[D\x1b[Cz"), "az")

    def test_strips_osc_title_sequence(self):
        self.assertEqual(strip_ansi_sequences("x\x1b]0;title\x07y"), "xy")


if __name__ == "__main__":
    unittest.main()
