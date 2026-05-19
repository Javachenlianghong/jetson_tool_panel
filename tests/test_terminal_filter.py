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

    def test_terminal_buffer_tracks_application_cursor_key_mode(self):
        buffer = PlainTerminalBuffer()
        self.assertFalse(buffer.application_cursor_keys)

        buffer.feed("\x1b[?1h")
        self.assertTrue(buffer.application_cursor_keys)

        buffer.feed("\x1b[?1l")
        self.assertFalse(buffer.application_cursor_keys)

    def test_terminal_buffer_keeps_application_cursor_mode_across_screen_clear(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("\x1b[?1h\x1b[2J")

        self.assertTrue(buffer.application_cursor_keys)

    def test_terminal_buffer_inserts_text_when_remote_enables_insert_mode(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("abcd\x1b[2D\x1b[4hX\x1b[4l")

        self.assertEqual(buffer.to_text(), "abXcd")
        self.assertFalse(buffer.insert_mode)

    def test_terminal_buffer_replaces_text_without_insert_mode(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("abcd\x1b[2DX")

        self.assertEqual(buffer.to_text(), "abXd")

    def test_terminal_buffer_handles_insert_character_sequence(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("abcd\x1b[2D\x1b[@X")

        self.assertEqual(buffer.to_text(), "abXcd")

    def test_terminal_buffer_backspace_moves_cursor_without_deleting_text(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("abcd\b\b")

        self.assertEqual(buffer.to_text(), "abcd")
        self.assertEqual(buffer.cursor_offset(), 2)

    def test_terminal_buffer_handles_readline_insert_redraw_after_left_key(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("abcd\b\bXcd\b\b")

        self.assertEqual(buffer.to_text(), "abXcd")
        self.assertEqual(buffer.cursor_offset(), 3)

    def test_terminal_buffer_handles_backspace_erase_echo(self):
        buffer = PlainTerminalBuffer()
        buffer.feed("abcd\b \b")

        self.assertEqual(buffer.to_text(), "abc ")
        self.assertEqual(buffer.cursor_offset(), 3)


if __name__ == "__main__":
    unittest.main()
