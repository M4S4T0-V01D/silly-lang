"""Built-in functions and methods on primitive types, str and list.

Every builtin lowers to E("bi", ty, name=..., args=[...]); codegen dispatches on
the name. Methods use "<type>.<method>" names with the receiver as args[0].
"""

import difflib

from . import ast as A
from .ir import E, is_place
from .types import (BOOL, CHAR, F64, I64, NEVER, STR, U8, VOID, ArrayTy, FnTy, ListTy, MapTy, TupleTy, NamedTy, Prim,
                    TupleTy, TaskTy, has_task, is_copy, is_float, is_int, is_numeric, is_signed)

FREE = {"print", "eprint", "len", "str", "abs", "min", "max", "sum", "panic", "exit", "input", "read_file",
        "write_file", "args", "clock", "take", "swap", "ord", "chr", "range", "enumerate",
        "spawn", "join_all", "cpu_count"}

LIST_METHODS = ["push", "pop", "insert", "remove", "swap", "reverse", "clear", "sort", "extend", "truncate",
                "len", "is_empty", "contains", "index_of", "clone", "get", "last", "first",
                "map", "filter", "any", "all", "count_by", "position", "each", "fold", "sort_by"]
CLOSURE_METHODS = {"map", "filter", "any", "all", "count_by", "position", "each", "fold", "sort_by"}
MAP_METHODS = ["get", "get_or", "contains", "insert", "remove", "clear", "len", "is_empty", "keys", "values",
               "items", "clone"]
STR_METHODS = ["len", "is_empty", "contains", "starts_with", "ends_with", "find", "split", "trim", "trim_start",
               "trim_end", "upper", "lower", "replace", "join", "chars", "bytes", "parse_int", "parse_float",
               "lines", "count", "clone"]
CHAR_METHODS = ["is_digit", "is_alpha", "is_alnum", "is_space", "is_upper", "is_lower", "upper", "lower"]
FLOAT_METHODS = ["sqrt", "floor", "ceil", "abs", "round", "trunc", "is_nan", "clone"]
INT_METHODS = ["abs", "clone", "min", "max"]


