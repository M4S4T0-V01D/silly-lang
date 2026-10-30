"""C code for expressions. Every method returns a C expression string.

Evaluation order is left to right, as in the source: whenever a later operand
has side effects (or allocates), earlier operands are first stored in temps.
"""

import math

from .ir import E, is_place
from .types import (Prim, ListTy, ArrayTy, MapTy, TupleTy, FnTy, RefTy, NamedTy, VOID, NEVER, STR, CHAR, BOOL,
                    is_int, is_float, is_signed, has_list, int_bits, region_bearing)
from .cg_types import INT_C, is_scalar

LIT_KINDS = {"int", "float", "bool", "char", "str", "unit", "fnref"}   # "lambda" allocates: not pure
# Kinds that never allocate and never have side effects on their own.
PURE_KINDS = LIT_KINDS | {"local", "field", "tuple_field", "index", "str_index", "unary", "logic", "compare",
                          "ternary", "cast", "tuple", "struct", "variant", "array"}
INT_NAME = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}
MATH_H = {"sqrt", "cbrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "log", "log2", "log10",
          "pow", "hypot", "floor", "ceil", "fabs", "round", "trunc", "fmod", "sinh", "cosh", "tanh", "exp2",
          "expm1", "log1p", "fmin", "fmax", "copysign", "sqrtf", "sinf", "cosf", "fabsf", "floorf", "ceilf"}


