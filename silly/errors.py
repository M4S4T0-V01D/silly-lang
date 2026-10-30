"""Diagnostics shared by every compiler stage."""


class Span:
    __slots__ = ("file", "line", "col")

    def __init__(self, file, line, col):
        self.file = file
        self.line = line
        self.col = col

    def __repr__(self):
        return f"{self.file}:{self.line}:{self.col}"


class SillyError(Exception):
    def __init__(self, msg, span=None, hint=None):
        super().__init__(msg)
        self.msg = msg
        self.span = span
        self.hint = hint
        self.notes = []

    def render(self, sources):
        out = []
        if self.span is None:
            out.append(f"error: {self.msg}")
        else:
            s = self.span
            out.append(f"{s.file}:{s.line}:{s.col}: error: {self.msg}")
            text = sources.get(s.file)
            if text is not None:
                lines = text.split("\n")
                if 0 < s.line <= len(lines):
                    src = lines[s.line - 1]
                    out.append(f"  {s.line:>4} | {src}")
                    out.append("       | " + " " * (s.col - 1) + "^")
        if self.hint:
            out.append(f"  hint: {self.hint}")
        for n in self.notes:
            out.append(f"  note: {n}")
        return "\n".join(out)