class BuiltinMixin:
    def is_builtin(self, name):
        return name in FREE

    # ---- helpers ----
    def bi(self, name, ty, span, args, **kw):
        return E("bi", ty, span, name=name, args=args, **kw)

    def positional(self, e, lo, hi=None, what=None):
        hi = lo if hi is None else hi
        what = what or "this function"
        for a in e.args:
            if a.name is not None:
                self.err(f"{what} takes no keyword argument '{a.name}'", a.span)
        n = len(e.args)
        if not lo <= n <= hi:
            want = str(lo) if lo == hi else f"{lo} to {hi}"
            self.err(f"{what} takes {want} argument(s), found {n}", e.span)
        return [a.value for a in e.args]

    def typed(self, ast, ty, consume=False):
        v = self.value(ast, ty) if consume else self.expr(ast, ty)
        self.expect_type(v, ty, ast.span)
        return v

    def option_of(self, t, span):
        decl = self.prelude_decl("Option")
        return self.prog.named_ty(decl, [t], self.prog.prelude, span)

    def result_of(self, t, e, span):
        decl = self.prelude_decl("Result")
        return self.prog.named_ty(decl, [t, e], self.prog.prelude, span)

    def printable(self, t, span):
        if t in (VOID, NEVER):
            self.err("this expression has no value to print", span)
        if has_task(t):
            self.err(f"{t} cannot be printed: it holds a Task", span, hint="join the task and print its result")

    def ref_place(self, ast, what):
        """`&mut place` argument of take/swap."""
        if not isinstance(ast, A.Ref) or not ast.mut:
            self.err(f"{what} needs `&mut` arguments", ast.span, hint=f"{what}(&mut x, ...)")
        p = self.expr(ast.expr, None)
        if not is_place(p):
            self.err("`&mut` needs a variable, field or element", ast.span)
        self.mutate(p, ast.span)
        return p

    # ---- free functions ----
    def builtin_call(self, name, e, exp):
        sp = e.span
        if name in ("print", "eprint"):
            sep = end = None
            vals = []
            for a in e.args:
                if a.name == "sep":
                    sep = self.typed(a.value, STR)
                elif a.name == "end":
                    end = self.typed(a.value, STR)
                elif a.name is not None:
                    self.err(f"{name}() has no parameter '{a.name}'", a.span, hint="use sep= or end=")
                else:
                    v = self.expr(a.value, None)
                    self.printable(v.ty, a.span)
                    vals.append(v)
            return self.bi(name, VOID, sp, vals, sep=sep, end=end)
        if name == "len":
            (x,) = self.positional(e, 1, what="len()")
            v = self.expr(x, None)
            if isinstance(v.ty, MapTy):
                return self.bi("map.len", I64, sp, [v])
            if not (v.ty == STR or isinstance(v.ty, (ListTy, ArrayTy))):
                self.err(f"len() needs a str, list, array or map, found {v.ty}", x.span)
            return self.bi("len", I64, sp, [v])
        if name == "str":
            (x,) = self.positional(e, 1, what="str()")
            v = self.expr(x, None)
            self.printable(v.ty, x.span)
            return self.bi("str", STR, sp, [v])
        if name == "abs":
            (x,) = self.positional(e, 1, what="abs()")
            v = self.expr(x, exp if exp is not None and is_numeric(exp) else None)
            if not (is_float(v.ty) or (is_int(v.ty) and is_signed(v.ty))):
                self.err(f"abs() needs a signed number, found {v.ty}", x.span)
            return self.bi("abs", v.ty, sp, [v])
        if name in ("min", "max"):
            xs = self.positional(e, 1, 16, what=f"{name}()")
            if len(xs) == 1:
                v = self.expr(xs[0], None)
                if not isinstance(v.ty, (ListTy, ArrayTy)) or not (is_numeric(v.ty.elem) or v.ty.elem == CHAR):
                    self.err(f"{name}() of one argument needs a list of numbers, found {v.ty}", xs[0].span)
                return self.bi(name + "_list", v.ty.elem, sp, [v])
            first = next((x for x in xs if not self.is_untyped_lit(x)), xs[0])
            v0 = self.expr(first, exp if exp is not None and is_numeric(exp) else None)
            vals = [v0 if x is first else self.typed(x, v0.ty) for x in xs]
            if not (is_numeric(v0.ty) or v0.ty in (CHAR, STR)):
                self.err(f"{name}() needs numbers, chars or strings, found {v0.ty}", first.span)
            return self.bi(name, v0.ty, sp, vals)
        if name == "sum":
            (x,) = self.positional(e, 1, what="sum()")
            v = self.expr(x, None)
            if not isinstance(v.ty, (ListTy, ArrayTy)) or not is_numeric(v.ty.elem):
                self.err(f"sum() needs a list of numbers, found {v.ty}", x.span)
            return self.bi("sum", v.ty.elem, sp, [v])
        if name == "panic":
            xs = self.positional(e, 0, 1, what="panic()")
            args = [self.typed(xs[0], STR)] if xs else []
            self.diverges = True
            return self.bi("panic", NEVER, sp, args)
        if name == "exit":
            (x,) = self.positional(e, 1, what="exit()")
            self.diverges = True
            return self.bi("exit", NEVER, sp, [self.typed(x, I64)])
        if name == "input":
            xs = self.positional(e, 0, 1, what="input()")
            return self.bi("input", self.option_of(STR, sp), sp, [self.typed(xs[0], STR)] if xs else [])
        if name == "read_file":
            (x,) = self.positional(e, 1, what="read_file()")
            return self.bi("read_file", self.result_of(STR, STR, sp), sp, [self.typed(x, STR)])
        if name == "write_file":
            xs = self.positional(e, 2, what="write_file()")
            return self.bi("write_file", BOOL, sp, [self.typed(x, STR) for x in xs])
        if name == "args":
            self.positional(e, 0, what="args()")
            return self.bi("args", ListTy(STR), sp, [])
        if name == "clock":
            self.positional(e, 0, what="clock()")
            return self.bi("clock", F64, sp, [])
        if name == "ord":
            (x,) = self.positional(e, 1, what="ord()")
            return E("cast", I64, sp, value=self.typed(x, CHAR))
        if name == "chr":
            (x,) = self.positional(e, 1, what="chr()")
            v = self.expr(x, I64)
            if not is_int(v.ty):
                self.err(f"chr() needs an integer, found {v.ty}", x.span)
            return E("cast", CHAR, sp, value=v)
        if name == "take":
            (x,) = self.positional(e, 1, what="take()")
            p = self.ref_place(x, "take")
            return self.bi("take", p.ty, sp, [p])
        if name == "swap":
            a, b = self.positional(e, 2, what="swap()")
            pa = self.ref_place(a, "swap")
            pb = self.ref_place(b, "swap")
            if pa.ty != pb.ty:
                self.err(f"swap() needs two places of the same type, found {pa.ty} and {pb.ty}", sp)
            self.check_alias([(pa, True), (pb, True)], set())
            return self.bi("swap", VOID, sp, [pa, pb])
        if name == "spawn":
            (x,) = self.positional(e, 1, what="spawn()")
            f = self.value(x, None)
            if not isinstance(f.ty, FnTy) or f.ty.params:
                self.err(f"spawn() needs a function that takes no arguments, found {f.ty}", x.span,
                         hint="spawn(fn() => work(a, b))")
            if f.ty.ret == NEVER:
                self.err("the spawned function never returns a value", x.span)
            return self.bi("spawn", TaskTy(f.ty.ret), sp, [f])
        if name == "join_all":
            (x,) = self.positional(e, 1, what="join_all()")
            v = self.value(x, None)
            if not (isinstance(v.ty, ListTy) and isinstance(v.ty.elem, TaskTy)):
                self.err(f"join_all() needs a list[Task[T]], found {v.ty}", x.span)
            r = v.ty.elem.ret
            return self.bi("join_all", VOID if r == VOID else ListTy(r), sp, [v])
        if name == "cpu_count":
            self.positional(e, 0, what="cpu_count()")
            return self.bi("cpu_count", I64, sp, [])
        if name in ("range", "enumerate"):
            self.err(f"{name}() can only be used as the iterable of a `for` loop", sp)
        self.err(f"unknown builtin '{name}'", sp)

    # ---- methods ----
    def builtin_method(self, recv, name, e, exp):
        t = recv.ty
        sp = e.span
        if isinstance(t, MapTy):
            return self.map_method(recv, name, e, exp)
        if isinstance(t, TaskTy):
            return self.task_method(recv, name, e, exp)
        if name == "clone" and has_task(t):
            self.err(f"{t} cannot be cloned: it holds a Task", sp, hint="a task can only be joined once")
        if name == "clone" and not isinstance(t, (ListTy,)):
            self.positional(e, 0, what="clone()")
            if t in (VOID, NEVER):
                self.err("cannot clone a value of type ()", sp)
            return self.bi("clone", t, sp, [recv])
        if isinstance(t, ListTy):
            return self.list_method(recv, name, e, exp)
        if isinstance(t, ArrayTy):
            return self.array_method(recv, name, e, exp)
        if t == STR:
            return self.str_method(recv, name, e, exp)
        if t == CHAR:
            if name not in CHAR_METHODS:
                self.no_method(t, name, CHAR_METHODS, sp)
            self.positional(e, 0, what=f"char.{name}()")
            return self.bi("char." + name, CHAR if name in ("upper", "lower") else BOOL, sp, [recv])
        if is_float(t):
            if name not in FLOAT_METHODS:
                self.no_method(t, name, FLOAT_METHODS, sp)
            self.positional(e, 0, what=f"{t}.{name}()")
            return self.bi("float." + name, BOOL if name == "is_nan" else t, sp, [recv])
        if is_int(t):
            if name == "abs":
                self.positional(e, 0, what="abs()")
                if not is_signed(t):
                    self.err(f"abs() is not defined for unsigned {t}", sp)
                return self.bi("abs", t, sp, [recv])
            if name in ("min", "max"):
                (x,) = self.positional(e, 1, what=f"{name}()")
                return self.bi(name, t, sp, [recv, self.typed(x, t)])
            self.no_method(t, name, INT_METHODS, sp)
        if isinstance(t, NamedTy):
            self.no_method(t, name, list(t.info.methods) + ["clone"], sp)
        self.err(f"{t} has no method '{name}'", sp)

    def task_method(self, recv, name, e, exp):
        t = recv.ty
        sp = e.span
        if name == "join":
            self.positional(e, 0, what="join()")
            return self.bi("task.join", t.ret, sp, [self.consume(recv, recv.span)])
        if name == "done":
            self.positional(e, 0, what="done()")
            return self.bi("task.done", BOOL, sp, [recv])
        self.no_method(t, name, ["join", "done"], sp)

    def no_method(self, t, name, known, span):
        close = difflib.get_close_matches(name, known, n=1)
        self.err(f"{t} has no method '{name}'", span, hint=f"did you mean '{close[0]}'?" if close else None)

    def mut_recv(self, recv, name, what="list"):
        if not is_place(recv):
            self.err(f"cannot call '{name}' on a temporary {what}", recv.span,
                     hint="store it in a `var` first")
        self.mutate(recv, recv.span)

    def list_method(self, recv, name, e, exp):
        t = recv.ty
        el = t.elem
        sp = e.span
        w = f"list.{name}()"
        if name in CLOSURE_METHODS:
            if name == "sort_by" and not is_place(recv):
                self.mut_recv(recv, name)
            decl = self.prelude_decl("__list_" + name)
            this = A.Arg(None, A.Ref(name == "sort_by", A.Checked(recv, span=recv.span), span=recv.span), span=recv.span)
            return self.call_decl(decl, None, None, None, None, [this] + list(e.args), exp, sp)
        if name == "push":
            (x,) = self.positional(e, 1, what=w)
            v = self.typed(x, el, consume=True)
            self.mut_recv(recv, name)
            return self.bi("list.push", VOID, sp, [recv, v])
        if name == "pop":
            self.positional(e, 0, what=w)
            self.mut_recv(recv, name)
            return self.bi("list.pop", el, sp, [recv])
        if name == "insert":
            i, x = self.positional(e, 2, what=w)
            iv = self.index_int(i)
            v = self.typed(x, el, consume=True)
            self.mut_recv(recv, name)
            return self.bi("list.insert", VOID, sp, [recv, iv, v])
        if name == "remove":
            (i,) = self.positional(e, 1, what=w)
            iv = self.index_int(i)
            self.mut_recv(recv, name)
            return self.bi("list.remove", el, sp, [recv, iv])
        if name == "swap":
            i, j = self.positional(e, 2, what=w)
            a, b = self.index_int(i), self.index_int(j)
            self.mut_recv(recv, name)
            return self.bi("list.swap", VOID, sp, [recv, a, b])
        if name == "truncate":
            (n,) = self.positional(e, 1, what=w)
            nv = self.index_int(n)
            self.mut_recv(recv, name)
            return self.bi("list.truncate", VOID, sp, [recv, nv])
        if name in ("reverse", "clear"):
            self.positional(e, 0, what=w)
            self.mut_recv(recv, name)
            return self.bi("list." + name, VOID, sp, [recv])
        if name == "sort":
            self.positional(e, 0, what=w)
            if not self.ordered(el):
                self.err(f"cannot sort a list of {el}: it has no ordering", sp)
            self.mut_recv(recv, name)
            return self.bi("list.sort", VOID, sp, [recv])
        if name == "extend":
            (x,) = self.positional(e, 1, what=w)
            v = self.typed(x, t, consume=True)
            self.mut_recv(recv, name)
            return self.bi("list.extend", VOID, sp, [recv, v])
        if name in ("len", "is_empty"):
            self.positional(e, 0, what=w)
            return self.bi("len" if name == "len" else "is_empty", I64 if name == "len" else BOOL, sp, [recv])
        if name in ("contains", "index_of"):
            (x,) = self.positional(e, 1, what=w)
            v = self.typed(x, el)
            if not self.comparable(el):
                self.err(f"values of type {el} cannot be compared", sp)
            if name == "contains":
                return self.bi("contains", BOOL, sp, [recv, v])
            return self.bi("index_of", self.option_of(I64, sp), sp, [recv, v])
        if name == "clone":
            self.positional(e, 0, what=w)
            return self.bi("clone", t, sp, [recv])
        if name in ("get", "last", "first"):
            args = [self.index_int(self.positional(e, 1, what=w)[0])] if name == "get" else \
                (self.positional(e, 0, what=w) and [])
            if not is_copy(el):
                self.err(f"list.{name}() copies the element, but {el} is not Copy", sp,
                         hint="index the list directly (xs[i]) and borrow or clone the element")
            return self.bi("list." + name, self.option_of(el, sp), sp, [recv] + args)
        self.no_method(t, name, LIST_METHODS, sp)

    def map_method(self, recv, name, e, exp):
        t = recv.ty
        sp = e.span
        w = f"map.{name}()"
        if name in ("get", "get_or"):
            args = self.positional(e, 1 if name == "get" else 2, what=w)
            k = self.typed(args[0], t.k)
            if not is_copy(t.v):
                self.err(f"map.{name}() copies the value, but {t.v} is not Copy", sp,
                         hint="index the map directly (m[k]) and borrow or clone the value")
            if name == "get":
                return self.bi("map.get", self.option_of(t.v, sp), sp, [recv, k])
            return self.bi("map.get_or", t.v, sp, [recv, k, self.typed(args[1], t.v)])
        if name == "contains":
            (x,) = self.positional(e, 1, what=w)
            return self.bi("map.contains", BOOL, sp, [recv, self.typed(x, t.k)])
        if name == "insert":
            k, v = self.positional(e, 2, what=w)
            kv, vv = self.typed(k, t.k), self.typed(v, t.v, consume=True)
            self.mut_recv(recv, name, "map")
            return self.bi("map.insert", self.option_of(t.v, sp), sp, [recv, kv, vv])
        if name == "remove":
            (x,) = self.positional(e, 1, what=w)
            k = self.typed(x, t.k)
            self.mut_recv(recv, name, "map")
            return self.bi("map.remove", self.option_of(t.v, sp), sp, [recv, k])
        if name == "clear":
            self.positional(e, 0, what=w)
            self.mut_recv(recv, name, "map")
            return self.bi("map.clear", VOID, sp, [recv])
        if name in ("len", "is_empty"):
            self.positional(e, 0, what=w)
            return self.bi("map." + name, I64 if name == "len" else BOOL, sp, [recv])
        if name in ("keys", "values", "items"):
            self.positional(e, 0, what=w)
            if name != "keys" and not is_copy(t.v):
                self.err(f"map.{name}() copies the values, but {t.v} is not Copy", sp,
                         hint=f"iterate in place with `for k, v in m.items():`" if name == "items" else
                         "iterate the keys and index the map")
            et = {"keys": t.k, "values": t.v, "items": TupleTy([t.k, t.v])}[name]
            return self.bi("map." + name, ListTy(et), sp, [recv])
        if name == "clone":
            self.positional(e, 0, what=w)
            return self.bi("clone", t, sp, [recv])
        self.no_method(t, name, MAP_METHODS, sp)

    def array_method(self, recv, name, e, exp):
        t = recv.ty
        sp = e.span
        w = f"array.{name}()"
        if name == "len":
            self.positional(e, 0, what=w)
            return self.bi("len", I64, sp, [recv])
        if name in ("contains", "index_of"):
            (x,) = self.positional(e, 1, what=w)
            v = self.typed(x, t.elem)
            if name == "contains":
                return self.bi("contains", BOOL, sp, [recv, v])
            return self.bi("index_of", self.option_of(I64, sp), sp, [recv, v])
        if name in ("sort", "reverse"):
            self.positional(e, 0, what=w)
            if name == "sort" and not self.ordered(t.elem):
                self.err(f"cannot sort an array of {t.elem}", sp)
            self.mut_recv(recv, name)
            return self.bi("array." + name, VOID, sp, [recv])
        if name == "to_list":
            self.positional(e, 0, what=w)
            return E("slice", ListTy(t.elem), sp, base=recv, lo=None, hi=None)
        self.no_method(t, name, ["len", "contains", "index_of", "sort", "reverse", "to_list", "clone"], sp)

    def str_method(self, recv, name, e, exp):
        sp = e.span
        w = f"str.{name}()"
        if name in ("len", "is_empty"):
            self.positional(e, 0, what=w)
            return self.bi("len" if name == "len" else "is_empty", I64 if name == "len" else BOOL, sp, [recv])
        if name in ("contains", "starts_with", "ends_with", "find", "count"):
            (x,) = self.positional(e, 1, what=w)
            v = self.expr(x, STR)
            if v.ty == CHAR:
                v = self.bi("str", STR, x.span, [v])
            self.expect_type(v, STR, x.span)
            ty = {"find": self.option_of(I64, sp), "count": I64}.get(name, BOOL)
            return self.bi("str." + name if name != "contains" else "contains", ty, sp, [recv, v])
        if name == "split":
            xs = self.positional(e, 0, 1, what=w)
            return self.bi("str.split", ListTy(STR), sp, [recv] + [self.typed(x, STR) for x in xs])
        if name in ("trim", "trim_start", "trim_end", "upper", "lower", "clone"):
            self.positional(e, 0, what=w)
            return self.bi("str." + name, STR, sp, [recv])
        if name == "replace":
            a, b = self.positional(e, 2, what=w)
            return self.bi("str.replace", STR, sp, [recv, self.typed(a, STR), self.typed(b, STR)])
        if name == "join":
            (x,) = self.positional(e, 1, what=w)
            v = self.expr(x, ListTy(STR))
            if v.ty not in (ListTy(STR),) and not (isinstance(v.ty, ArrayTy) and v.ty.elem == STR):
                self.err(f"join() needs a list of str, found {v.ty}", x.span)
            return self.bi("str.join", STR, sp, [recv, v])
        if name in ("chars", "bytes", "lines"):
            self.positional(e, 0, what=w)
            ty = {"chars": ListTy(CHAR), "bytes": ListTy(U8), "lines": ListTy(STR)}[name]
            return self.bi("str." + name, ty, sp, [recv])
        if name == "parse_int":
            self.positional(e, 0, what=w)
            return self.bi("str.parse_int", self.option_of(I64, sp), sp, [recv])
        if name == "parse_float":
            self.positional(e, 0, what=w)
            return self.bi("str.parse_float", self.option_of(F64, sp), sp, [recv])
        self.no_method(STR, name, STR_METHODS, sp)
