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
