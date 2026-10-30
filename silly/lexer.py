"""Tokenizer: Python-style significant indentation, C/Rust-style literals."""

import re

from .errors import SillyError, Span

KEYWORDS = {
    "fn", "let", "var", "const", "struct", "enum", "match", "case", "if", "elif",
    "else", "while", "for", "in", "loop", "break", "continue", "return", "and",
    "or", "not", "true", "false", "as", "import", "from", "pass", "mut", "extern",
    "is", "trait", "impl",
}

# Longest first so that greedy matching works.
OPERATORS = [
    "..=", "<<=", ">>=", "//=", "**",
    "==", "!=", "<=", ">=", "<<", ">>", "->", "=>", "..", "+=", "-=", "*=", "/=",
    "%=", "&=", "|=", "^=", "//",
    "+", "-", "*", "/", "%", "&", "|", "^", "~", "<", ">", "=", "(", ")", "[", "]",
    "{", "}", ",", ":", ".", "?", "@", ";",
]

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", "'": "'", '"': '"', "{": "{", "}": "}"}


class Token:
    __slots__ = ("kind", "value", "span")

    def __init__(self, kind, value, span):
        self.kind = kind    # NAME KW INT FLOAT STR FSTR CHAR OP NEWLINE INDENT DEDENT EOF
        self.value = value
        self.span = span

    def __repr__(self):
        return f"{self.kind}({self.value!r})@{self.span}"


