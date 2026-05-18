import unittest

from core.terminal_filter import PlainTerminalBuffer, strip_ansi_sequences


class TerminalFilterTest(unittest.TestCase):
    def test_strips_erase_line_sequence(self):
        self.assertEqual(strip_ansi_sequences("abc\x1b[K"), "abc")

    def test_strips_cursor_sequences(self):
        self.assertEqual(strip_ansi_sequences("a\x1b[D\x1b[Cz"), "az")

    def test_strips_osc_title_sequence(self):
        self.assertEqual(strip_ansi_sequences("x\x1b]0;title\x07y"), "xy")

    def test_terminal_buffer_handles_carriage_return_linefeed(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("first\r\nsecond")
        self.assertEqual(buffer.to_text(), "first\nsecond")

    def test_terminal_buffer_redraws_readline_history_line(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("jetson@nano:~/app$ py")
        buffer.feed("\r\x1b[Kjetson@nano:~/app$ python3 app.py")
        self.assertEqual(buffer.to_text(), "jetson@nano:~/app$ python3 app.py")

    def test_terminal_buffer_clears_tail_when_history_line_gets_shorter(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("jetson@nano:~/app$ python3 very-long-command.py")
        buffer.feed("\rjetson@nano:~/app$ ls\x1b[K")
        self.assertEqual(buffer.to_text(), "jetson@nano:~/app$ ls")

    def test_terminal_buffer_clears_line_when_history_moves_down_to_empty(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("jetson@nano:~/app$ python3 app.py")
        buffer.feed("\rjetson@nano:~/app$ \x1b[K")
        self.assertEqual(buffer.to_text(), "jetson@nano:~/app$ ")

    def test_terminal_buffer_handles_cursor_key_redraw_split_across_chunks(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("jetson@nano:~/app$ python3 app.py")
        buffer.feed("\rjetson@nano:~/app$ l")
        buffer.feed("s\x1b")
        buffer.feed("[K")
        self.assertEqual(buffer.to_text(), "jetson@nano:~/app$ ls")

    def test_terminal_buffer_keeps_incomplete_escape_for_next_chunk(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("prompt old\r\x1b")
        buffer.feed("[Kprompt new")
        self.assertEqual(buffer.to_text(), "prompt new")


if __name__ == "__main__":
    unittest.main()
