"""Recursive-descent parser producing silly.ast nodes."""

from . import ast as A
from .errors import SillyError
from .lexer import tokenize

COMPOUND_ASSIGN = {"=", "+=", "-=", "*=", "/=", "//=", "%=", "&=", "|=", "^=", "<<=", ">>="}
COMPARE_OPS = {"==", "!=", "<", "<=", ">", ">="}


class Parser:
    def __init__(self, tokens, file, text):
        self.toks = tokens
        self.i = 0
        self.file = file
        self.text = text

    # ---- token helpers ----
    @property
    def tok(self):
        return self.toks[self.i]

    def peek(self, k=1):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def at(self, kind, value=None):
        t = self.tok
        return t.kind == kind and (value is None or t.value == value)

    def at_op(self, *ops):
        return self.tok.kind == "OP" and self.tok.value in ops

    def at_kw(self, *kws):
        return self.tok.kind == "KW" and self.tok.value in kws

    def next(self):
        t = self.tok
        self.i += 1
        return t

    def accept(self, kind, value=None):
        if self.at(kind, value):
            return self.next()
        return None

    def expect(self, kind, value=None, what=None):
        if self.at(kind, value):
            return self.next()
        want = what or (repr(value) if value else kind.lower())
        got = self.describe(self.tok)
        raise SillyError(f"expected {want}, found {got}", self.tok.span)

    def describe(self, t):
        if t.kind == "NEWLINE":
            return "end of line"
        if t.kind in ("INDENT", "DEDENT"):
            return "change of indentation"
        if t.kind == "EOF":
            return "end of file"
        return repr(t.value) if t.kind in ("OP", "KW", "NAME") else t.kind.lower()

    def err(self, msg, span=None, hint=None):
        raise SillyError(msg, span or self.tok.span, hint)

    def ident(self, what="identifier"):
        return self.expect("NAME", what=what).value

    # ---- module ----
    def parse_module(self, name):
        items = []
        while not self.at("EOF"):
            if self.accept("NEWLINE"):
                continue
            items.append(self.item())
        return A.Module(name, items, self.file)

    def decorators(self):
        decos = []
        while self.at_op("@"):
            sp = self.next().span
            name = self.ident("decorator name")
            args = []
            if self.accept("OP", "("):
                while not self.at_op(")"):
                    args.append(self.expr())
                    if not self.accept("OP", ","):
                        break
                self.expect("OP", ")")
            decos.append((name, args, sp))
            self.expect("NEWLINE")
        return decos

    def item(self):
        decos = self.decorators()
        t = self.tok
        if self.at_kw("fn"):
            return self.fn_decl(decos)
        if self.at_kw("extern"):
            self.next()
            if self.at("STR") and not decos:
                # `extern "file.c"` compiles a C file next to this module into the program.
                f = self.next().value
                link = ""
                if self.at("NAME", "link"):
                    self.next()
                    link = self.expect("STR", what="a string of linker flags").value
                self.expect("NEWLINE")
                return A.Native(f, link, span=t.span)
            return self.fn_decl(decos, is_extern=True)
        if self.at_kw("struct"):
            return self.struct_decl(decos)
        if self.at_kw("enum"):
            return self.enum_decl(decos)
        if self.at_kw("trait"):
            return self.trait_decl(decos)
        if self.at_kw("impl"):
            return self.impl_decl(decos)
        if decos:
            self.err("decorators can only be applied to fn, struct, enum, trait and impl")
        if self.at_kw("const"):
            return self.const_decl()
        if self.at_kw("import"):
            self.next()
            path = self.dotted()
            alias = None
            if self.accept("KW", "as"):
                alias = self.ident()
            self.expect("NEWLINE")
            return A.Import(path, None, alias, span=t.span)
        if self.at_kw("from"):
            self.next()
            path = self.dotted()
            self.expect("KW", "import")
            names = [self.ident()]
            while self.accept("OP", ","):
                names.append(self.ident())
            self.expect("NEWLINE")
            return A.Import(path, names, None, span=t.span)
        if self.at_kw("let", "var"):
            self.err("top-level variables are not allowed; use `const` (Silly has no global mutable state)")
        self.err(f"expected a declaration (fn, struct, enum, trait, impl, const, import), found {self.describe(t)}")

    def dotted(self):
        parts = [self.ident("module name")]
        while self.accept("OP", "."):
            parts.append(self.ident("module name"))
        return ".".join(parts)

    def tparams(self):
        """`[T, U: Show + Eq]` -> (names, {name: [(trait name, span)]})."""
        tps, bounds = [], {}
        if self.accept("OP", "["):
            while not self.at_op("]"):
                name = self.ident("type parameter")
                tps.append(name)
                if self.accept("OP", ":"):
                    bounds[name] = [self.trait_name()]
                    while self.accept("OP", "+"):
                        bounds[name].append(self.trait_name())
                if not self.accept("OP", ","):
                    break
            self.expect("OP", "]")
        return tps, bounds

    def trait_name(self):
        sp = self.tok.span
        return self.dotted(), sp

    def fn_decl(self, decos, is_extern=False, in_type=False, in_trait=False):
        sp = self.expect("KW", "fn").span
        name = self.ident("function name")
        tps, bounds = self.tparams()
        self.expect("OP", "(")
        params = []
        self_mode = None
        first = True
        while not self.at_op(")"):
            psp = self.tok.span
            if first and in_type and (self.at("NAME", "self") or (self.at_kw("mut") and self.peek().kind == "NAME" and self.peek().value == "self")):
                self_mode = "mut" if self.accept("KW", "mut") else "ref"
                self.next()
            else:
                pname = self.ident("parameter name")
                self.expect("OP", ":", "':' and a parameter type")
                params.append(A.Param(pname, self.type_expr(allow_ref=True), span=psp))
            first = False
            if not self.accept("OP", ","):
                break
        self.expect("OP", ")")
        ret = None
        if self.accept("OP", "->"):
            ret = self.type_expr()
        if is_extern or (in_trait and self.at("NEWLINE")):
            self.expect("NEWLINE")
            body = None
        else:
            body = self.block()
        d = A.FnDecl(name, tps, params, ret, body, decos, self_mode, is_extern, span=sp)
        d.bounds = bounds
        return d

    def struct_decl(self, decos):
        sp = self.expect("KW", "struct").span
        name = self.ident("struct name")
        tps, bounds = self.tparams()
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT", what="an indented struct body")
        fields, methods = [], []
        while not self.accept("DEDENT"):
            if self.accept("NEWLINE"):
                continue
            if self.at("STR"):
                self.next()  # docstring
                self.expect("NEWLINE")
                continue
            if self.accept("KW", "pass"):
                self.expect("NEWLINE")
                continue
            if self.at_op("@") or self.at_kw("fn"):
                methods.append(self.fn_decl(self.decorators(), in_type=True))
                continue
            fsp = self.tok.span
            fname = self.ident("field name")
            self.expect("OP", ":")
            fields.append((fname, self.type_expr(), fsp))
            self.expect("NEWLINE")
        d = A.StructDecl(name, tps, fields, methods, decos, span=sp)
        d.bounds = bounds
        return d

    def enum_decl(self, decos):
        sp = self.expect("KW", "enum").span
        name = self.ident("enum name")
        tps, bounds = self.tparams()
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT", what="an indented enum body")
        variants, methods = [], []
        while not self.accept("DEDENT"):
            if self.accept("NEWLINE"):
                continue
            if self.at("STR"):
                self.next()
                self.expect("NEWLINE")
                continue
            if self.at_op("@") or self.at_kw("fn"):
                methods.append(self.fn_decl(self.decorators(), in_type=True))
                continue
            vsp = self.tok.span
            vname = self.ident("variant name")
            vfields = []
            if self.accept("OP", "("):
                while not self.at_op(")"):
                    if self.at("NAME") and self.peek().kind == "OP" and self.peek().value == ":":
                        fname = self.next().value
                        self.next()
                        vfields.append((fname, self.type_expr()))
                    else:
                        vfields.append((None, self.type_expr()))
                    if not self.accept("OP", ","):
                        break
                self.expect("OP", ")")
            variants.append(A.Variant(vname, vfields, span=vsp))
            self.expect("NEWLINE")
        d = A.EnumDecl(name, tps, variants, methods, decos, span=sp)
        d.bounds = bounds
        return d

    def method_block(self, what, in_trait=False):
        """An indented block of methods (and docstrings) for a trait or impl."""
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT", what=f"an indented {what} body")
        methods = []
        while not self.accept("DEDENT"):
            if self.accept("NEWLINE"):
                continue
            if self.at("STR"):
                self.next()
                self.expect("NEWLINE")
                continue
            if self.accept("KW", "pass"):
                self.expect("NEWLINE")
                continue
            if not (self.at_op("@") or self.at_kw("fn")):
                self.err(f"a {what} body can only contain methods, found {self.describe(self.tok)}")
            methods.append(self.fn_decl(self.decorators(), in_type=True, in_trait=in_trait))
        return methods

    def trait_decl(self, decos):
        sp = self.expect("KW", "trait").span
        name = self.ident("trait name")
        supers = []
        if self.accept("OP", "("):
            while not self.at_op(")"):
                supers.append(self.trait_name())
                if not self.accept("OP", ","):
                    break
            self.expect("OP", ")")
        return A.TraitDecl(name, supers, self.method_block("trait", in_trait=True), decos, span=sp)

    def impl_decl(self, decos):
        sp = self.expect("KW", "impl").span
        trait = self.trait_name()
        self.expect("KW", "for", "'for' and the implementing type")
        ty = self.type_expr()
        return A.ImplDecl(trait, ty, self.method_block("impl"), decos, span=sp)

    def const_decl(self):
        sp = self.expect("KW", "const").span
        name = self.ident("constant name")
        ty = None
        if self.accept("OP", ":"):
            ty = self.type_expr()
        self.expect("OP", "=")
        value = self.expr()
        self.expect("NEWLINE")
        return A.ConstDecl(name, ty, value, span=sp)

    # ---- types ----
    def type_expr(self, allow_ref=False):
        t = self.tok
        if self.at_op("&"):
            if not allow_ref:
                self.err("reference types are only allowed for function parameters",
                         hint="Silly references are second-class: they cannot be stored, returned or nested")
            self.next()
            mut = bool(self.accept("KW", "mut"))
            return A.TRef(mut, self.type_expr(), span=t.span)
        if self.accept("OP", "("):
            elems = []
            while not self.at_op(")"):
                elems.append(self.type_expr())
                if not self.accept("OP", ","):
                    break
            self.expect("OP", ")")
            return A.TTuple(elems, span=t.span)
        if self.accept("OP", "["):
            elem = self.type_expr()
            self.expect("OP", ";", "';' in array type [T; N]")
            size = self.expr()
            self.expect("OP", "]")
            return A.TArray(elem, size, span=t.span)
        if self.accept("KW", "fn"):
            self.expect("OP", "(")
            ps = []
            while not self.at_op(")"):
                ps.append(self.type_expr())
                if not self.accept("OP", ","):
                    break
            self.expect("OP", ")")
            ret = None
            if self.accept("OP", "->"):
                ret = self.type_expr()
            return A.TFn(ps, ret, span=t.span)
        name = self.ident("type")
        while self.at_op(".") and self.peek().kind == "NAME":
            self.next()
            name += "." + self.next().value
        args = []
        if self.accept("OP", "["):
            while not self.at_op("]"):
                args.append(self.type_expr())
                if not self.accept("OP", ","):
                    break
            self.expect("OP", "]")
        return A.TName(name, args, span=t.span)

    # ---- statements ----
    def block(self):
        self.expect("OP", ":", "':' to start a block")
        if not self.accept("NEWLINE"):
            # single-line block: `if x: return 1`
            return [self.simple_stmt()]
        self.expect("INDENT", what="an indented block")
        stmts = []
        while not self.accept("DEDENT"):
            if self.accept("NEWLINE"):
                continue
            stmts.append(self.stmt())
        return stmts

    def stmt(self):
        t = self.tok
        if t.kind == "KW":
            k = t.value
            if k == "if":
                return self.if_stmt()
            if k == "while":
                self.next()
                cond = self.expr()
                return A.While(cond, self.block(), span=t.span)
            if k == "loop":
                self.next()
                return A.Loop(self.block(), span=t.span)
            if k == "for":
                self.next()
                pat = self.for_pattern()
                self.expect("KW", "in")
                it = self.expr()
                return A.For(pat, it, self.block(), span=t.span)
            if k == "match":
                return self.match_stmt()
            if k in ("fn", "struct", "enum", "trait", "impl") and not (k == "fn" and self.peek().kind == "OP" and self.peek().value == "("):
                self.err("nested declarations are not supported; declare at the top level")
        if self.at("STR") and self.peek().kind == "NEWLINE":
            self.next()  # docstring / string comment
            self.next()
            return A.Pass(span=t.span)
        return self.simple_stmt()

    def simple_stmt(self):
        s = self.simple_stmt_inner()
        self.expect("NEWLINE")
        return s

    def simple_stmt_inner(self):
        t = self.tok
        if self.at_kw("let", "var"):
            mutable = self.next().value == "var"
            pat = self.let_pattern(mutable)
            ty = None
            if self.accept("OP", ":"):
                ty = self.type_expr()
            value = None
            if self.accept("OP", "="):
                value = self.expr()
            elif not mutable:
                self.err("`let` needs an initial value", hint="use `var name: Type` for a zero-initialised mutable variable")
            elif ty is None:
                self.err("`var` without a value needs a type annotation")
            return A.Let(mutable, pat, ty, value, span=t.span)
        if self.accept("KW", "return"):
            value = None
            if not self.at("NEWLINE"):
                value = self.expr()
            return A.Return(value, span=t.span)
        if self.accept("KW", "break"):
            return A.Break(span=t.span)
        if self.accept("KW", "continue"):
            return A.Continue(span=t.span)
        if self.accept("KW", "pass"):
            return A.Pass(span=t.span)
        if self.at("NAME", "assert"):
            self.next()
            cond = self.expr()
            msg = None
            if self.accept("OP", ","):
                msg = self.expr()
            return A.Assert(cond, msg, span=t.span)
        e = self.expr()
        if self.tok.kind == "OP" and self.tok.value in COMPOUND_ASSIGN:
            op = self.next().value
            value = self.expr()
            return A.Assign(e, op, value, span=t.span)
        return A.ExprStmt(e, span=t.span)

    def let_pattern(self, mutable):
        t = self.tok
        if self.accept("OP", "("):
            subs = []
            while not self.at_op(")"):
                subs.append(self.let_pattern(mutable))
                if not self.accept("OP", ","):
                    break
            self.expect("OP", ")")
            return A.PTuple(subs, span=t.span)
        name = self.ident("variable name")
        if name == "_":
            return A.PWild(span=t.span)
        return A.PBind(name, mutable, span=t.span)

    def for_pattern(self):
        t = self.tok
        first = self.let_pattern(False)
        if self.at_op(","):
            subs = [first]
            while self.accept("OP", ","):
                subs.append(self.let_pattern(False))
            return A.PTuple(subs, span=t.span)
        return first

    def if_stmt(self):
        t = self.expect("KW", "if")
        branches = [(self.expr(), self.block())]
        orelse = None
        while True:
            if self.accept("KW", "elif"):
                branches.append((self.expr(), self.block()))
            elif self.accept("KW", "else"):
                orelse = self.block()
                break
            else:
                break
        return A.If(branches, orelse, span=t.span)

    def match_stmt(self):
        t = self.expect("KW", "match")
        subject = self.expr()
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT", what="indented `case` arms")
        arms = []
        while not self.accept("DEDENT"):
            if self.accept("NEWLINE"):
                continue
            ct = self.expect("KW", "case", "`case`")
            pat = self.pattern()
            guard = None
            if self.accept("KW", "if"):
                guard = self.expr()
            arms.append(A.Arm(pat, guard, self.block(), span=ct.span))
        if not arms:
            self.err("match needs at least one case", t.span)
        return A.Match(subject, arms, span=t.span)

    # ---- patterns ----
    def pattern(self):
        t = self.tok
        p = self.pattern_primary()
        if self.at_op("|"):
            alts = [p]
            while self.accept("OP", "|"):
                alts.append(self.pattern_primary())
            return A.POr(alts, span=t.span)
        return p

    def pattern_primary(self):
        t = self.tok
        if self.accept("OP", "("):
            subs = []
            while not self.at_op(")"):
                subs.append(self.pattern())
                if not self.accept("OP", ","):
                    break
            self.expect("OP", ")")
            return A.PTuple(subs, span=t.span)
        if self.accept("KW", "mut"):
            return A.PBind(self.ident(), True, span=t.span)
        if t.kind == "NAME":
            if t.value == "_":
                self.next()
                return A.PWild(span=t.span)
            path = [self.next().value]
            while self.at_op(".") and self.peek().kind == "NAME":
                self.next()
                path.append(self.next().value)
            if self.at_op("("):
                self.next()
                subs = []
                while not self.at_op(")"):
                    subs.append(self.pattern())
                    if not self.accept("OP", ","):
                        break
                self.expect("OP", ")")
                return A.PVariant(path, subs, span=t.span)
            if len(path) == 1 and not path[0][0].isupper():
                return A.PBind(path[0], False, span=t.span)
            return A.PVariant(path, None, span=t.span)
        # literal or range
        lo = self.pattern_literal()
        if self.at_op("..", "..="):
            inclusive = self.next().value == "..="
            hi = self.pattern_literal()
            return A.PRange(lo, hi, inclusive, span=t.span)
        return A.PLit(lo, span=t.span)

    def pattern_literal(self):
        t = self.tok
        neg = bool(self.accept("OP", "-"))
        if t.kind == "OP" and not neg:
            self.err(f"expected a pattern, found {self.describe(t)}")
        t2 = self.next()
        if t2.kind == "INT":
            return A.IntLit(-t2.value[0] if neg else t2.value[0], t2.value[1], span=t.span)
        if t2.kind == "FLOAT":
            return A.FloatLit(-t2.value[0] if neg else t2.value[0], t2.value[1], span=t.span)
        if neg:
            self.err("expected a number after '-' in pattern", t2.span)
        if t2.kind == "STR":
            return A.StrLit(t2.value, span=t.span)
        if t2.kind == "CHAR":
            return A.CharLit(t2.value, span=t.span)
        if t2.kind == "KW" and t2.value in ("true", "false"):
            return A.BoolLit(t2.value == "true", span=t.span)
        self.err(f"expected a pattern, found {self.describe(t2)}", t2.span)

    # ---- expressions ----
    def expr(self):
        t = self.tok
        e = self.or_expr()
        if self.at_kw("if"):
            # Python-style conditional expression: a if cond else b
            self.next()
            cond = self.or_expr()
            self.expect("KW", "else", "`else` in conditional expression")
            other = self.expr()
            return A.Ternary(cond, e, other, span=t.span)
        return e

    def or_expr(self):
        e = self.and_expr()
        while self.at_kw("or"):
            sp = self.next().span
            e = A.Binary("or", e, self.and_expr(), span=sp)
        return e

    def and_expr(self):
        e = self.not_expr()
        while self.at_kw("and"):
            sp = self.next().span
            e = A.Binary("and", e, self.not_expr(), span=sp)
        return e

    def not_expr(self):
        if self.at_kw("not"):
            sp = self.next().span
            return A.Unary("not", self.not_expr(), span=sp)
        return self.compare()

    def compare(self):
        t = self.tok
        first = self.range_expr()
        if self.at_kw("is"):
            self.next()
            return A.Is(first, self.pattern(), span=t.span)
        ops, operands = [], [first]
        while True:
            if self.tok.kind == "OP" and self.tok.value in COMPARE_OPS:
                ops.append(self.next().value)
            elif self.at_kw("in"):
                self.next()
                ops.append("in")
            elif self.at_kw("not") and self.peek().kind == "KW" and self.peek().value == "in":
                self.next()
                self.next()
                ops.append("not in")
            else:
                break
            operands.append(self.range_expr())
        if not ops:
            return first
        return A.Compare(ops, operands, span=t.span)

    def range_expr(self):
        t = self.tok
        lo = self.bitor()
        if self.at_op("..", "..="):
            inclusive = self.next().value == "..="
            hi = self.bitor()
            return A.Range(lo, hi, inclusive, span=t.span)
        return lo

    def binary_level(self, ops, sub):
        e = sub()
        while self.tok.kind == "OP" and self.tok.value in ops:
            t = self.next()
            e = A.Binary(t.value, e, sub(), span=t.span)
        return e

    def bitor(self):
        return self.binary_level(("|",), self.bitxor)

    def bitxor(self):
        return self.binary_level(("^",), self.bitand)

    def bitand(self):
        return self.binary_level(("&",), self.shift)

    def shift(self):
        return self.binary_level(("<<", ">>"), self.additive)

    def additive(self):
        return self.binary_level(("+", "-"), self.term)

    def term(self):
        return self.binary_level(("*", "/", "%", "//"), self.cast)

    def cast(self):
        e = self.unary()
        while self.at_kw("as"):
            sp = self.next().span
            e = A.Cast(e, self.type_expr(), span=sp)
        return e

    def unary(self):
        t = self.tok
        if self.at_op("-", "~"):
            self.next()
            return A.Unary(t.value, self.unary(), span=t.span)
        if self.at_op("&"):
            self.next()
            mut = bool(self.accept("KW", "mut"))
            return A.Ref(mut, self.unary(), span=t.span)
        return self.power()

    def power(self):
        e = self.postfix()
        if self.at_op("**"):
            sp = self.next().span
            return A.Binary("**", e, self.unary(), span=sp)
        return e

    def postfix(self):
        e = self.primary()
        while True:
            t = self.tok
            if self.accept("OP", "("):
                args = []
                while not self.at_op(")"):
                    asp = self.tok.span
                    if self.at("NAME") and self.peek().kind == "OP" and self.peek().value == "=":
                        name = self.next().value
                        self.next()
                        args.append(A.Arg(name, self.expr(), span=asp))
                    else:
                        args.append(A.Arg(None, self.expr(), span=asp))
                    if not self.accept("OP", ","):
                        break
                self.expect("OP", ")", "')' or ',' in argument list")
                e = A.Call(e, args, span=t.span)
            elif self.accept("OP", "["):
                if self.at_op(":"):
                    lo = None
                else:
                    lo = self.expr()
                if self.accept("OP", ":"):
                    hi = None if self.at_op("]") else self.expr()
                    self.expect("OP", "]")
                    e = A.Slice(e, lo, hi, span=t.span)
                    continue
                idx = [lo]
                while self.accept("OP", ","):
                    idx.append(self.expr())
                self.expect("OP", "]")
                e = A.Index(e, idx, span=t.span)
            elif self.at_op(".") and self.peek().kind in ("NAME", "INT", "FLOAT"):
                self.next()
                nt = self.next()
                if nt.kind == "NAME":
                    e = A.Field(e, nt.value, span=nt.span)
                elif nt.kind == "INT":
                    e = A.Field(e, str(nt.value[0]), span=nt.span)
                else:
                    # `t.0.1` lexes as t . 0.1
                    a, b = repr(nt.value[0]).split(".")
                    e = A.Field(A.Field(e, a, span=nt.span), b, span=nt.span)
            elif self.at_op("?"):
                self.next()
                e = A.Try(e, span=t.span)
            else:
                return e

    def primary(self):
        t = self.tok
        k = t.kind
        if k == "INT":
            self.next()
            return A.IntLit(t.value[0], t.value[1], span=t.span)
        if k == "FLOAT":
            self.next()
            return A.FloatLit(t.value[0], t.value[1], span=t.span)
        if k == "STR":
            self.next()
            value = t.value
            while self.at("STR"):  # implicit concatenation of adjacent literals
                value += self.next().value
            return A.StrLit(value, span=t.span)
        if k == "FSTR":
            self.next()
            return self.fstring(t)
        if k == "CHAR":
            self.next()
            return A.CharLit(t.value, span=t.span)
        if k == "NAME":
            self.next()
            return A.Name(t.value, span=t.span)
        if k == "KW":
            if t.value in ("true", "false"):
                self.next()
                return A.BoolLit(t.value == "true", span=t.span)
            if t.value == "fn" and self.peek().kind == "OP" and self.peek().value == "(":
                return self.lambda_expr()
        if self.accept("OP", "("):
            if self.accept("OP", ")"):
                return A.TupleLit([], span=t.span)
            first = self.expr()
            if self.accept("OP", ")"):
                return first
            elems = [first]
            while self.accept("OP", ","):
                if self.at_op(")"):
                    break
                elems.append(self.expr())
            self.expect("OP", ")")
            return A.TupleLit(elems, span=t.span)
        if self.accept("OP", "["):
            if self.accept("OP", "]"):
                return A.ListLit([], span=t.span)
            first = self.expr()
            if self.accept("OP", ";"):
                count = self.expr()
                self.expect("OP", "]")
                return A.ArrayRepeat(first, count, span=t.span)
            elems = [first]
            while self.accept("OP", ","):
                if self.at_op("]"):
                    break
                elems.append(self.expr())
            self.expect("OP", "]")
            return A.ListLit(elems, span=t.span)
        if self.accept("OP", "{"):
            pairs = []
            while not self.at_op("}"):
                k = self.expr()
                self.expect("OP", ":")
                pairs.append((k, self.expr()))
                if not self.accept("OP", ","):
                    break
            self.expect("OP", "}")
            return A.MapLit(pairs, span=t.span)
        self.err(f"expected an expression, found {self.describe(t)}")

    def lambda_expr(self):
        """`fn(x, y: int) => expr`, or `fn(x: int) -> int:` + an indented block at the end of a line."""
        sp = self.expect("KW", "fn").span
        self.expect("OP", "(")
        params = []
        while not self.at_op(")"):
            psp = self.tok.span
            pname = self.ident("parameter name")
            pty = self.type_expr() if self.accept("OP", ":") else None
            params.append(A.Param(pname, pty, span=psp))
            if not self.accept("OP", ","):
                break
        self.expect("OP", ")")
        ret = self.type_expr() if self.accept("OP", "->") else None
        if self.accept("OP", "=>"):
            return A.Lambda(params, ret, self.expr(), True, span=sp)
        if not self.at_op(":"):
            self.err("expected '=>' and an expression, or ':' and an indented block, after a lambda's parameters")
        if self.peek().kind != "NEWLINE":
            self.err("a block lambda must end its line: `fn(x: int) -> int:` then an indented body",
                     hint="use `fn(x) => expr` for a one-line lambda")
        body = self.block()
        self.toks.insert(self.i, type(self.tok)("NEWLINE", None, self.tok.span))  # the line the block ended
        return A.Lambda(params, ret, body, False, span=sp)

    def fstring(self, t):
        parts = []
        for p in t.value:
            if isinstance(p, str):
                parts.append(p)
            else:
                src, spec, sp = p
                toks = tokenize("(" + src + ")", self.file)
                for tk in toks:  # remap positions into the enclosing line
                    tk.span.line = sp.line
                    tk.span.col = sp.col + max(0, tk.span.col - 2)
                sub = Parser(toks, self.file, self.text)
                e = sub.expr()
                if not sub.at("NEWLINE") and not sub.at("EOF"):
                    sub.err("unexpected tokens in f-string field")
                parts.append((e, spec))
        return A.FStr(parts, span=t.span)


def parse(text, file="<input>", name="main"):
    toks = tokenize(text, file)
    return Parser(toks, file, text).parse_module(name)