class Lexer:
    def __init__(self, text, file):
        self.text = text
        self.file = file
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.indents = [0]
        self.depth = 0  # bracket nesting; newlines are ignored inside brackets

    def span(self):
        return Span(self.file, self.line, self.col)

    def err(self, msg, span=None):
        raise SillyError(msg, span or self.span())

    def peek(self, k=0):
        p = self.pos + k
        return self.text[p] if p < len(self.text) else ""

    def advance(self, n=1):
        for _ in range(n):
            c = self.text[self.pos]
            self.pos += 1
            if c == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1

    def add(self, kind, value, span):
        self.tokens.append(Token(kind, value, span))

    def tokenize(self):
        at_line_start = True
        while self.pos < len(self.text):
            if at_line_start and self.depth == 0:
                at_line_start = False
                if self.handle_indent():
                    continue
            c = self.peek()
            if c == "\n":
                if self.depth == 0 and self.tokens and self.tokens[-1].kind not in ("NEWLINE", "INDENT", "DEDENT"):
                    self.add("NEWLINE", None, self.span())
                self.advance()
                at_line_start = self.depth == 0
            elif c in " \t\r":
                self.advance()
            elif c == "#":
                while self.pos < len(self.text) and self.peek() != "\n":
                    self.advance()
            elif c == "\\" and self.peek(1) == "\n":
                self.advance(2)  # explicit line continuation
            elif c.isdigit():
                self.number()
            elif c.isalpha() or c == "_":
                self.name()
            elif c == '"':
                self.string(fmt=False)
            elif c == "f" and self.peek(1) == '"':
                pass  # unreachable: handled in name()
            elif c == "'":
                self.char()
            else:
                self.operator()
        if self.tokens and self.tokens[-1].kind not in ("NEWLINE", "DEDENT"):
            self.add("NEWLINE", None, self.span())
        while len(self.indents) > 1:
            self.indents.pop()
            self.add("DEDENT", None, self.span())
        self.add("EOF", None, self.span())
        return self.tokens

    def handle_indent(self):
        """Measure indentation at the start of a logical line. Returns True when the
        line is blank or a comment (so no INDENT/DEDENT should be produced)."""
        start = self.pos
        width = 0
        while self.peek() in (" ", "\t"):
            if self.peek() == "\t":
                self.err("tabs are not allowed for indentation; use spaces")
            width += 1
            self.advance()
        c = self.peek()
        if c in ("\n", "#", "\r", ""):
            return True
        sp = self.span()
        if width > self.indents[-1]:
            self.indents.append(width)
            self.add("INDENT", None, sp)
        else:
            while width < self.indents[-1]:
                self.indents.pop()
                self.add("DEDENT", None, sp)
            if width != self.indents[-1]:
                self.err("inconsistent dedent: does not match any outer indentation level", sp)
        return False

    def number(self):
        sp = self.span()
        start = self.pos
        is_float = False
        if self.peek() == "0" and self.peek(1) in "xXbBoO" and self.peek(1):
            base = {"x": 16, "b": 2, "o": 8}[self.peek(1).lower()]
            self.advance(2)
            s0 = self.pos
            while self.peek().isalnum() or self.peek() == "_":
                self.advance()
            raw = self.text[s0:self.pos]
            digits, suffix = raw, None
            m = re.match(r"^(.*?)_?(i8|i16|i32|i64|u8|u16|u32|u64|usize)$", raw)
            if m and (base != 16 or raw[len(m.group(1))] == "_"):
                digits, suffix = m.group(1), m.group(2)
            try:
                value = int(digits.replace("_", ""), base)
            except ValueError:
                self.err(f"invalid base-{base} literal", sp)
            self.add("INT", (value, suffix), sp)
            return
        while self.peek().isdigit() or self.peek() == "_":
            self.advance()
        if self.peek() == "." and self.peek(1).isdigit():
            is_float = True
            self.advance()
            while self.peek().isdigit() or self.peek() == "_":
                self.advance()
        if self.peek() in "eE" and self.peek() and (self.peek(1).isdigit() or (self.peek(1) in "+-" and self.peek(2).isdigit())):
            is_float = True
            self.advance(2)
            while self.peek().isdigit():
                self.advance()
        text = self.text[start:self.pos].replace("_", "")
        suffix = None
        if self.peek().isalpha():
            s0 = self.pos
            while self.peek().isalnum():
                self.advance()
            suffix = self.text[s0:self.pos]
            if suffix not in ("i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64", "int", "float", "usize"):
                self.err(f"unknown numeric suffix '{suffix}'", sp)
            if suffix in ("f32", "f64", "float"):
                is_float = True
        if is_float:
            if suffix and suffix not in ("f32", "f64", "float"):
                self.err("float literal with integer suffix", sp)
            self.add("FLOAT", (float(text), suffix), sp)
        else:
            self.add("INT", (int(text), suffix), sp)

    def name(self):
        sp = self.span()
        if self.peek() == "f" and self.peek(1) == '"':
            self.advance()
            self.string(fmt=True, sp=sp)
            return
        start = self.pos
        while self.peek().isalnum() or self.peek() == "_":
            self.advance()
        word = self.text[start:self.pos]
        self.add("KW" if word in KEYWORDS else "NAME", word, sp)

    def read_escape(self):
        self.advance()  # backslash
        c = self.peek()
        if c in ESCAPES:
            self.advance()
            return ESCAPES[c]
        if c == "x":
            self.advance()
            h = self.text[self.pos:self.pos + 2]
            self.advance(2)
            return chr(int(h, 16))
        if c == "u" and self.peek(1) == "{":
            self.advance(2)
            start = self.pos
            while self.peek() != "}":
                self.advance()
            h = self.text[start:self.pos]
            self.advance()
            return chr(int(h, 16))
        self.err(f"unknown escape sequence '\\{c}'")

    def string(self, fmt, sp=None):
        sp = sp or self.span()
        self.advance()  # opening quote
        parts = []
        buf = []
        while True:
            c = self.peek()
            if c == "" or c == "\n":
                self.err("unterminated string literal", sp)
            if c == '"':
                self.advance()
                break
            if c == "\\":
                buf.append(self.read_escape())
                continue
            if fmt and c == "{":
                if self.peek(1) == "{":
                    buf.append("{")
                    self.advance(2)
                    continue
                if buf:
                    parts.append("".join(buf))
                    buf = []
                parts.append(self.fstring_field())
                continue
            if fmt and c == "}":
                if self.peek(1) == "}":
                    buf.append("}")
                    self.advance(2)
                    continue
                self.err("single '}' in f-string; use '}}'")
            buf.append(c)
            self.advance()
        if fmt:
            if buf:
                parts.append("".join(buf))
            self.add("FSTR", parts, sp)
        else:
            self.add("STR", "".join(buf), sp)

    def fstring_field(self):
        """Returns (expr_text, spec, span) for one {expr:spec} field."""
        self.advance()  # {
        sp = self.span()
        start = self.pos
        depth = 0
        while True:
            c = self.peek()
            if c == "" or c == "\n":
                self.err("unterminated f-string field", sp)
            if c in "([{":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif c == "}" and depth == 0:
                break
            elif c == "}":
                depth -= 1
            elif c == ":" and depth == 0:
                break
            elif c == '"':
                self.err("string literals inside f-string fields are not supported", self.span())
            self.advance()
        expr = self.text[start:self.pos]
        spec = ""
        if self.peek() == ":":
            self.advance()
            s0 = self.pos
            while self.peek() not in ("}", "", "\n"):
                self.advance()
            spec = self.text[s0:self.pos]
        if self.peek() != "}":
            self.err("unterminated f-string field", sp)
        self.advance()
        if not expr.strip():
            self.err("empty expression in f-string", sp)
        return (expr, spec, sp)

    def char(self):
        sp = self.span()
        self.advance()
        if self.peek() == "\\":
            ch = self.read_escape()
        else:
            ch = self.peek()
            self.advance()
        if self.peek() != "'":
            self.err("character literal must contain exactly one character", sp)
        self.advance()
        self.add("CHAR", ord(ch), sp)

    def operator(self):
        sp = self.span()
        for op in OPERATORS:
            if self.text.startswith(op, self.pos):
                if op in ("(", "[", "{"):
                    self.depth += 1
                elif op in (")", "]", "}"):
                    self.depth = max(0, self.depth - 1)
                self.advance(len(op))
                self.add("OP", op, sp)
                return
        self.err(f"unexpected character {self.peek()!r}")


def tokenize(text, file="<input>"):
    return Lexer(text, file).tokenize()
