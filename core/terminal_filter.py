"""Small helpers for displaying SSH PTY output in a plain text widget."""

import re


ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-?]*[ -/]*[@-~]"
    r"|\][^\x07]*(?:\x07|\x1b\\)"
    r"|[PX^_].*?\x1b\\"
    r"|[@-Z\\-_]"
    r")"
)


def strip_ansi_sequences(text):
    return ANSI_ESCAPE_RE.sub("", str(text or ""))


class PlainTerminalBuffer:
    """A small terminal-like text buffer for readline-style SSH output."""

    def __init__(self):
        self.lines = [""]
        self.row = 0
        self.col = 0
        self._pending_escape = ""

    def clear(self):
        self.lines = [""]
        self.row = 0
        self.col = 0
        self._pending_escape = ""

    def feed(self, text):
        text = self._pending_escape + str(text or "")
        self._pending_escape = ""
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\x1b":
                sequence, next_index, incomplete = self._read_escape(text, index)
                if incomplete:
                    self._pending_escape = text[index:]
                    break
                self._handle_escape(sequence)
                index = next_index
                continue
            self._handle_char(char)
            index += 1

    def to_text(self):
        return "\n".join(self.lines)

    def cursor_offset(self):
        offset = 0
        self._ensure_cursor_line()
        for index, line in enumerate(self.lines):
            if index == self.row:
                return offset + min(self.col, len(line))
            offset += len(line) + 1
        return len(self.to_text())

    def _ensure_cursor_line(self):
        while self.row >= len(self.lines):
            self.lines.append("")

    def _current_line(self):
        self._ensure_cursor_line()
        return self.lines[self.row]

    def _read_escape(self, text, index):
        if index + 1 >= len(text):
            return "", len(text), True
        kind = text[index + 1]
        if kind == "[":
            cursor = index + 2
            while cursor < len(text):
                if "@" <= text[cursor] <= "~":
                    return text[index:cursor + 1], cursor + 1, False
                cursor += 1
            return "", len(text), True
        if kind == "]":
            return self._read_string_escape(text, index, index + 2)
        if kind in ("P", "X", "^", "_"):
            return self._read_string_escape(text, index, index + 2)
        if kind in ("(", ")", "*", "+", "-", ".", "/", "#", "%"):
            if index + 2 >= len(text):
                return "", len(text), True
            return text[index:index + 3], index + 3, False
        return text[index:index + 2], index + 2, False

    def _read_string_escape(self, text, index, start):
        bell_index = text.find("\x07", start)
        st_index = text.find("\x1b\\", start)
        endings = []
        if bell_index >= 0:
            endings.append((bell_index, bell_index + 1))
        if st_index >= 0:
            endings.append((st_index, st_index + 2))
        if not endings:
            return "", len(text), True
        _end_start, end_index = min(endings)
        return text[index:end_index], end_index, False

    def _handle_escape(self, sequence):
        if not sequence.startswith("\x1b["):
            return
        final = sequence[-1]
        body = sequence[2:-1]
        if body.startswith("?"):
            return
        params = body.split(";") if body else []

        def param(position, default):
            if position >= len(params) or params[position] == "":
                return default
            try:
                return int(params[position])
            except ValueError:
                return default

        count = max(1, param(0, 1))
        if final == "K":
            self._erase_line(param(0, 0))
        elif final == "J" and param(0, 0) in (2, 3):
            self.clear()
        elif final in ("G", "`"):
            self.col = max(0, param(0, 1) - 1)
        elif final == "C":
            self.col += count
        elif final == "D":
            self.col = max(0, self.col - count)
        elif final == "A":
            self.row = max(0, self.row - count)
            self.col = min(self.col, len(self._current_line()))
        elif final == "B":
            self.row += count
            self._ensure_cursor_line()
            self.col = min(self.col, len(self._current_line()))
        elif final in ("H", "f"):
            self.row = max(0, param(0, 1) - 1)
            self.col = max(0, param(1, 1) - 1)
            self._ensure_cursor_line()
        elif final == "P":
            self._delete_chars(count)
        elif final == "X":
            self._erase_chars(count)

    def _handle_char(self, char):
        if char == "\r":
            self.col = 0
        elif char == "\n":
            self._new_line()
        elif char in ("\b", "\x7f"):
            self._delete_previous_char()
        elif char == "\x07":
            return
        elif char == "\t":
            self._put_text("    ")
        elif ord(char) >= 32:
            self._put_text(char)

    def _new_line(self):
        if self.row >= len(self.lines) - 1:
            self.lines.append("")
            self.row = len(self.lines) - 1
        else:
            self.row += 1
        self.col = 0

    def _put_text(self, text):
        for char in text:
            line = self._current_line()
            if self.col > len(line):
                line += " " * (self.col - len(line))
            if self.col < len(line):
                line = line[:self.col] + char + line[self.col + 1:]
            else:
                line += char
            self.lines[self.row] = line
            self.col += 1

    def _delete_previous_char(self):
        if self.col <= 0:
            return
        line = self._current_line()
        self.col -= 1
        self.lines[self.row] = line[:self.col] + line[self.col + 1:]

    def _delete_chars(self, count):
        line = self._current_line()
        self.lines[self.row] = line[:self.col] + line[self.col + count:]

    def _erase_chars(self, count):
        line = self._current_line()
        if self.col >= len(line):
            return
        end = min(len(line), self.col + count)
        self.lines[self.row] = line[:self.col] + (" " * (end - self.col)) + line[end:]

    def _erase_line(self, mode):
        line = self._current_line()
        if mode == 1:
            self.lines[self.row] = (" " * min(self.col, len(line))) + line[self.col:]
        elif mode == 2:
            self.lines[self.row] = ""
            self.col = 0
        else:
            self.lines[self.row] = line[:self.col]
