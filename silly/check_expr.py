"""Expression checking: literals, names, operators, calls, constructors and generics."""

import difflib
import re

from . import ast as A
from .traits import PrimDecl
from .ir import E, is_place, place_path, root_var
from .types import (ALIASES, BOOL, CHAR, F64, FLOAT_TYPES, I64, INT_TYPES, NEVER, STR, U8, VOID, ArrayTy,
                    FnTy, ListTy, MapTy, NamedTy, is_hashable, Prim, RefTy, TParam, TupleTy, contains_tparam, int_range,
                    comparable, is_copy, is_float, is_int, is_numeric, is_signed, ordered, unify)

SPEC_RE = re.compile(r"^(?:(.)?([<>^]))?([+\- ])?(0)?(\d+)?(,)?(?:\.(\d+))?([bcdeEfFgosxX%])?$")


class ExprMixin:
    # ---- entry points ----
    def expr(self, e, exp):
        m = getattr(self, "ex_" + type(e).__name__, None)
        if m is None:
            self.err("this expression is not supported here", e.span)
        return m(e, exp)

    def value(self, e, exp):
        """An expression whose value is taken by value: non-Copy places are moved."""
        return self.consume(self.expr(e, exp), e.span)

    def expect_type(self, e, ty, span):
        if e.ty == ty or e.ty == NEVER:
            return
        hint = None
        if is_numeric(e.ty) and is_numeric(ty):
            hint = f"Silly never converts numbers implicitly; write `(...) as {ty}`"
        elif ty == STR and e.ty != STR:
            hint = "convert with str(x) or use an f-string"
        elif isinstance(ty, NamedTy) and ty.decl.name == "Option" and e.ty == ty.args[0]:
            hint = "wrap the value: Some(x)"
        self.err(f"expected {ty}, found {e.ty}", span, hint=hint)

    def is_untyped_lit(self, e):
        if isinstance(e, A.Unary) and e.op == "-":
            e = e.expr
        return isinstance(e, (A.IntLit, A.FloatLit)) and not e.suffix

    # ---- literals ----
    def ex_IntLit(self, e, exp, neg=False):
        v = -e.value if neg else e.value
        if e.suffix:
            name = ALIASES.get(e.suffix, e.suffix)
            if name in FLOAT_TYPES:
                return E("float", Prim(name), e.span, value=float(v))
            ty = Prim(name)
        elif exp is not None and is_int(exp):
            ty = exp
        elif exp is not None and is_float(exp):
            return E("float", exp, e.span, value=float(v))
        else:
            ty = I64
        lo, hi = int_range(ty)
        if not lo <= v <= hi:
            self.err(f"integer literal {v} does not fit in {ty} (range {lo}..={hi})", e.span)
        return E("int", ty, e.span, value=v)

    def ex_FloatLit(self, e, exp, neg=False):
        v = -e.value if neg else e.value
        if e.suffix:
            ty = Prim(ALIASES.get(e.suffix, e.suffix))
        elif exp is not None and is_float(exp):
            ty = exp
        else:
            ty = F64
        return E("float", ty, e.span, value=v)

    def ex_StrLit(self, e, exp):
        return E("str", STR, e.span, value=e.value.encode("utf-8"))

    def ex_CharLit(self, e, exp):
        if exp == U8:
            if e.value > 255:
                self.err("character does not fit in a u8", e.span)
            return E("int", U8, e.span, value=e.value)
        return E("char", CHAR, e.span, value=e.value)

    def ex_BoolLit(self, e, exp):
        return E("bool", BOOL, e.span, value=e.value)

    def ex_FStr(self, e, exp):
        parts = []
        for p in e.parts:
            if isinstance(p, str):
                if p:
                    parts.append(p.encode("utf-8"))
                continue
            sub, spec = p
            v = self.expr(sub, None)
            if v.ty in (VOID, NEVER):
                self.err("this expression has no value to format", sub.span)
            self.printable(v.ty, sub.span)
            parts.append((v, self.parse_spec(spec, v.ty, sub.span)))
        return E("fstr", STR, e.span, parts=parts)

    def parse_spec(self, spec, ty, span):
        if not spec:
            return None
        m = SPEC_RE.match(spec)
        if not m:
            self.err(f"invalid format spec '{spec}'", span,
                     hint="format specs look like :>8, :<5, :^9, :08.3f, :x, :,")
        fill, align, sign, zero, width, comma, prec, kind = m.groups()
        if kind in ("b", "o", "x", "X", "d", "c") and not (is_int(ty) or ty == CHAR):
            self.err(f"format ':{kind}' needs an integer, found {ty}", span)
        if kind in ("e", "E", "f", "F", "g", "%") and not is_numeric(ty):
            self.err(f"format ':{kind}' needs a number, found {ty}", span)
        if (prec is not None and kind is None) and not (is_numeric(ty) or ty == STR):
            self.err(f"precision is not allowed for {ty}", span)
        if (sign or comma) and not is_numeric(ty):
            self.err(f"sign/grouping options need a number, found {ty}", span)
        return dict(fill=fill or (" " if not zero else "0"), align=align or ("=" if zero else None), sign=sign,
                    width=int(width) if width else 0, comma=bool(comma),
                    prec=int(prec) if prec is not None else None, kind=kind, zero=bool(zero))

    # ---- names & static paths ----
    def ex_Name(self, e, exp):
        v = self.lookup_var(e.name)
        if v is not None:
            if v.id in self.moved:
                sp = self.moved[v.id]
                self.err(f"'{e.name}' was moved at line {sp.line} and can no longer be used", e.span,
                         hint=f"use `{e.name}.clone()` at line {sp.line} if you need to keep it")
            if getattr(v, "captured", False) and v.use_span is None:
                v.use_span = e.span
            return E("local", v.ty, e.span, var=v)
        st = self.static(e)
        if st is not None:
            return self.static_value(st, e, exp)
        self.unknown_name(e.name, e.span)

    def unknown_name(self, name, span):
        cands = [n for s in self.scopes for n in s] + list(self.mod.scope)
        close = difflib.get_close_matches(name, cands, n=1)
        self.err(f"unknown name '{name}'", span, hint=f"did you mean '{close[0]}'?" if close else None)

    def static(self, e):
        """Resolve a Name/Field/Index chain that names a module-level item."""
        if isinstance(e, A.Name):
            if self.lookup_var(e.name) is not None:
                return None
            return self.mod.scope.get(e.name) or self.type_entry(e.name)
        if isinstance(e, A.Field):
            base = self.static(e.base)
            if base is None:
                return None
            kind, payload, m = base[:3]
            targs = base[3] if len(base) > 3 else None
            if kind == "module":
                ent = payload.scope.get(e.name)
                if ent is None or ent[2] is not payload:
                    self.err(f"module '{payload.name}' has no item '{e.name}'", e.span)
                return ent
            if kind in ("struct", "enum"):
                decl = payload
                if kind == "enum":
                    for i, v in enumerate(decl.variants):
                        if v.name == e.name:
                            return ("variant", (decl, i), m, targs)
                for md in decl.methods:
                    if md.name == e.name:
                        return ("method", (decl, md), m, targs)
                ent = self.type_method_entry(decl, e.name, e.span)
                if ent is not None:
                    return ent + (m, targs)
                self.err(f"type '{decl.name}' has no variant or method '{e.name}'", e.span)
            if kind == "prim":
                ent = self.type_method_entry(payload, e.name, e.span)
                if ent is None:
                    self.err(f"no trait gives {payload} a function '{e.name}'", e.span)
                return ent + (m, None)
            if kind == "trait":
                for md in payload.methods:
                    if md.name == e.name:
                        return ("trait_method", (payload, md), m)
                self.err(f"trait '{payload.name}' has no method '{e.name}'", e.span)
            return None
        if isinstance(e, A.Index):
            base = self.static(e.base)
            if base is not None and base[0] in ("struct", "enum", "fn"):
                targs = [self.prog.resolve_type(self.expr_to_type(i), self.env, self.mod) for i in e.indices]
                return base[:3] + (targs,)
        return None

    def expr_to_type(self, e):
        if isinstance(e, A.Name):
            return A.TName(e.name, [], span=e.span)
        if isinstance(e, A.Field):
            base = self.expr_to_type(e.base)
            if not isinstance(base, A.TName) or base.args:
                self.err("expected a type", e.span)
            return A.TName(base.name + "." + e.name, [], span=e.span)
        if isinstance(e, A.Index):
            base = self.expr_to_type(e.base)
            return A.TName(base.name, [self.expr_to_type(i) for i in e.indices], span=e.span)
        if isinstance(e, A.TupleLit):
            return A.TTuple([self.expr_to_type(i) for i in e.elems], span=e.span)
        if isinstance(e, A.ArrayRepeat):
            return A.TArray(self.expr_to_type(e.elem), e.count, span=e.span)
        self.err("expected a type", e.span)

    def static_value(self, st, e, exp):
        kind, payload = st[0], st[1]
        targs = st[3] if len(st) > 3 else None
        if kind == "const":
            return self.const_value(payload, st[2], e.span)
        if kind == "fn":
            decl = payload
            if decl.tparams and not targs:
                self.err(f"generic function '{decl.name}' needs explicit type arguments to be used as a value",
                         e.span, hint=f"write {decl.name}[T, ...]")
            inst = self.prog.fn_inst(decl, None, targs or [], st[2], e.span)
            if any(isinstance(p, RefTy) for _, p in inst.params):
                self.err(f"function '{decl.name}' takes reference parameters and cannot be used as a value", e.span)
            return E("fnref", inst.fn_ty, e.span, inst=inst)
        if kind == "variant":
            decl, i = payload
            if decl.variants[i].fields:
                self.err(f"variant '{decl.variants[i].name}' needs arguments", e.span,
                         hint=f"{decl.variants[i].name}(...)")
            return self.make_variant(decl, i, targs, [], exp, e.span)
        if kind == "method":
            self.err("methods cannot be used as values", e.span)
        if kind == "trait_method":
            self.err("trait methods cannot be used as values", e.span, hint="wrap it: fn(x) => x.method()")
        what = {"module": "a module", "struct": "a type", "enum": "a type", "prim": "a type",
                "trait": "a trait"}.get(kind, kind)
        self.err(f"'{getattr(payload, 'name', '?')}' is {what}, not a value", e.span)

    # ---- constants ----
    def const_value(self, decl, mod, span):
        key = id(decl)
        cache = self.prog.consts
        if key in cache:
            if cache[key] is None:
                self.err(f"constant '{decl.name}' is defined in terms of itself", span)
            return cache[key]
        cache[key] = None
        ty = self.prog.resolve_type(decl.type, {}, mod) if decl.type is not None else None
        val, vty = self.fold(decl.value, mod, ty)
        ty = ty or vty
        kinds = {"int": is_int, "float": is_float}
        if is_int(ty):
            if isinstance(val, float) or isinstance(val, bool):
                self.err(f"constant '{decl.name}' must be an integer", decl.value.span)
            lo, hi = int_range(ty)
            if not lo <= val <= hi:
                self.err(f"constant value {val} does not fit in {ty}", decl.value.span)
            r = E("int", ty, span, value=val)
        elif is_float(ty):
            r = E("float", ty, span, value=float(val))
        elif ty == BOOL:
            r = E("bool", ty, span, value=bool(val))
        elif ty == STR:
            r = E("str", ty, span, value=val)
        elif ty == CHAR:
            r = E("char", ty, span, value=val)
        else:
            self.err("constants must be numbers, bools, chars or strings", decl.span)
        del kinds
        cache[key] = r
        return r

    def fold(self, e, mod, ty):
        """Evaluate a constant expression at compile time. Returns (python value, type)."""
        if isinstance(e, A.IntLit):
            t = Prim(ALIASES.get(e.suffix, e.suffix)) if e.suffix else (ty if ty and is_numeric(ty) else I64)
            return (float(e.value) if is_float(t) else e.value), t
        if isinstance(e, A.FloatLit):
            return e.value, (Prim(ALIASES.get(e.suffix, e.suffix)) if e.suffix else (ty if ty and is_float(ty) else F64))
        if isinstance(e, A.BoolLit):
            return e.value, BOOL
        if isinstance(e, A.StrLit):
            return e.value.encode("utf-8"), STR
        if isinstance(e, A.CharLit):
            return e.value, CHAR
        if isinstance(e, A.Name):
            ent = mod.scope.get(e.name)
            if ent is None or ent[0] != "const":
                self.err(f"'{e.name}' is not a constant", e.span)
            r = self.const_value(ent[1], ent[2], e.span)
            return r.value, r.ty
        if isinstance(e, A.Unary):
            v, t = self.fold(e.expr, mod, ty)
            if e.op == "-" and is_numeric(t):
                return -v, t
            if e.op == "~" and is_int(t):
                return ~v, t
            if e.op == "not" and t == BOOL:
                return not v, t
        if isinstance(e, A.Binary):
            a, ta = self.fold(e.left, mod, ty)
            b, tb = self.fold(e.right, mod, ta)
            if ta != tb and not (e.op in ("<<", ">>") and is_int(ta) and is_int(tb)):
                self.err(f"constant operands have different types: {ta} and {tb}", e.span)
            op = e.op
            try:
                if ta == STR and op == "+":
                    return a + b, STR
                if is_numeric(ta):
                    if op == "+": return a + b, ta
                    if op == "-": return a - b, ta
                    if op == "*": return a * b, ta
                    if op == "**": return a ** b, ta
                    if op == "/":
                        return (a / b if is_float(ta) else int(a / b) if abs(a) < 2 ** 52 else
                                (abs(a) // abs(b)) * (1 if (a < 0) == (b < 0) else -1)), ta
                    if op == "//": return a // b, ta
                    if op == "%": return a % b, ta
                if is_int(ta):
                    if op == "<<": return a << b, ta
                    if op == ">>": return a >> b, ta
                    if op == "&": return a & b, ta
                    if op == "|": return a | b, ta
                    if op == "^": return a ^ b, ta
                if ta == BOOL and op in ("and", "or"):
                    return (a and b) if op == "and" else (a or b), BOOL
            except ZeroDivisionError:
                self.err("division by zero in constant expression", e.span)
        self.err("this expression cannot be evaluated at compile time", e.span)

    # ---- fields, indexing ----
    def ex_Field(self, e, exp):
        st = self.static(e)
        if st is not None:
            return self.static_value(st, e, exp)
        base = self.expr(e.base, None)
        t = base.ty
        if isinstance(t, TupleTy):
            if not e.name.isdigit() or int(e.name) >= len(t.elems):
                self.err(f"tuple {t} has no field '{e.name}'", e.span)
            i = int(e.name)
            return E("tuple_field", t.elems[i], e.span, base=base, index=i, name=e.name)
        if isinstance(t, NamedTy) and not t.is_enum:
            info = t.info
            if e.name in info.field_index:
                i = info.field_index[e.name]
                return E("field", info.fields[i][1], e.span, base=base, name=e.name, index=i, info=info)
            if e.name in info.methods:
                self.err(f"'{e.name}' is a method; call it with ()", e.span)
            close = difflib.get_close_matches(e.name, list(info.field_index), n=1)
            self.err(f"{t} has no field '{e.name}'", e.span, hint=f"did you mean '{close[0]}'?" if close else None)
        if isinstance(t, NamedTy) and e.name in t.info.methods:
            self.err(f"'{e.name}' is a method; call it with ()", e.span)
        self.err(f"{t} has no field '{e.name}'", e.span,
                 hint="call it with () if it is a method" if not isinstance(t, NamedTy) else None)

    def index_int(self, e):
        i = self.expr(e, I64)
        if not is_int(i.ty):
            self.err(f"indices must be integers, found {i.ty}", e.span)
        return i

    def ex_Index(self, e, exp):
        st = self.static(e)
        if st is not None:
            return self.static_value(st, e, exp)
        base = self.expr(e.base, None)
        if len(e.indices) != 1:
            self.err("only one index is allowed", e.span)
        t = base.ty
        if isinstance(t, MapTy):
            k = self.typed(e.indices[0], t.k)
            return E("map_index", t.v, e.span, base=base, key=k)
        idx = self.index_int(e.indices[0])
        if isinstance(t, (ListTy, ArrayTy)):
            if isinstance(t, ArrayTy) and idx.kind == "int" and not 0 <= idx.value < t.size:
                self.err(f"index {idx.value} is out of bounds for {t}", e.indices[0].span)
            return E("index", t.elem, e.span, base=base, index=idx)
        if t == STR:
            return E("str_index", U8, e.span, base=base, index=idx)
        self.err(f"cannot index a value of type {t}", e.span)

    def ex_Slice(self, e, exp):
        base = self.expr(e.base, None)
        lo = self.index_int(e.lo) if e.lo is not None else None
        hi = self.index_int(e.hi) if e.hi is not None else None
        t = base.ty
        if t == STR:
            return E("slice", STR, e.span, base=base, lo=lo, hi=hi)
        if isinstance(t, (ListTy, ArrayTy)):
            if not is_copy(t.elem):
                self.err(f"slicing copies elements, but {t.elem} is not Copy", e.span,
                         hint="clone the list first, or loop over the indices")
            return E("slice", ListTy(t.elem), e.span, base=base, lo=lo, hi=hi)
        self.err(f"cannot slice a value of type {t}", e.span)

    # ---- operators ----
    def operands(self, la, ra, exp):
        if self.is_untyped_lit(la) and not self.is_untyped_lit(ra):
            r = self.expr(ra, exp)
            l = self.expr(la, r.ty)
        else:
            l = self.expr(la, exp)
            r = self.expr(ra, l.ty)
        return l, r

    def ex_Unary(self, e, exp):
        if e.op == "-" and isinstance(e.expr, A.IntLit):
            return self.ex_IntLit(e.expr, exp, neg=True)
        if e.op == "-" and isinstance(e.expr, A.FloatLit):
            return self.ex_FloatLit(e.expr, exp, neg=True)
        if e.op == "not":
            v = self.expr(e.expr, BOOL)
            self.expect_type(v, BOOL, e.expr.span)
            return E("unary", BOOL, e.span, op="!", operand=v)
        v = self.expr(e.expr, exp)
        if e.op == "-":
            if not (is_float(v.ty) or (is_int(v.ty) and is_signed(v.ty))):
                self.err(f"cannot negate a value of type {v.ty}", e.span)
            return E("unary", v.ty, e.span, op="-", operand=v)
        if e.op == "~":
            if not is_int(v.ty):
                self.err(f"'~' needs an integer, found {v.ty}", e.span)
            return E("unary", v.ty, e.span, op="~", operand=v)
        self.err(f"unknown operator {e.op}", e.span)

    def ex_Ref(self, e, exp):
        self.err("`&` can only be used on a function argument", e.span,
                 hint="Silly references are second-class: they are passed to calls, never stored")

    def ex_Range(self, e, exp):
        self.err("ranges can only be used in `for` loops and `case` patterns", e.span,
                 hint="build a list with range: `var xs: list[int] = []` then push in a loop")

    def ex_Is(self, e, exp):
        return self.is_expr(e)

    def check_arith(self, op, lt, rt, span):
        if op in ("<<", ">>"):
            if not (is_int(lt) and is_int(rt)):
                self.err(f"shifts need integers, found {lt} {op} {rt}", span)
            return
        if lt != rt:
            hint = None
            if is_numeric(lt) and is_numeric(rt):
                hint = f"convert one side explicitly, e.g. `x as {lt}`"
            elif STR in (lt, rt):
                hint = "use an f-string or str(x) to build strings"
            self.err(f"operator '{op}' needs both sides to have the same type, found {lt} and {rt}", span,
                     hint=hint)
        if op in ("&", "|", "^"):
            if not (is_int(lt) or lt == BOOL):
                self.err(f"operator '{op}' needs integers or bools, found {lt}", span)
            return
        if not is_numeric(lt):
            self.err(f"operator '{op}' needs numbers, found {lt}", span)

    def ex_Binary(self, e, exp):
        op = e.op
        if op in ("and", "or"):
            l = self.expr(e.left, BOOL)
            self.expect_type(l, BOOL, e.left.span)
            r = self.expr(e.right, BOOL)
            self.expect_type(r, BOOL, e.right.span)
            return E("logic", BOOL, e.span, op=op, left=l, right=r)
        num_exp = exp if exp is not None and (is_numeric(exp) or exp == STR) else None
        if op in ("<<", ">>"):
            l = self.expr(e.left, num_exp)
            r = self.expr(e.right, None)
            self.check_arith(op, l.ty, r.ty, e.span)
            return E("binary", l.ty, e.span, op=op, left=l, right=r)
        l, r = self.operands(e.left, e.right, num_exp)
        if l.ty == STR and op == "+":
            self.expect_type(r, STR, e.right.span)
            return E("binary", STR, e.span, op="+", left=l, right=r)
        if op == "*" and (l.ty == STR or r.ty == STR):
            s, n = (l, r) if l.ty == STR else (r, l)
            if not is_int(n.ty):
                self.err(f"a string can only be repeated by an integer, found {n.ty}", e.span)
            return E("str_repeat", STR, e.span, s=s, n=n)
        if op == "+" and isinstance(l.ty, ListTy):
            self.expect_type(r, l.ty, e.right.span)
            return E("list_concat", l.ty, e.span, left=l, right=r)
        self.check_arith(op, l.ty, r.ty, e.span)
        return E("binary", l.ty, e.span, op=op, left=l, right=r)

    def ordered(self, t):
        return ordered(t)

    def comparable(self, t):
        return comparable(t)

    def ex_Compare(self, e, exp):
        operands = []
        prev = None
        for i, op in enumerate(e.ops):
            la, ra = e.operands[i], e.operands[i + 1]
            if op in ("in", "not in"):
                cont = self.expr(ra, None)
                if cont.ty == STR:
                    item = self.expr(la, STR) if prev is None else prev
                    if item.ty not in (STR, CHAR):
                        self.err(f"`in` on a string needs a str or char, found {item.ty}", la.span)
                elif isinstance(cont.ty, MapTy):
                    item = self.expr(la, cont.ty.k) if prev is None else prev
                    self.expect_type(item, cont.ty.k, la.span)
                elif isinstance(cont.ty, (ListTy, ArrayTy)):
                    item = self.expr(la, cont.ty.elem) if prev is None else prev
                    self.expect_type(item, cont.ty.elem, la.span)
                    if not self.comparable(item.ty):
                        self.err(f"values of type {item.ty} cannot be compared", la.span)
                else:
                    self.err(f"`in` needs a list, array, map or str on the right, found {cont.ty}", ra.span)
                if prev is None:
                    operands.append(item)
                operands.append(cont)
                prev = cont
                continue
            if prev is None:
                l, r = self.operands(la, ra, None)
                operands.append(l)
            else:
                l = prev
                r = self.expr(ra, l.ty)
            if r.ty != l.ty:
                self.err(f"cannot compare {l.ty} with {r.ty}", e.span,
                         hint="convert one side with `as`" if is_numeric(l.ty) and is_numeric(r.ty) else None)
            if op in ("==", "!="):
                if not self.comparable(l.ty):
                    self.err(f"values of type {l.ty} cannot be compared", e.span)
            elif not self.ordered(l.ty):
                self.err(f"values of type {l.ty} have no ordering for '{op}'", e.span)
            operands.append(r)
            prev = r
        return E("compare", BOOL, e.span, ops=list(e.ops), operands=operands)

    def ex_Ternary(self, e, exp):
        cond = self.cond(e.cond)
        rs = [self.branch(lambda: self.value(e.then, exp))]
        then = rs[0][0]
        rs.append(self.branch(lambda: self.value(e.other, exp if exp is not None or then.ty == NEVER else then.ty)))
        other = rs[1][0]
        self.merge(rs, exhaustive=True)
        if then.ty == NEVER:
            ty = other.ty
        else:
            ty = then.ty
            self.expect_type(other, ty, e.other.span)
        return E("ternary", ty, e.span, cond=cond, then=then, other=other)

    def ex_Cast(self, e, exp):
        to = self.ty(e.type)
        v = self.expr(e.expr, to if self.is_untyped_lit(e.expr) and is_numeric(to) else None)
        f = v.ty
        ok = f == to or (is_numeric(f) and is_numeric(to)) or (f == CHAR and is_int(to)) \
            or (is_int(f) and to == CHAR) or (f == BOOL and is_int(to))
        if not ok:
            hint = "use str(x) to convert to a string" if to == STR else (
                "use s.parse_int() / s.parse_float()" if f == STR else None)
            self.err(f"cannot cast {f} to {to}", e.span, hint=hint)
        return E("cast", to, e.span, value=v)

    # ---- aggregates ----
    def ex_ListLit(self, e, exp):
        if isinstance(exp, ArrayTy):
            if len(e.elems) != exp.size:
                self.err(f"expected {exp.size} elements for {exp}, found {len(e.elems)}", e.span)
            elems = []
            for x in e.elems:
                v = self.value(x, exp.elem)
                self.expect_type(v, exp.elem, x.span)
                elems.append(v)
            return E("array", exp, e.span, elems=elems)
        et = exp.elem if isinstance(exp, ListTy) else None
        if not e.elems:
            if et is None:
                self.err("cannot infer the element type of an empty list", e.span,
                         hint="annotate it: `var xs: list[int] = []`")
            return E("list", ListTy(et), e.span, elems=[])
        elems = []
        for x in e.elems:
            v = self.value(x, et)
            if et is None:
                et = v.ty
            self.expect_type(v, et, x.span)
            elems.append(v)
        return E("list", ListTy(et), e.span, elems=elems)

    def ex_MapLit(self, e, exp):
        kt, vt = (exp.k, exp.v) if isinstance(exp, MapTy) else (None, None)
        if not e.pairs and kt is None:
            self.err("cannot infer the key and value types of an empty map", e.span,
                     hint="annotate it: `var m: map[str, int] = {}`")
        pairs = []
        for ka, va in e.pairs:
            k = self.value(ka, kt)
            if kt is None:
                kt = k.ty
                if not is_hashable(kt):
                    self.err(f"{kt} cannot be a map key", ka.span,
                             hint="map keys must be integers, char, bool, str or tuples of those")
            self.expect_type(k, kt, ka.span)
            v = self.value(va, vt)
            if vt is None:
                vt = v.ty
            self.expect_type(v, vt, va.span)
            pairs.append((k, v))
        return E("map", MapTy(kt, vt), e.span, pairs=pairs)

    def ex_ArrayRepeat(self, e, exp):
        et = exp.elem if isinstance(exp, (ListTy, ArrayTy)) else None
        v = self.value(e.elem, et)
        if et is not None:
            self.expect_type(v, et, e.elem.span)
        if isinstance(exp, ListTy) or not self.is_const_int(e.count):
            n = self.index_int(e.count)
            return E("list_repeat", ListTy(v.ty), e.span, value=v, count=n)
        if not is_copy(v.ty):
            self.err(f"array elements must be Copy, but {v.ty} is not", e.elem.span,
                     hint="use a list instead: `var xs: list[T] = [x; n]`")
        size = self.prog.const_int(e.count, self.mod)
        if size <= 0:
            self.err("array size must be positive", e.count.span)
        return E("array_repeat", ArrayTy(v.ty, size), e.span, value=v)

    def is_const_int(self, e):
        if isinstance(e, A.IntLit):
            return True
        if isinstance(e, A.Name) and self.lookup_var(e.name) is None:
            ent = self.mod.scope.get(e.name)
            return ent is not None and ent[0] == "const"
        return False

    def ex_TupleLit(self, e, exp):
        if not e.elems:
            return E("unit", VOID, e.span)
        exps = exp.elems if isinstance(exp, TupleTy) and len(exp.elems) == len(e.elems) else [None] * len(e.elems)
        elems = [self.value(x, t) for x, t in zip(e.elems, exps)]
        for v, x in zip(elems, e.elems):
            if v.ty in (VOID, NEVER):
                self.err("tuple elements must have a value", x.span)
        return E("tuple", TupleTy([v.ty for v in elems]), e.span, elems=elems)

    # ---- ? operator ----
    def prelude_decl(self, name):
        return self.prog.prelude.scope[name][1]

    def ex_Try(self, e, exp):
        inner = self.expr(e.expr, None)
        t = inner.ty
        ret = self.inst.ret
        opt, res = self.prelude_decl("Option"), self.prelude_decl("Result")
        if not isinstance(t, NamedTy) or t.decl not in (opt, res):
            self.err(f"`?` needs an Option or Result, found {t}", e.span)
        if t.decl is opt:
            if not (isinstance(ret, NamedTy) and ret.decl is opt):
                self.err("`?` on an Option can only be used in a function that returns an Option", e.span)
        else:
            if not (isinstance(ret, NamedTy) and ret.decl is res):
                self.err("`?` on a Result can only be used in a function that returns a Result", e.span)
            if ret.args[1] != t.args[1]:
                self.err(f"`?` would return Err({t.args[1]}) but the function returns {ret}", e.span)
        inner = self.consume(inner, e.span)
        return E("try", t.args[0], e.span, value=inner, src_ty=t, ret=ret, is_option=t.decl is opt)

    # ---- calls ----
    def ex_Call(self, e, exp):
        f = e.func
        if isinstance(f, A.Name):
            if self.lookup_var(f.name) is not None:
                return self.call_value(e, exp)
            if f.name not in self.mod.scope:
                if self.is_builtin(f.name):
                    return self.builtin_call(f.name, e, exp)
                if self.type_entry(f.name) is None:
                    self.unknown_name(f.name, f.span)
        elif isinstance(f, A.Field) and self.static(f) is None:
            return self.method_call(f, e, exp)
        st = self.static(f)
        if st is None:
            return self.call_value(e, exp)
        kind, payload, mod = st[:3]
        targs = st[3] if len(st) > 3 else None
        if kind == "fn":
            return self.call_decl(payload, None, None, targs, None, e.args, exp, e.span)
        if kind == "method":
            owner, md = payload
            if md.self_mode is not None or self.has_deco(md, "consuming"):
                self.err(f"'{md.name}' takes self; call it on a value: x.{md.name}(...)", e.span)
            return self.call_decl(md, owner, targs, None, None, e.args, exp, e.span)
        if kind == "trait_method":
            return self.trait_call(*payload, e, exp)
        if kind == "struct":
            return self.construct(payload, targs, e.args, exp, e.span)
        if kind == "variant":
            decl, i = payload
            return self.make_variant(decl, i, targs, e.args, exp, e.span)
        self.err(f"'{getattr(payload, 'name', '?')}' is not callable", e.span)

    @staticmethod
    def has_deco(decl, name):
        return any(d[0] == name for d in decl.decorators)

    def call_value(self, e, exp):
        fn = self.expr(e.func, None)
        if not isinstance(fn.ty, FnTy):
            self.err(f"a value of type {fn.ty} cannot be called", e.span)
        if len(e.args) != len(fn.ty.params) or any(a.name for a in e.args):
            self.err(f"expected {len(fn.ty.params)} positional argument(s), found {len(e.args)}", e.span)
        args = []
        for a, pt in zip(e.args, fn.ty.params):
            v = self.value(a.value, pt)
            self.expect_type(v, pt, a.span)
            args.append(v)
        return E("call_ind", fn.ty.ret, e.span, fn=fn, args=args)

    def method_call(self, f, e, exp):
        recv = self.expr(f.base, None)
        t = recv.ty
        if isinstance(t, NamedTy) and f.name in t.info.methods:
            md = t.info.methods[f.name]
            return self.call_decl(md, t.decl, list(t.args), None, recv, e.args, exp, e.span)
        via_impl = self.impl_method_call(recv, f.name, e, exp)
        if via_impl is not None:
            return via_impl
        return self.builtin_method(recv, f.name, e, exp)

    def bind_args(self, params, args, span, what):
        """Match positional/keyword args to params. Returns a list of arg ASTs in param order."""
        out = [None] * len(params)
        names = [n for n, _ in params]
        pos = 0
        seen_kw = False
        for a in args:
            if a.name is None:
                if seen_kw:
                    self.err("positional arguments must come before keyword arguments", a.span)
                if pos >= len(params):
                    self.err(f"{what} takes {len(params)} argument(s) but {len(args)} were given", a.span)
                out[pos] = a
                pos += 1
            else:
                seen_kw = True
                if a.name not in names:
                    close = difflib.get_close_matches(a.name, [n for n in names if n], n=1)
                    self.err(f"{what} has no parameter named '{a.name}'", a.span,
                             hint=f"did you mean '{close[0]}'?" if close else None)
                i = names.index(a.name)
                if out[i] is not None:
                    self.err(f"argument '{a.name}' given twice", a.span)
                out[i] = a
        missing = [n or f"#{i}" for i, ((n, _), a) in enumerate(zip(params, out)) if a is None]
        if missing:
            self.err(f"{what} is missing argument(s): {', '.join(missing)}", span)
        return out

    def check_args(self, params, arg_asts, binds, recv=None, recv_ty=None):
        """Check arguments against (possibly generic) parameter types, inferring TParams into binds.
        Returns (arg IRs in parameter order, list of (place, mut) references)."""
        before = set(self.moved)
        refs = []
        if recv is not None:
            if isinstance(recv_ty, RefTy):
                if recv_ty.mut:
                    if not is_place(recv) or root_var(recv) is None:
                        self.err("cannot call a `mut self` method on a temporary value", recv.span)
                    self.mutate(recv, recv.span)
                    refs.append((recv, True))
                elif is_place(recv):
                    refs.append((recv, False))
            else:
                recv = self.consume(recv, recv.span)
        order = sorted(range(len(params)), key=lambda i: (isinstance(arg_asts[i].value, A.Lambda),)
                       + ((arg_asts[i].span.line, arg_asts[i].span.col) if arg_asts[i].span else (0, i)))
        out = [None] * len(params)
        for i in order:
            (pname, pt), a = params[i], arg_asts[i]
            av = a.value
            if isinstance(pt, RefTy):
                inner = pt.inner
                exp = self.concrete(inner, binds)
                if isinstance(av, A.Ref):
                    if pt.mut and not av.mut:
                        self.err(f"parameter '{pname}' is `&mut`; pass `&mut ...`", a.span)
                    place = self.expr(av.expr, exp)
                    mut = av.mut and pt.mut
                else:
                    if pt.mut:
                        self.err(f"parameter '{pname}' is `&mut`; pass `&mut {self.describe_ast(av)}`", a.span,
                                 hint="mutable borrows are always written explicitly at the call site")
                    place = self.expr(av, exp)
                    mut = False
                self.unify_arg(inner, place, binds, a.span)
                if mut:
                    if not is_place(place) or root_var(place) is None:
                        self.err("`&mut` needs a variable, field or element", a.span)
                    self.mutate(place, a.span)
                if is_place(place):
                    refs.append((place, mut))
                    out[i] = E("ref", RefTy(mut, place.ty), a.span, place=place)
                else:
                    out[i] = E("ref_tmp", RefTy(False, place.ty), a.span, value=place)
            else:
                exp = self.concrete(pt, binds)
                if exp is None and isinstance(av, A.Lambda):
                    exp = self.prog.subst(pt, binds) if binds else pt   # lambdas infer what is known so far
                views = None
                if getattr(self, "call_views", False) and isinstance(pt, FnTy):
                    views = [isinstance(p, TParam) and p.name == "T" for p in pt.params]
                if views and isinstance(av, A.Lambda):
                    self.lambda_views = views
                v = self.value(av, exp)
                self.unify_arg(pt, v, binds, a.span)
                if views and v.kind != "lambda" and isinstance(v.ty, FnTy):
                    for p, view in zip(v.ty.params, views):
                        if view and not is_copy(p):
                            self.err(f"this function would take each {p} by value, but the list only lends them",
                                     a.span, hint="pass a lambda, e.g. `fn(x) => f(x.clone())`")
                out[i] = v
        self.check_alias(refs, set(self.moved) - before)
        return recv, out

    def describe_ast(self, e):
        if isinstance(e, A.Name):
            return e.name
        if isinstance(e, A.Field):
            return self.describe_ast(e.base) + "." + e.name
        return "x"

    def concrete(self, t, binds):
        if t is None:
            return None
        if not contains_tparam(t):
            return t
        if not binds:
            return None
        s = self.prog.subst(t, binds)
        return None if contains_tparam(s) else s

    def unify_arg(self, pt, v, binds, span):
        if v.ty == NEVER:
            return
        if not contains_tparam(pt):
            self.expect_type(v, pt, span)
            return
        if not unify(pt, v.ty, binds):
            shown = self.prog.subst(pt, binds) if binds else pt
            self.err(f"expected {shown}, found {v.ty}", span)

    def check_alias(self, refs, moved_now):
        for place, _ in refs:
            r = root_var(place)
            if r is not None and r.id in moved_now:
                self.err(f"'{r.name}' is moved by one argument and borrowed by another in the same call",
                         place.span, hint="clone it, or split the call into two statements")
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                (a, am), (b, bm) = refs[i], refs[j]
                if not (am or bm):
                    continue
                ra, rb = root_var(a), root_var(b)
                if ra is None or ra is not rb:
                    continue
                pa, pb = place_path(a), place_path(b)
                if pa is not None and pb is not None and pa[:len(pb)] != pb and pb[:len(pa)] != pa:
                    continue  # disjoint fields of the same struct
                self.err(f"'{ra.name}' is passed as `&mut` while it is also borrowed in the same call",
                         (b if bm else a).span,
                         hint="a mutable reference must be the only way to reach its value during the call")

    def generic_env(self, tparams, given, what, span):
        if given is not None:
            if len(given) != len(tparams):
                self.err(f"{what} expects {len(tparams)} type argument(s), got {len(given)}", span)
            return dict(zip(tparams, given)), []
        tps = [self.prog.fresh_tparam(n) for n in tparams]
        return dict(zip(tparams, tps)), tps

    def solve(self, tps, binds, what, span):
        out = []
        for tp in tps:
            if tp not in binds:
                self.err(f"cannot infer type parameter '{tp.name}' of {what}", span,
                         hint="give it explicitly, e.g. name[int](...), or annotate the variable")
            out.append(binds[tp])
        return out

    def seed(self, ret, exp, binds):
        if exp is not None and contains_tparam(ret):
            trial = {}
            if unify(ret, exp, trial):
                binds.update(trial)

    def call_decl(self, decl, owner_decl, owner_args, targs, recv, args, exp, span):
        mod = self.prog.decl_mod.get(id(decl)) or self.prog.decl_module(owner_decl or decl)
        env = {}
        tps = []
        prim_owner = isinstance(owner_decl, PrimDecl)
        if owner_decl is not None:
            oenv, otps = self.generic_env(owner_decl.tparams, owner_args, f"type '{owner_decl.name}'", span)
            env.update(oenv)
            tps += otps
            env["Self"] = Prim(owner_decl.name) if prim_owner else self.prog.named_ty(
                owner_decl, [oenv[tp] for tp in owner_decl.tparams], self.prog.decl_module(owner_decl), span)
        menv, mtps = self.generic_env(decl.tparams, targs if owner_decl is None else None,
                                      f"function '{decl.name}'", span)
        env.update(menv)
        tps += mtps
        params = [(p.name, self.prog.resolve_type(p.type, env, mod, allow_ref=True)) for p in decl.params]
        ret = self.prog.resolve_type(decl.ret, env, mod) if decl.ret else VOID
        binds = {}
        self.seed(ret, exp, binds)
        what = f"'{decl.name}'"
        asts = self.bind_args(params, args, span, what)
        recv_ty = None
        if recv is not None:
            if decl.self_mode is None and not self.has_deco(decl, "consuming"):
                self.err(f"'{decl.name}' is a static method; call it as {owner_decl.name}.{decl.name}(...)", span)
            recv_ty = None if self.has_deco(decl, "consuming") else RefTy(decl.self_mode == "mut", recv.ty)
        saved, self.call_views = getattr(self, "call_views", False), self.has_deco(decl, "views")
        try:
            recv, irs = self.check_args(params, asts, binds, recv, recv_ty)
        finally:
            self.call_views = saved
        solved = self.solve(tps, binds, what, span)
        n_owner = len(owner_decl.tparams) if owner_decl is not None and owner_args is None else 0
        owner = None
        if prim_owner:
            owner = self.prog.prim_info(Prim(owner_decl.name))
        elif owner_decl is not None:
            oargs = owner_args if owner_args is not None else solved[:n_owner]
            owner = self.prog.named_ty(owner_decl, oargs, mod, span).info
        margs = solved[n_owner:] if owner_decl is not None else (targs if targs is not None else solved)
        self.prog.check_bounds(decl, margs, mod, span, f"'{decl.name}'")
        inst = self.prog.fn_inst(decl, owner, margs, mod, span)
        for (pn, pt), v in zip(inst.params, irs):
            want = pt.inner if isinstance(pt, RefTy) else pt
            if v.ty != NEVER and (v.ty.inner if isinstance(v.ty, RefTy) else v.ty) != want:
                self.err(f"argument '{pn}' has type {v.ty}, expected {want}", v.span)
        all_args = ([recv] if recv is not None else []) + irs
        return E("call", inst.ret, span, inst=inst, args=all_args)

    def construct(self, decl, targs, args, exp, span):
        mod = self.prog.decl_module(decl)
        env, tps = self.generic_env(decl.tparams, targs, f"type '{decl.name}'", span)
        params = [(fname, self.prog.resolve_type(ft, env, mod)) for fname, ft, _ in decl.fields]
        binds = {}
        if exp is not None and isinstance(exp, NamedTy) and exp.decl is decl:
            binds.update({tp: a for tp, a in zip(tps, exp.args)})
        asts = self.bind_args(params, args, span, f"'{decl.name}'")
        _, irs = self.check_args(params, asts, binds)
        ty = self.prog.named_ty(decl, targs if targs is not None else self.solve(tps, binds, f"'{decl.name}'", span),
                                mod, span)
        for (fname, ft), v in zip(ty.info.fields, irs):
            self.expect_type(v, ft, v.span)
        return E("struct", ty, span, info=ty.info, fields=irs)

    def make_variant(self, decl, i, targs, args, exp, span):
        mod = self.prog.decl_module(decl)
        v = decl.variants[i]
        env, tps = self.generic_env(decl.tparams, targs, f"type '{decl.name}'", span)
        params = [(fname, self.prog.resolve_type(ft, env, mod)) for fname, ft in v.fields]
        binds = {}
        if exp is not None and isinstance(exp, NamedTy) and exp.decl is decl:
            binds.update({tp: a for tp, a in zip(tps, exp.args)})
        if not v.fields and args:
            self.err(f"variant '{v.name}' takes no arguments", span)
        asts = self.bind_args(params, args, span, f"variant '{v.name}'")
        _, irs = self.check_args(params, asts, binds)
        if targs is None and tps and any(tp not in binds for tp in tps):
            self.err(f"cannot infer the type of '{v.name}'", span,
                     hint=f"annotate the variable, e.g. `let x: {decl.name}[int] = {v.name}`")
        ty = self.prog.named_ty(decl, targs if targs is not None else self.solve(tps, binds, v.name, span), mod, span)
        for (_, ft), a in zip(ty.info.variants[i][1], irs):
            self.expect_type(a, ft, a.span)
        return E("variant", ty, span, info=ty.info, vidx=i, args=irs)