def c_string(b):
    """A C string literal for the bytes b (octal escapes are always 3 digits)."""
    out = []
    for c in b:
        ch = chr(c)
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "?":
            out.append("\\?")
        elif 0x20 <= c < 0x7F:
            out.append(ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append("\\%03o" % c)
    return '"' + "".join(out) + '"'


def to_bytes(v):
    return v if isinstance(v, bytes) else str(v).encode("utf-8")


class ExprMixin:
    def init_expr(self):
        self.tmp_n = 0
        self.pure_memo = {}

    def tmp(self, prefix="_t"):
        self.tmp_n += 1
        return f"{prefix}{self.tmp_n}"

    def loc(self, span):
        if span is None:
            return '"<unknown>"'
        return c_string(f"{self.rel(span.file)}:{span.line}:{span.col}".encode())

    # ---- purity ----
    def pure(self, e):
        """True when evaluating e has no side effects and allocates nothing."""
        key = id(e)
        r = self.pure_memo.get(key)
        if r is None:
            r = self.pure_memo[key] = self._pure(e)
        return r

    def _pure(self, e):
        k = e.kind
        if k == "binary":
            return e.ty != STR and self.pure(e.left) and self.pure(e.right)
        if k == "slice":
            return e.ty == STR and self.pure(e.base) and all(self.pure(x) for x in (e.lo, e.hi) if x is not None)
        if k == "bi":
            return e.name in ("len", "abs", "min", "max") and all(self.pure(a) for a in e.args)
        if k not in PURE_KINDS:
            return False
        for name in ("base", "index", "operand", "left", "right", "cond", "then", "other", "value"):
            sub = getattr(e, name, None)
            if hasattr(sub, "kind") and not self.pure(sub):
                return False
        for name in ("elems", "fields", "args", "operands"):
            for sub in getattr(e, name, None) or ():
                if hasattr(sub, "kind") and not self.pure(sub):
                    return False
        return True

    def is_const(self, e):
        return e.kind in LIT_KINDS or (e.kind == "local" and not e.var.mutable and not e.var.is_ref)

    def simple_place(self, e):
        """A place whose C text can be evaluated twice: locals, fields and tuple fields of them."""
        while e.kind in ("field", "tuple_field"):
            e = e.base
        return e.kind == "local"

    # ---- sequencing ----
    def eval_seq(self, exprs, ctys=None):
        """C code for exprs evaluated strictly left to right: (prelude statements, values)."""
        pre, vals = [], []
        later_impure = [False] * len(exprs)
        acc = False
        for i in range(len(exprs) - 1, -1, -1):
            later_impure[i] = acc
            acc = acc or not self.pure(exprs[i])
        for i, e in enumerate(exprs):
            ct = ctys[i] if ctys else None
            v = self.value(e, ct)
            if later_impure[i] and not self.is_const(e):
                if e.ty in (VOID, NEVER):
                    pre.append(v + ";")
                    v = "(char)0" if e.ty == VOID else v
                else:
                    t = self.tmp()
                    pre.append(f"{ct or self.value_ctype(e.ty)} {t} = {v};")
                    v = t
            vals.append(v)
        return pre, vals

    @staticmethod
    def wrap(pre, result):
        if not pre:
            return result
        return "({ " + " ".join(pre) + " " + result + "; })"

    def value(self, e, cty=None):
        """C for e as a value; never/void become placeholders where a value is required."""
        c = self.expr(e)
        if e.ty == NEVER:
            ct = cty or "char"
            return f"({{ {c}; __builtin_unreachable(); ({ct}){{0}}; }})" if ct != "void" else c
        if e.ty == VOID and cty is not None and cty != "void":
            return f"({{ {c}; (char)0; }})"
        return c

    def expr(self, e):
        return getattr(self, "x_" + e.kind)(e)

    # ---- literals ----
    def int_lit(self, v, t):
        name = t.name if isinstance(t, Prim) else "i64"
        if name not in INT_NAME:
            name = "i64"
        if name.startswith("u"):
            v &= (1 << int_bits(t)) - 1 if name in INT_NAME else v
            s = f"{v}ULL"
        elif v == -(1 << 63):
            s = "(-9223372036854775807LL-1)"
        else:
            s = f"{v}LL" if v >= 0 else f"({v}LL)"
        return s if name in ("i64", "u64") else f"(({INT_C[name]}){s})"

    def x_int(self, e):
        if is_float(e.ty):
            return self.float_lit(float(e.value), e.ty)
        return self.int_lit(int(e.value), e.ty)

    def float_lit(self, v, t):
        if math.isnan(v):
            s = "__builtin_nan(\"\")"
        elif math.isinf(v):
            s = "__builtin_inf()" if v > 0 else "(-__builtin_inf())"
        else:
            s = repr(v)
            if "e" not in s and "." not in s:
                s += ".0"
            if v < 0:
                s = f"({s})"
        return f"((float){s})" if t.name == "f32" else s

    def x_float(self, e):
        return self.float_lit(float(e.value), e.ty)

    def x_bool(self, e):
        return "true" if e.value else "false"

    def x_char(self, e):
        v = e.value
        if isinstance(v, str):
            v = ord(v)
        return f"((uint32_t){int(v)})"

    def str_lit(self, b):
        b = to_bytes(b)
        if not b:
            return "SL_STR(\"\", 0)"
        return f"SL_STR({c_string(b)}, {len(b)})"

    def x_str(self, e):
        return self.str_lit(e.value)

    def x_unit(self, e):
        return "((void)0)"

    def x_fnref(self, e):
        return f"((sl_fn){{(void *){self.thunk(e.inst)}, NULL}})"

    def thunk(self, inst):
        """A wrapper giving a top-level function the calling convention of function values."""
        self.use_fn(inst)
        key = ("thunk", id(inst))
        name = self.helpers.get(key)
        if name is None:
            name = self.helpers[key] = "thk_" + inst.cname
            ps = [self.ctype(pt) for _, pt in inst.params]
            proto = f"static {self.ctype(inst.ret)} {name}(sl_env *_env" + "".join(f", {c} a{i}" for i, c in enumerate(ps)) + ")"
            target = self.extern_cname(inst) if inst.is_extern else inst.cname
            call = f"{target}({', '.join(f'a{i}' for i in range(len(ps)))})"
            body = f"{call};" if inst.ret in (VOID, NEVER) else f"return {call};"
            self.fn_protos.append(proto + ";")
            self.fn_defs.append(f"{proto} {{ (void)_env; {body} }}")
        return name

    def x_lambda(self, e):
        inst = e.inst
        self.use_fn(inst)
        if not e.caps:
            return f"((sl_fn){{(void *){inst.cname}, NULL}})"
        env = self.env_type(inst)
        c = self.tmp("_c")
        relocs = [v for v in inst.captures if region_bearing(v.ty)]
        reloc = f"envr_{inst.cname}" if relocs else "NULL"
        pre = [f"{env} *{c} = ({env} *)sl_alloc(sizeof({env}));",
               f"{c}->h.size = sizeof({env}); {c}->h.reloc = {reloc};"]
        for k, cap in enumerate(e.caps):
            pre.append(f"{c}->c{k} = {self.value(cap)};")
        return self.wrap(pre, f"(sl_fn){{(void *){inst.cname}, &{c}->h}}")

    def env_type(self, inst):
        """struct env_lam_N { sl_env h; captures... } and, if needed, its relocation function."""
        name = f"env_{inst.cname}"
        key = ("env", id(inst))
        if key in self.helpers:
            return name
        self.helpers[key] = name
        fields = "".join(f" {self.field_ctype(v.ty)} c{k};" for k, v in enumerate(inst.captures))
        self.forward.append(f"typedef struct {name} {name};")
        self.bodies.append(f"struct {name} {{ sl_env h;{fields} }};")
        relocs = [(k, v) for k, v in enumerate(inst.captures) if region_bearing(v.ty)]
        if relocs:
            proto = f"static void envr_{inst.cname}(sl_env *env, const uint8_t *lo, const uint8_t *hi)"
            body = " ".join(self.reloc_stmt(v.ty, f"&e->c{k}") for k, v in relocs)
            self.protos.append(proto + ";")
            self.helper_defs.append(f"{proto} {{ {name} *e = ({name} *)env; {body} }}")
        return name

    # ---- places ----
    def x_local(self, e):
        v = e.var
        return f"(*{v.cname})" if v.is_ref else v.cname

    def x_field(self, e):
        return f"{self.expr(e.base)}.f_{e.name}"

    def x_tuple_field(self, e):
        return f"{self.expr(e.base)}._{e.index}"

    def x_index(self, e):
        bt = e.base.ty
        loc = self.loc(e.span)
        if isinstance(bt, ArrayTy):
            i = self.expr(e.index)
            return f"{self.expr(e.base)}.a[sl_idx((int64_t)({i}), {bt.size}, {loc})]"
        ec = self.ctype(bt.elem)
        if self.simple_place(e.base):
            b = self.expr(e.base)
            return f"(({ec} *){b}.p)[sl_idx((int64_t)({self.expr(e.index)}), {b}.n, {loc})]"
        t = self.tmp("_l")
        if is_place(e.base):
            return (f"(*({{ sl_list *{t} = &{self.expr(e.base)}; "
                    f"&(({ec} *){t}->p)[sl_idx((int64_t)({self.expr(e.index)}), {t}->n, {loc})]; }}))")
        return (f"({{ sl_list {t} = {self.expr(e.base)}; "
                f"(({ec} *){t}.p)[sl_idx((int64_t)({self.expr(e.index)}), {t}.n, {loc})]; }})")

    def x_map_index(self, e):
        t = e.base.ty
        pre = []
        mp = self.map_ptr(e.base, pre)
        kv = self.map_key(t, e.key, pre)
        at = f"{self.map_at_fn(t)}({mp}, {kv}, {self.loc(e.span)})"
        if not pre:
            return f"(*{at})"
        return f"(*({{ {' '.join(pre)} {at}; }}))"

    def x_map(self, e):
        t = e.ty
        if not e.pairs:
            return "((sl_map){0})"
        kc, vc, en = self.ctype(t.k), self.field_ctype(t.v), self.entry_ctype(t)
        # Keys and values first, then the table (as for list literals).
        pre, kvs = [], []
        for k, v in e.pairs:
            kt, vt = self.tmp("_k"), self.tmp("_v")
            pre.append(f"{kc} {kt} = {self.value(k, kc)};")
            pre.append(f"{vc} {vt} = {self.value(v, vc)};")
            kvs.append((kt, vt))
        r, f = self.tmp("_m"), self.tmp("_f")
        pre.append(f"sl_map {r} = sl_map_with({len(kvs)}, sizeof({en})); bool {f};")
        put = self.map_put_fn(t)
        for kt, vt in kvs:
            pre.append(f"*{put}(&{r}, {kt}, &{f}) = {vt};")
        return self.wrap(pre, r)

    def x_str_index(self, e):
        pre, (b, i) = self.eval_seq([e.base, e.index])
        return self.wrap(pre, f"sl_str_at({b}, (int64_t)({i}), {self.loc(e.span)})")

    def addr(self, e):
        """Pointer to the storage of e (a temporary copy when e is not a place)."""
        if is_place(e):
            return f"&{self.expr(e)}"
        return f"({self.value_ctype(e.ty)}[1]){{{self.value(e)}}}"

    def x_slice(self, e):
        parts = [e.base] + [x for x in (e.lo, e.hi) if x is not None]
        pre, vals = self.eval_seq(parts)
        b = vals[0]
        rest = vals[1:]
        lo = f"(int64_t)({rest.pop(0)})" if e.lo is not None else "0"
        hi = f"(int64_t)({rest.pop(0)})" if e.hi is not None else "INT64_MAX"
        if e.ty == STR:
            return self.wrap(pre, f"sl_str_slice({b}, {lo}, {hi})")
        bt = e.base.ty
        ec = self.ctype(bt.elem)
        if isinstance(bt, ArrayTy):
            src, n = self.tmp("_a"), str(bt.size)
            pre.append(f"{self.ctype(bt)} {src} = {b};")
            p = f"{src}.a"
        else:
            src = self.tmp("_s")
            pre.append(f"sl_list {src} = {b};")
            p, n = f"(({ec} *){src}.p)", f"{src}.n"
        lt, ht, r = self.tmp("_lo"), self.tmp("_hi"), self.tmp("_r")
        pre.append(f"int64_t {lt} = {lo}, {ht} = {hi}; sl_slice_bounds(&{lt}, &{ht}, {n});")
        pre.append(f"sl_list {r} = sl_list_new({ht} - {lt}, sizeof({ec}));")
        pre.append(f"if ({r}.n) memcpy({r}.p, {p} + {lt}, (size_t){r}.n * sizeof({ec}));")
        return self.wrap(pre, r)

    # ---- operators ----
    def x_unary(self, e):
        v = self.expr(e.operand)
        if e.op == "!":
            return f"(!{v})"
        if is_float(e.ty):
            return f"(-{v})"
        ct = self.ctype(e.ty)
        if e.op == "-":
            return f"(({ct})(0 - {v}))"
        return f"(({ct})~{v})"

    def x_logic(self, e):
        op = "&&" if e.op == "and" else "||"
        return f"({self.expr(e.left)} {op} {self.expr(e.right)})"

    def x_binary(self, e):
        pre, (a, b) = self.eval_seq([e.left, e.right])
        return self.wrap(pre, self.binop(e.op, e.ty, a, b, e.right.ty, e.span))

    def binop(self, op, t, a, b, rt=None, span=None):
        if t == STR:
            return f"sl_str_concat({a}, {b})"
        ct = self.ctype(t)
        if is_float(t):
            f = "f" if t.name == "f32" else ""
            if op == "%":
                return f"sl_fmod{f}({a}, {b})"
            if op == "//":
                return f"floor{f}({a} / {b})"
            if op == "**":
                return f"pow{f}({a}, {b})"
            return f"({a} {op} {b})"
        name = t.name
        loc = self.loc(span)
        if op == "/":
            return f"sl_div_{name}({a}, {b}, {loc})"
        if op == "%":
            return f"sl_mod_{name}({a}, {b}, {loc})"
        if op == "//":
            return f"sl_fdiv_{name}({a}, {b}, {loc})"
        if op == "**":
            return f"sl_pow_{name}({a}, ({ct})({b}), {loc})"
        if op in ("<<", ">>"):
            mask = int_bits(t) - 1
            return f"(({ct})({a} {op} (({b}) & {mask})))"
        if op in ("&", "|", "^"):
            return f"(({ct})({a} {op} {b}))"
        if t == BOOL:
            return f"({a} {op} {b})"
        return f"(({ct})({a} {op} {b}))"

    def compare_code(self, op, t, a, b):
        if op == "==":
            return self.eq_code(t, a, b)
        if op == "!=":
            return f"(!{self.eq_code(t, a, b)})"
        if is_scalar(t):
            return f"({a} {op} {b})"
        return f"({self.cmp_code(t, a, b)} {op} 0)"

    def in_code(self, item_ty, cont_ty, x, c):
        if cont_ty == STR:
            if item_ty == CHAR:
                t, k = self.tmp("_cb"), self.tmp("_ck")
                return (f"({{ uint8_t {t}[4]; int {k} = sl_utf8_encode({x}, {t}); "
                        f"sl_str_contains({c}, (sl_str){{{t}, {k}}}); }})")
            return f"sl_str_contains({c}, {x})"
        if isinstance(cont_ty, MapTy):
            t = self.tmp("_s")
            return f"({{ sl_map {t} = {c}; {self.map_find_fn(cont_ty)}(&{t}, {x}) >= 0; }})"
        f = self.find_fn(cont_ty.elem)
        if isinstance(cont_ty, ArrayTy):
            t = self.tmp("_a")
            return f"({{ {self.ctype(cont_ty)} {t} = {c}; {f}({t}.a, {cont_ty.size}, {x}) >= 0; }})"
        ec = self.ctype(cont_ty.elem)
        t = self.tmp("_s")
        return f"({{ sl_list {t} = {c}; {f}(({ec} *){t}.p, {t}.n, {x}) >= 0; }})"

    def one_compare(self, op, l, r, a, b):
        if op == "in":
            return self.in_code(l.ty, r.ty, a, b)
        if op == "not in":
            return f"(!{self.in_code(l.ty, r.ty, a, b)})"
        return self.compare_code(op, l.ty, a, b)

    def x_compare(self, e):
        ops, xs = e.ops, e.operands
        if len(ops) == 1:
            pre, (a, b) = self.eval_seq(xs)
            return self.wrap(pre, self.one_compare(ops[0], xs[0], xs[1], a, b))
        # a < b < c: every operand is evaluated at most once, and the chain short-circuits.
        names = []
        pre = []
        for x in xs:
            if self.is_const(x) or (x.kind == "local"):
                names.append(self.expr(x))
            else:
                names.append(None)

        def build(i):
            parts = []
            for j in (i, i + 1):
                if names[j] is None:
                    t = self.tmp()
                    parts.append(f"{self.value_ctype(xs[j].ty)} {t} = {self.value(xs[j])};")
                    names[j] = t
            cur = self.one_compare(ops[i], xs[i], xs[i + 1], names[i], names[i + 1])
            if i + 1 < len(ops):
                cur = f"({cur} && {build(i + 1)})"
            return self.wrap(parts, cur)
        return self.wrap(pre, build(0))

    def x_ternary(self, e):
        ct = self.value_ctype(e.ty) if e.ty not in (VOID, NEVER) else None
        c = self.expr(e.cond)
        if ct is None:
            return f"({c} ? (void)({self.expr(e.then)}) : (void)({self.expr(e.other)}))"
        return f"({c} ? {self.value(e.then, ct)} : {self.value(e.other, ct)})"

    def x_cast(self, e):
        to, v = e.ty, e.value
        f = v.ty
        c = self.expr(v)
        if f == to:
            return c
        ct = self.ctype(to)
        if to == CHAR:
            return f"sl_chr((int64_t)({c}), {self.loc(e.span)})"
        if is_int(to) and is_float(f):
            return f"sl_f2i_{to.name}({c})"
        return f"(({ct})({c}))"

    # ---- aggregates ----
    def x_list(self, e):
        et = e.ty.elem
        ec = self.ctype(et)
        if not e.elems:
            return "((sl_list){0})"
        n = len(e.elems)
        lits = all(x.kind in ("int", "float", "bool", "char") for x in e.elems)
        r = self.tmp("_l")
        if lits and n > 4:
            d = self.tmp("_d")
            vals = ", ".join(self.expr(x) for x in e.elems)
            return (f"({{ static const {ec} {d}[{n}] = {{{vals}}}; sl_list {r} = sl_list_new({n}, sizeof({ec})); "
                    f"memcpy({r}.p, {d}, sizeof {d}); {r}; }})")
        # Elements first, then the buffer: the new list then ends at the top of the
        # data stack, so pushing onto it grows it in place.
        pre, vals = [], []
        for x in e.elems:
            if x.kind in LIT_KINDS:
                vals.append(self.value(x, ec))
            else:
                t = self.tmp()
                pre.append(f"{ec} {t} = {self.value(x, ec)};")
                vals.append(t)
        pre.append(f"sl_list {r} = sl_list_new({n}, sizeof({ec}));")
        for i, v in enumerate(vals):
            pre.append(f"(({ec} *){r}.p)[{i}] = {v};")
        return self.wrap(pre, r)

    def x_list_repeat(self, e):
        et = e.ty.elem
        ec = self.ctype(et)
        pre, (v, n) = self.eval_seq([e.value, e.count], [ec, "int64_t"])
        vt, nt, r = self.tmp("_v"), self.tmp("_n"), self.tmp("_l")
        pre.append(f"{ec} {vt} = {v}; int64_t {nt} = (int64_t)({n}); if ({nt} < 0) {nt} = 0;")
        pre.append(f"sl_list {r} = sl_list_new({nt}, sizeof({ec}));")
        if e.value.kind in ("int", "float", "bool", "char") and not e.value.value:
            pre.append(f"if ({nt}) memset({r}.p, 0, (size_t){nt} * sizeof({ec}));")
        else:
            pre.append(f"for (int64_t _i = 0; _i < {nt}; _i++) (({ec} *){r}.p)[_i] = "
                       f"{self.clone_code(et, vt) if has_list(et) else vt};")
        return self.wrap(pre, r)

    def x_list_concat(self, e):
        et = e.ty.elem
        ec = self.ctype(et)
        pre, (a, b) = self.eval_seq([e.left, e.right])
        at, bt, r = self.tmp("_a"), self.tmp("_b"), self.tmp("_l")
        pre.append(f"sl_list {at} = {a}, {bt} = {b};")
        # The left operand is moved into the result: grow it (in place when it is on top).
        pre.append(f"sl_list {r} = {at}; sl_list_reserve(&{r}, {at}.n + {bt}.n, sizeof({ec}));")
        pre.append(f"if ({bt}.n) memcpy(({ec} *){r}.p + {r}.n, {bt}.p, (size_t){bt}.n * sizeof({ec}));")
        pre.append(f"{r}.n += {bt}.n;")
        return self.wrap(pre, r)

    def x_str_repeat(self, e):
        pre, (s, n) = self.eval_seq([e.s, e.n])
        return self.wrap(pre, f"sl_str_repeat({s}, (int64_t)({n}))")

    def x_array(self, e):
        ec = self.field_ctype(e.ty.elem)
        pre, vals = self.eval_seq(e.elems, [ec] * len(e.elems))
        return self.wrap(pre, f"(({self.ctype(e.ty)}){{{{{', '.join(vals)}}}}})")

    def x_array_repeat(self, e):
        ct = self.ctype(e.ty)
        ec = self.field_ctype(e.ty.elem)
        v = e.value
        if v.kind in ("int", "float", "bool", "char") and not v.value:
            return f"(({ct}){{0}})"
        vt, a = self.tmp("_v"), self.tmp("_a")
        return (f"({{ {ec} {vt} = {self.value(v, ec)}; {ct} {a}; "
                f"for (int64_t _i = 0; _i < {e.ty.size}; _i++) {a}.a[_i] = {vt}; {a}; }})")

    def x_tuple(self, e):
        ctys = [self.field_ctype(x.ty) for x in e.elems]
        pre, vals = self.eval_seq(e.elems, ctys)
        return self.wrap(pre, f"(({self.ctype(e.ty)}){{{', '.join(vals)}}})")

    def x_struct(self, e):
        names = [fn for fn, _ in e.info.fields]
        ctys = [self.field_ctype(ft) for _, ft in e.info.fields]
        pre, vals = self.eval_seq(e.fields, ctys)
        inits = ", ".join(f".f_{n} = {v}" for n, v in zip(names, vals))
        return self.wrap(pre, f"(({self.ctype(e.ty)}){{{inits}}})")

    def x_variant(self, e):
        ct = self.ctype(e.ty)
        if not e.args:
            return f"(({ct}){{.tag = {e.vidx}}})"
        fs = e.info.variants[e.vidx][1]
        ctys = [self.field_ctype(ft) for _, ft in fs]
        pre, vals = self.eval_seq(e.args, ctys)
        return self.wrap(pre, f"(({ct}){{.tag = {e.vidx}, .u.v{e.vidx} = {{{', '.join(vals)}}}}})")

    # ---- f-strings ----
    def spec_lit(self, sp):
        fill = ord(sp["fill"]) if sp.get("fill") else 32
        align = f"'{sp['align']}'" if sp.get("align") else "0"
        sign = f"'{sp['sign']}'" if sp.get("sign") else "0"
        kind = f"'{sp['kind']}'" if sp.get("kind") else "0"
        prec = sp["prec"] if sp.get("prec") is not None else -1
        comma = "true" if sp.get("comma") else "false"
        return f"&(sl_spec){{{fill}, {align}, {sign}, {kind}, {comma}, {sp.get('width') or 0}, {prec}}}"

    def fmt_stmt(self, t, v, sp):
        if sp is None:
            return self.write_stmt(t, v)
        s = self.spec_lit(sp)
        kind = sp.get("kind")
        if is_float(t) or (is_int(t) and kind in ("e", "E", "f", "F", "g", "G", "%")):
            return f"sl_fmt_float({s}, (double)({v}));"
        if is_int(t):
            if is_signed(t):
                x = self.tmp("_x")
                return (f"{{ int64_t {x} = (int64_t)({v}); "
                        f"sl_fmt_int({s}, {x} < 0 ? 0 - (uint64_t){x} : (uint64_t){x}, {x} < 0); }}")
            return f"sl_fmt_int({s}, (uint64_t)({v}), false);"
        if t == CHAR and kind is not None and kind != "s":
            return f"sl_fmt_int({s}, (uint64_t)({v}), false);"
        if t == STR:
            return f"sl_fmt_str({s}, {v});"
        if t == CHAR:
            b = self.tmp("_cb")
            return f"{{ uint8_t {b}[4]; sl_fmt_str({s}, (sl_str){{{b}, sl_utf8_encode({v}, {b})}}); }}"
        f = self.tmp("_f")
        return f"{{ uint8_t *{f} = sl_ds.top; {self.write_stmt(t, v)} sl_pad({s}, {f}, '<', 0); }}"

    def x_fstr(self, e):
        # Values that allocate are computed before the builder opens; the builder
        # then writes the whole string contiguously at the top of the data stack.
        pre, body = [], []
        for p in e.parts:
            if isinstance(p, (bytes, str)):
                b = to_bytes(p)
                if b:
                    body.append(f"sl_w({c_string(b)}, {len(b)});")
                continue
            x, sp = p
            v = self.value(x)
            if not self.pure(x) or (not self.simple_place(x) and x.kind not in LIT_KINDS):
                t = self.tmp()
                pre.append(f"{self.value_ctype(x.ty)} {t} = {v};")
                v = t
            body.append(self.fmt_stmt(x.ty, v, sp))
        if not body:
            return self.wrap(pre, "SL_STR(\"\", 0)")
        b = self.tmp("_sb")
        return self.wrap(pre + [f"sl_sb {b} = sl_sb_begin();"] + body, f"sl_sb_end({b})")

    # ---- error propagation ----
    def x_try(self, e):
        st = e.src_ty
        info = st.info
        ok = info.vindex["Some" if e.is_option else "Ok"]
        t = self.tmp()
        pre = [f"{self.ctype(st)} {t} = {self.value(e.value)};"]
        rc = self.ctype(e.ret)
        rinfo = e.ret.info
        if e.is_option:
            out = f"(({rc}){{.tag = {rinfo.vindex['None']}}})"
        else:
            bad = info.vindex["Err"]
            ri = rinfo.vindex["Err"]
            out = f"(({rc}){{.tag = {ri}, .u.v{ri} = {{{t}.u.v{bad}.f0}}}})"
        pre.append(f"if ({t}.tag != {ok}) {{ {self.return_code(out)} }}")
        if e.ty in (VOID, NEVER) or not info.variants[ok][1]:
            return self.wrap(pre, "(void)0")
        return self.wrap(pre, f"{t}.u.v{ok}.f0")

    # ---- calls ----
    def arg_code(self, a, pt):
        if a.kind == "ref":
            return f"&{self.expr(a.place)}"
        if a.kind == "ref_tmp":
            return f"({self.value_ctype(a.value.ty)}[1]){{{self.value(a.value)}}}"
        return self.value(a, self.value_ctype(pt))

    def call_args(self, args, ptys):
        """Evaluate arguments left to right; references to temporaries stay inline."""
        later = [False] * len(args)
        acc = False
        for i in range(len(args) - 1, -1, -1):
            later[i] = acc
            a = args[i]
            inner = a.place if a.kind == "ref" else a.value if a.kind == "ref_tmp" else a
            acc = acc or not self.pure(inner)
        pre, vals = [], []
        for i, (a, pt) in enumerate(zip(args, ptys)):
            v = self.arg_code(a, pt)
            if later[i]:
                if a.kind == "ref" and not self.pure(a.place):
                    t = self.tmp("_p")
                    pre.append(f"{self.ctype(a.place.ty)} *{t} = {v};")
                    v = t
                elif a.kind not in ("ref", "ref_tmp") and not self.is_const(a):
                    t = self.tmp()
                    pre.append(f"{self.value_ctype(pt)} {t} = {v};")
                    v = t
                elif a.kind == "ref_tmp":
                    t = self.tmp()
                    pre.append(f"{self.value_ctype(a.value.ty)} {t} = {self.value(a.value)};")
                    v = f"&{t}"
            vals.append(v)
        return pre, vals

    def x_call(self, e):
        inst = e.inst
        self.use_fn(inst)
        args = list(e.args)
        ptys = [pt for _, pt in inst.params]
        if inst.self_ty is not None:
            recv = args[0]
            if isinstance(inst.self_ty, RefTy):
                inner = recv.place if recv.kind == "ref" else recv
                args[0] = E_ref(inner)
            ptys = [inst.self_ty] + ptys
        pre, vals = self.call_args(args, ptys)
        name = self.extern_cname(inst) if inst.is_extern else inst.cname
        return self.wrap(pre, f"{name}({', '.join(vals)})")

    def x_call_ind(self, e):
        ptys = e.fn.ty.params
        if e.fn.kind == "fnref":     # a known function: call it directly
            return self.x_call(E("call", e.ty, e.span, inst=e.fn.inst, args=e.args))
        f = self.expr(e.fn)
        fpre = []
        if not (e.fn.kind == "local" and not e.fn.var.is_ref and (self.is_const(e.fn) or
                                                                  all(self.pure(a) for a in e.args))):
            t = self.tmp("_fn")
            fpre = [f"sl_fn {t} = {f};"]
            f = t
        pre, vals = self.call_args(e.args, ptys)
        code = f"(({self.fnptr(e.fn.ty)}){f}.code)"
        return self.wrap(fpre + pre, f"{code}({', '.join([f + '.env'] + vals)})")

    def x_ref(self, e):
        return f"&{self.expr(e.place)}"

    def x_ref_tmp(self, e):
        return f"({self.value_ctype(e.value.ty)}[1]){{{self.value(e.value)}}}"

    def extern_cname(self, inst):
        name = inst.extern_name
        if name in MATH_H or inst.module.native:
            # math.h names, and the functions of a module's own `extern "file.c"`, which
            # come before all generated code and may be static.
            return name
        key = ("extern", name)
        if key not in self.helpers:
            self.helpers[key] = f"sl_ext_{name}"
            ps = ", ".join(self.ctype(pt) for _, pt in inst.params) or "void"
            self.protos.append(f'extern {self.ctype(inst.ret)} sl_ext_{name}({ps}) __asm__("{name}");')
        return self.helpers[key]

    # ---- patterns ----
    def x_is(self, e):
        pre = []
        if getattr(e, "init_var", None) is not None:
            pre.append(f"{e.init_var.cname} = {self.value(e.init, self.value_ctype(e.init.ty))};")
            subj = e.init_var.cname
        elif self.simple_place(e.src):
            subj = self.expr(e.src)
        else:
            p = self.tmp("_p")
            pre.append(f"{self.ctype(e.src.ty)} *{p} = &{self.expr(e.src)};")
            subj = f"(*{p})"
        return self.wrap(pre, self.pat(e.pattern, subj))

    def pat(self, p, subj):
        """A C condition testing subj against p; bindings are assigned as a side effect."""
        k = p.kind
        if k == "pwild":
            return "1"
        if k == "pbind":
            v = p.var
            return f"({{ {v.cname} = {subj}; 1; }})"
        if k == "plit":
            lit = p.value
            lc = self.expr(lit) if hasattr(lit, "kind") else self.raw_lit(lit, p.ty)
            return self.eq_code(p.ty, subj, lc)
        if k == "prange":
            parts = []
            if p.lo is not None:
                parts.append(f"{subj} >= {self.pat_bound(p.lo, p.ty)}")
            if p.hi is not None:
                parts.append(f"{subj} {'<=' if p.inclusive else '<'} {self.pat_bound(p.hi, p.ty)}")
            return "(" + (" && ".join(parts) or "1") + ")"
        if k == "ptuple":
            conds = [self.pat(s, f"{subj}._{i}") for i, s in enumerate(p.subs)]
            conds = [c for c in conds if c != "1"]
            return "(" + (" && ".join(conds) or "1") + ")"
        if k == "por":
            return "(" + " || ".join(self.pat(a, subj) for a in p.alts) + ")"
        if k == "pvariant":
            conds = [f"{subj}.tag == {p.vidx}"]
            for i, s in enumerate(p.subs or ()):
                c = self.pat(s, f"{subj}.u.v{p.vidx}.f{i}")
                if c != "1":
                    conds.append(c)
            return "(" + " && ".join(conds) + ")"
        raise AssertionError(f"pattern {k}")

    def pat_bound(self, b, t):
        return self.expr(b) if hasattr(b, "kind") else self.raw_lit(b, t)

    def raw_lit(self, v, t):
        if t == STR:
            return self.str_lit(v)
        if t == CHAR:
            return f"((uint32_t){ord(v) if isinstance(v, str) else int(v)})"
        if t == BOOL:
            return "true" if v else "false"
        if is_float(t):
            return self.float_lit(float(v), t)
        return self.int_lit(int(v), t)

    def x_seq(self, e):
        pre = []
        for s in e.stmts:
            pre.append(f"{s.var.cname} = ({self.value_ctype(s.var.ty)}){{0}};")
        return self.wrap(pre, self.expr(e.result))

    def x_bi(self, e):
        return getattr(self, "bi_" + e.name.replace(".", "_"))(e)


class E_ref:
    """A by-reference receiver: generated as the address of a place or temporary."""
    def __init__(self, inner):
        self.kind = "ref" if is_place(inner) else "ref_tmp"
        self.place = inner
        self.value = inner
        self.ty = RefTy(False, inner.ty)
