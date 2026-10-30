"""Checks one function instance: types, moves, borrows, and data-stack regions.

Memory-safety rules enforced here (summarised in docs/memory-model.md):
  * references are second-class: they exist only as parameters, never stored,
    returned or bound to variables, so no lifetime annotations are needed;
  * values owning lists move on assignment; use-after-move is a compile error;
  * a call may not pass `&mut x` together with any other reference into `x`;
  * a collection being iterated (or matched by reference) is frozen;
  * a loop whose body mutates an outer variable that points into the data stack
    keeps its allocations; every other loop releases them each iteration.
"""

from . import ast as A
from .builtins import BuiltinMixin
from .check_expr import ExprMixin
from .check_lambda import LambdaMixin
from .check_trait import TraitMixin
from .errors import SillyError
from .ir import E, S, Var, is_place, root_var
from .types import (BOOL, CHAR, I64, NEVER, STR, U8, VOID, ArrayTy, ListTy, MapTy, NamedTy, RefTy,
                    TupleTy, is_copy, is_int, region_bearing)


class Loop:
    def __init__(self, depth):
        self.depth = depth
        self.reset = True
        self.carry = {}          # var id -> Var: outer storage the body changes; compacted per iteration
        self.moved_any = set()   # var ids moved anywhere in the body
        self.exit_moved = set()
        self.has_break = False


class FnChecker(LambdaMixin, TraitMixin, BuiltinMixin, ExprMixin):
    def __init__(self, prog, inst):
        self.prog = prog
        self.inst = inst
        self.mod = inst.module
        self.env = inst.env
        self.scopes = [{}]
        self.moved = {}          # var id -> span of the move
        self.diverges = False
        self.loops = []
        self.frozen = {}         # var id -> description of the active borrow
        self.tmp = 0

    # ---- helpers ----
    def err(self, msg, span, hint=None):
        raise SillyError(msg, span, hint)

    def ty(self, texpr):
        return self.prog.resolve_type(texpr, self.env, self.mod)

    def new_var(self, name, ty, span, mutable=False, borrowed=False, is_ref=False, declare=True):
        if ty == VOID or ty == NEVER:
            self.err(f"cannot bind '{name}' to a value of type {ty}", span)
        v = Var(name, ty, mutable=mutable, borrowed=borrowed, is_ref=is_ref, loop_depth=len(self.loops))
        self.inst.locals.append(v)
        if declare and name != "_":
            self.scopes[-1][name] = v
        return v

    def temp(self, ty, span):
        self.tmp += 1
        return self.new_var(f"t{self.tmp}", ty, span, mutable=True, declare=False)

    def lookup_var(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if self.parent is not None:
            return self.capture(name)
        return None

    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        self.scopes.pop()

    # ---- entry ----
    def check(self):
        inst = self.inst
        decl = inst.decl
        params = []
        if isinstance(inst.self_ty, RefTy):
            v = self.new_var("self", inst.self_ty.inner, decl.span, mutable=inst.self_ty.mut, is_ref=True)
            params.append(v)
        elif inst.self_ty is not None:
            params.append(self.new_var("self", inst.self_ty, decl.span, mutable=decl.self_mode == "mut"))
        for (name, pty), p in zip(inst.params, decl.params):
            if self.lookup_var(name) is not None:
                self.err(f"duplicate parameter '{name}'", p.span)
            if isinstance(pty, RefTy):
                v = self.new_var(name, pty.inner, p.span, mutable=pty.mut, is_ref=True)
            else:
                v = self.new_var(name, pty, p.span)
            params.append(v)
        inst.param_vars = params
        body = self.block(decl.body)
        if not self.diverges and inst.ret not in (VOID, NEVER):
            self.err(f"function '{decl.name}' can reach its end without returning a {inst.ret}", decl.span)
        inst.body = body
        inst.done = True

    # ---- blocks & statements ----
    def block(self, stmts, scoped=True):
        if scoped:
            self.push_scope()
        out = []
        for st in stmts:
            out.extend(self.stmt(st))
        if scoped:
            self.pop_scope()
        return out

    def stmt(self, st):
        m = getattr(self, "st_" + type(st).__name__)
        r = m(st)
        return r if isinstance(r, list) else [r]

    def st_Pass(self, st):
        return []

    def st_ExprStmt(self, st):
        e = self.expr(st.expr, None)
        if e.ty == NEVER:
            self.diverges = True
        elif not is_copy(e.ty) and not is_place(e):
            pass  # temporaries are dropped; their storage is reclaimed with the frame
        return S("expr", st.span, e=e)

    def st_Let(self, st):
        ty = self.ty(st.type) if st.type is not None else None
        if st.value is None:
            v = self.bind_pattern_decl(st.pattern, ty, st.mutable)
            return S("let", st.span, var=v, value=None)
        value = self.value(st.value, ty)
        if ty is not None:
            self.expect_type(value, ty, st.value.span)
        if value.ty in (VOID, NEVER):
            if value.ty == NEVER:
                self.diverges = True
                return S("expr", st.span, e=value)
            self.err("cannot bind the result of an expression that has no value", st.value.span)
        if isinstance(st.pattern, A.PBind):
            v = self.new_var(st.pattern.name, value.ty, st.pattern.span, mutable=st.mutable)
            return S("let", st.span, var=v, value=value)
        if isinstance(st.pattern, A.PWild):
            return S("expr", st.span, e=value)
        # tuple destructuring
        tmp = self.temp(value.ty, st.span)
        out = [S("let", st.span, var=tmp, value=value)]
        out += self.destructure(st.pattern, E("local", value.ty, st.span, var=tmp), st.mutable)
        return out

    def bind_pattern_decl(self, pat, ty, mutable):
        if not isinstance(pat, A.PBind):
            self.err("a variable without an initial value must be a simple name", pat.span)
        return self.new_var(pat.name, ty, pat.span, mutable=mutable)

    def destructure(self, pat, src, mutable):
        if isinstance(pat, A.PWild):
            return []
        if isinstance(pat, A.PBind):
            v = self.new_var(pat.name, src.ty, pat.span, mutable=mutable)
            return [S("let", pat.span, var=v, value=src)]
        if not isinstance(src.ty, TupleTy):
            self.err(f"cannot destructure a value of type {src.ty} as a tuple", pat.span)
        if len(pat.subs) != len(src.ty.elems):
            self.err(f"tuple pattern has {len(pat.subs)} elements but the value has {len(src.ty.elems)}", pat.span)
        out = []
        for i, (sub, et) in enumerate(zip(pat.subs, src.ty.elems)):
            out += self.destructure(sub, E("tuple_field", et, pat.span, base=src, index=i), mutable)
        return out

    def st_Assign(self, st):
        if isinstance(st.target, A.TupleLit) and st.op == "=":
            # (a, b) = (b, a): evaluate the whole right side first, then assign element-wise.
            value = self.value(st.value, None)
            if not isinstance(value.ty, TupleTy) or len(value.ty.elems) != len(st.target.elems):
                self.err(f"cannot assign {value.ty} to a {len(st.target.elems)}-element tuple", st.span)
            tmp = self.temp(value.ty, st.span)
            out = [S("let", st.span, var=tmp, value=value)]
            for i, (t, et) in enumerate(zip(st.target.elems, value.ty.elems)):
                if isinstance(t, A.Name) and t.name == "_":
                    continue
                v = self.lookup_var(t.name) if isinstance(t, A.Name) else None
                place = E("local", v.ty, t.span, var=v) if v is not None else self.expr(t, None)
                if not is_place(place):
                    self.err("left side of assignment is not assignable", t.span)
                if place.ty != et:
                    self.err(f"expected {place.ty}, found {et}", t.span)
                self.mutate(place, t.span, whole=True)
                src = E("tuple_field", et, t.span, base=E("local", value.ty, t.span, var=tmp), index=i, name=str(i))
                out.append(S("assign", t.span, place=place, value=src))
            return out
        v =self.lookup_var(st.target.name) if isinstance(st.target, A.Name) and st.op == "=" else None
        if v is not None:
            # Assigning a whole variable is allowed even after it was moved.
            target = E("local", v.ty, st.target.span, var=v)
        else:
            target = self.expr(st.target, None)
        if not is_place(target):
            if isinstance(st.target, A.Index) and getattr(getattr(target, "base", None), "ty", None) == STR or \
                    getattr(target, "args", None) and target.args[0].ty == STR:
                self.err("strings are immutable", st.target.span, hint="build a new string with + or an f-string")
            self.err("left side of assignment is not assignable", st.target.span)
        if st.op == "=":
            value = self.value(st.value, target.ty)
            self.expect_type(value, target.ty, st.value.span)
            self.mutate(target, st.span, whole=True)
            if target.kind == "map_index":
                return S("map_set", st.span, place=target, value=value)
            return S("assign", st.span, place=target, value=value)
        op = st.op[:-1]
        if target.ty == STR and op == "+":
            rhs = self.expr(st.value, STR)
            self.expect_type(rhs, STR, st.value.span)
            self.mutate(target, st.span)
            return S("assign", st.span, place=target, value=E("binary", STR, st.span, op="+", left=target, right=rhs))
        rhs = self.value(st.value, target.ty if op not in ("<<", ">>") else None)
        self.check_arith(op, target.ty, rhs.ty, st.span)
        self.mutate(target, st.span)
        return S("assign_op", st.span, place=target, op=op, value=rhs)

    def st_Return(self, st):
        ret = self.inst.ret
        if st.value is None:
            if ret != VOID:
                self.err(f"missing return value of type {ret}", st.span)
            value = None
        else:
            if ret == VOID:
                self.err("this function does not return a value", st.value.span,
                         hint="add `-> Type` to the function signature")
            value = self.value(st.value, ret)
            self.expect_type(value, ret, st.value.span)
        self.diverges = True
        return S("return", st.span, value=value)

    def st_Break(self, st):
        if not self.loops:
            self.err("`break` outside of a loop", st.span)
        lp = self.loops[-1]
        lp.has_break = True
        lp.exit_moved |= set(self.moved)
        self.diverges = True
        return S("break", st.span)

    def st_Continue(self, st):
        if not self.loops:
            self.err("`continue` outside of a loop", st.span)
        self.loops[-1].exit_moved |= set(self.moved)
        self.diverges = True
        return S("continue", st.span)

    def st_Assert(self, st):
        cond = self.cond(st.cond)
        msg = None
        if st.msg is not None:
            msg = self.expr(st.msg, STR)
            self.expect_type(msg, STR, st.msg.span)
        return S("assert", st.span, cond=cond, msg=msg, text=self.source_text(st.cond))

    def source_text(self, e):
        lines = self.prog.sources.get(e.span.file, "").split("\n")
        if 0 < e.span.line <= len(lines):
            return lines[e.span.line - 1].strip()
        return "assertion"

    # ---- flow merging ----
    def branch(self, fn):
        """Run fn from the current state; return (result, moved_after, diverged)."""
        saved_moved, saved_div = dict(self.moved), self.diverges
        self.diverges = False
        r = fn()
        out = (r, self.moved, self.diverges)
        self.moved, self.diverges = saved_moved, saved_div
        return out

    def merge(self, results, exhaustive):
        """Combine branch states: a value moved on any live path counts as moved."""
        live = [m for _, m, d in results if not d]
        merged = {}
        if not exhaustive:
            live.append(self.moved)
        for m in live:
            merged.update(m)
        self.moved = merged if live or not exhaustive else dict(self.moved)
        if exhaustive and not live:
            self.diverges = True
        return [r for r, _, _ in results]

    def st_If(self, st):
        results = []
        cond_scopes = []
        for cond_ast, body in st.branches:
            self.push_scope()
            cond, pre = self.cond_with_bindings(cond_ast)
            cond_scopes.append(self.scopes[-1])
            res = self.branch(lambda body=body: self.block(body))
            self.pop_scope()
            results.append(((cond, pre, res[0]), res[1], res[2]))
        if st.orelse is not None:
            res = self.branch(lambda: self.block(st.orelse))
            results.append((("else", None, res[0]), res[1], res[2]))
        parts = self.merge(results, exhaustive=st.orelse is not None)
        branches = [(c, pre, b) for c, pre, b in parts if c != "else"]
        orelse = parts[-1][2] if st.orelse is not None else None
        return S("if", st.span, branches=branches, orelse=orelse)

    def run_loop(self, body_fn):
        lp = Loop(len(self.loops))
        self.loops.append(lp)
        before = dict(self.moved)
        saved_div = self.diverges
        self.diverges = False
        body = body_fn()
        end_moved = set(self.moved) | lp.exit_moved
        self.loops.pop()
        if lp.carry.keys() & (lp.moved_any | lp.exit_moved):
            # A carried variable may hold a moved-out (stale) value at the next iteration's
            # start, so it can't be relocated: keep this loop's allocations instead.
            lp.reset = False
            lp.carry = {}
        for vid in end_moved - set(before):
            var = self.var_by_id(vid)
            if var is not None and var.loop_depth <= lp.depth and vid in self.moved:
                self.err(f"'{var.name}' is moved inside a loop and would be used again in the next iteration",
                         self.moved[vid], hint=f"use `.clone()`, or reassign '{var.name}' before the iteration ends")
        merged = dict(before)
        merged.update(self.moved)
        self.moved = merged
        self.diverges = saved_div
        return lp, body

    def var_by_id(self, vid):
        for v in self.inst.locals:
            if v.id == vid:
                return v
        return None

    def st_While(self, st):
        if isinstance(st.cond, A.BoolLit) and st.cond.value:
            return self.st_Loop(A.Loop(st.body, span=st.span))

        def body():
            self.push_scope()
            cond, pre = self.cond_with_bindings(st.cond)
            b = self.block(st.body)
            self.pop_scope()
            return cond, pre, b

        lp, (cond, pre, b) = self.run_loop(body)
        return S("while", st.span, cond=cond, pre=pre, body=b, reset=lp.reset, carry=list(lp.carry.values()))

    def st_Loop(self, st):
        lp, b = self.run_loop(lambda: self.block(st.body))
        if not lp.has_break:
            self.diverges = True
        return S("loop", st.span, body=b, reset=lp.reset, carry=list(lp.carry.values()))

    def st_For(self, st):
        it = st.iterable
        # for i in range(...) / a..b
        if isinstance(it, A.Range) or (isinstance(it, A.Call) and isinstance(it.func, A.Name)
                                       and it.func.name == "range" and self.lookup_var("range") is None):
            return self.for_range(st)
        enum_idx = None
        if isinstance(it, A.Call) and isinstance(it.func, A.Name) and it.func.name == "enumerate" \
                and self.lookup_var("enumerate") is None:
            if len(it.args) != 1:
                self.err("enumerate() takes exactly one argument", it.span)
            if not isinstance(st.pattern, A.PTuple) or len(st.pattern.subs) != 2:
                self.err("use `for i, x in enumerate(xs):`", st.pattern.span)
            enum_idx, pat = st.pattern.subs
            it = it.args[0].value
        else:
            pat = st.pattern
        mode = elem = src = None
        if isinstance(it, A.Call) and isinstance(it.func, A.Field) and it.func.name == "items" and not it.args:
            recv = self.expr(it.func.base, None)
            if isinstance(recv.ty, MapTy):
                # for k, v in m.items(): walk the entries in place, no list is built.
                src, mode, elem = recv, "items", TupleTy([recv.ty.k, recv.ty.v])
        if src is None:
            src = self.expr(it, None)
        if mode == "items":
            assert elem is not None
        elif src.ty == STR:
            elem = CHAR
        elif isinstance(src.ty, (ListTy, ArrayTy)):
            elem = src.ty.elem
        elif isinstance(src.ty, MapTy):
            mode, elem = "keys", src.ty.k
        else:
            self.err(f"cannot iterate over a value of type {src.ty}", it.span,
                     hint="iterate over a list, array, str, range(...) or a..b")
        owned_temp = not is_place(src)
        if owned_temp:
            # Iterating a temporary: keep it alive in a hidden variable.
            tv = self.temp(src.ty, it.span)
            pre = [S("let", it.span, var=tv, value=src)]
            src = E("local", src.ty, it.span, var=tv)
        else:
            pre = []
        root = root_var(src)

        def body():
            self.push_scope()
            iv = None
            if enum_idx is not None:
                if not isinstance(enum_idx, (A.PBind, A.PWild)):
                    self.err("enumerate index must be a name", enum_idx.span)
                iv = self.new_var(enum_idx.name if isinstance(enum_idx, A.PBind) else "_", I64, enum_idx.span)
            borrowed = not is_copy(elem)
            if isinstance(pat, A.PBind):
                ev = self.new_var(pat.name, elem, pat.span, borrowed=borrowed)
                binds = []
            else:
                ev = self.temp(elem, pat.span)
                ev.borrowed = borrowed
                binds = self.destructure(pat, E("local", elem, pat.span, var=ev), False)
                for b in binds:
                    b.var.borrowed = borrowed or b.var.borrowed
            b = binds + self.block(st.body)
            self.pop_scope()
            return iv, ev, b

        if root is not None:
            self.frozen[root.id] = f"it is being iterated by the `for` loop at line {st.span.line}"
        lp, (iv, ev, b) = self.run_loop(body)
        if root is not None:
            del self.frozen[root.id]
        return pre + [S("for_each", st.span, src=src, var=ev, idx=iv, body=b, reset=lp.reset, carry=list(lp.carry.values()), mode=mode)]

    def for_range(self, st):
        it = st.iterable
        if not isinstance(st.pattern, (A.PBind, A.PWild)):
            self.err("a range loop binds a single name", st.pattern.span)
        step = None
        inclusive = False
        if isinstance(it, A.Range):
            lo_ast, hi_ast, inclusive = it.lo, it.hi, it.inclusive
        else:
            args = [a.value for a in it.args]
            if not 1 <= len(args) <= 3 or any(a.name for a in it.args):
                self.err("range() takes 1 to 3 positional arguments", it.span)
            if len(args) == 1:
                lo_ast, hi_ast = A.IntLit(0, None, span=it.span), args[0]
            else:
                lo_ast, hi_ast = args[0], args[1]
            if len(args) == 3:
                step = args[2]
        lo, hi = self.int_pair(lo_ast, hi_ast)
        if step is not None:
            step_ir = self.value(step, lo.ty)
            self.expect_type(step_ir, lo.ty, step.span)
            if step_ir.kind == "int" and step_ir.value == 0:
                self.err("range() step must not be zero", step.span)
        else:
            step_ir = None

        def body():
            self.push_scope()
            name = st.pattern.name if isinstance(st.pattern, A.PBind) else "_"
            v = self.new_var(name, lo.ty, st.pattern.span)
            b = self.block(st.body)
            self.pop_scope()
            return v, b

        lp, (v, b) = self.run_loop(body)
        return S("for_range", st.span, var=v, lo=lo, hi=hi, step=step_ir, inclusive=inclusive, body=b,
                 reset=lp.reset, carry=list(lp.carry.values()))

    def int_pair(self, a, b):
        if self.is_untyped_lit(a) and not self.is_untyped_lit(b):
            hi = self.value(b, None)
            lo = self.value(a, hi.ty)
        else:
            lo = self.value(a, None)
            hi = self.value(b, lo.ty)
        if not is_int(lo.ty):
            self.err(f"range bounds must be integers, found {lo.ty}", a.span)
        self.expect_type(hi, lo.ty, b.span)
        return lo, hi

    # ---- match ----
    def st_Match(self, st):
        subj = self.expr(st.subject, None)
        pre = []
        if is_place(subj):
            src = subj
            by_ref = True
        else:
            tv = self.temp(subj.ty, st.subject.span)
            pre.append(S("let", st.span, var=tv, value=subj))
            src = E("local", subj.ty, st.span, var=tv)
            by_ref = False
        root = root_var(src) if by_ref else None
        # Matching an owned local lets arms move bindings out of it; doing so moves the local.
        owner = src.var if by_ref and src.kind == "local" and not src.var.is_ref and not src.var.borrowed \
            and not getattr(src.var, "move_root", None) else None
        results = []
        for arm in st.arms:
            def run(arm=arm):
                self.push_scope()
                pat = self.pattern(arm.pattern, src.ty, borrowed=by_ref and owner is None, move_root=owner)
                if root is not None and self.pattern_borrows(pat):
                    self.frozen[root.id] = f"it is borrowed by the `case` at line {arm.span.line}"
                guard = self.cond(arm.guard) if arm.guard is not None else None
                body = self.block(arm.body)
                self.frozen.pop(root.id if root else None, None)
                self.pop_scope()
                return (pat, guard, body)
            results.append(self.branch(run))
        missing = self.exhaustiveness(src.ty, st.arms, st.span)
        arms = self.merge(results, exhaustive=not missing)
        return pre + [S("match", st.span, subject=src, arms=arms, ty=src.ty)]

    def pattern_borrows(self, p):
        if p.kind == "pbind":
            return p.var.borrowed or getattr(p.var, "move_root", None) is not None
        return any(self.pattern_borrows(s) for s in getattr(p, "subs", []) or [])

    def exhaustiveness(self, ty, arms, span):
        def irrefutable(p):
            if isinstance(p, (A.PWild, A.PBind)):
                return True
            if isinstance(p, A.PTuple):
                return all(irrefutable(s) for s in p.subs)
            if isinstance(p, A.POr):
                return any(irrefutable(a) for a in p.alts)
            return False

        covered = set()
        bools = set()
        for arm in arms:
            if arm.guard is not None:
                continue
            alts = arm.pattern.alts if isinstance(arm.pattern, A.POr) else [arm.pattern]
            for p in alts:
                if irrefutable(p):
                    return None
                if isinstance(p, A.PVariant) and isinstance(ty, NamedTy) and ty.is_enum:
                    if p.subs is None or all(irrefutable(s) for s in p.subs):
                        covered.add(p.path[-1])
                if isinstance(p, A.PLit) and isinstance(p.expr, A.BoolLit):
                    bools.add(p.expr.value)
        if isinstance(ty, NamedTy) and ty.is_enum:
            missing = [n for n, _ in ty.info.variants if n not in covered]
            if missing:
                self.err(f"match is not exhaustive: missing {', '.join(missing)}", span,
                         hint="add the missing cases or a `case _:` arm")
            return None
        if ty == BOOL and bools == {True, False}:
            return None
        self.err(f"match on {ty} is not exhaustive", span, hint="add a `case _:` arm")

    def pattern(self, p, ty, borrowed, move_root=None):
        """Lower a pattern against a subject of type ty. Bindings are declared in the current scope."""
        if isinstance(p, A.PWild):
            return E("pwild", ty, p.span)
        if isinstance(p, A.PBind):
            v = self.new_var(p.name, ty, p.span, mutable=p.mut, borrowed=borrowed and not is_copy(ty))
            if move_root is not None and not is_copy(ty):
                v.move_root = move_root
            return E("pbind", ty, p.span, var=v)
        if isinstance(p, A.PLit):
            lit = self.expr(p.expr, ty)
            self.expect_type(lit, ty, p.span)
            return E("plit", ty, p.span, value=lit)
        if isinstance(p, A.PRange):
            lo = self.expr(p.lo, ty)
            hi = self.expr(p.hi, ty)
            self.expect_type(lo, ty, p.span)
            self.expect_type(hi, ty, p.span)
            if not (is_int(ty) or ty == CHAR or ty == U8):
                self.err(f"range patterns need an integer or char subject, found {ty}", p.span)
            return E("prange", ty, p.span, lo=lo, hi=hi, inclusive=p.inclusive)
        if isinstance(p, A.PTuple):
            if not isinstance(ty, TupleTy) or len(ty.elems) != len(p.subs):
                self.err(f"tuple pattern does not match type {ty}", p.span)
            return E("ptuple", ty, p.span, subs=[self.pattern(s, t, borrowed, move_root) for s, t in zip(p.subs, ty.elems)])
        if isinstance(p, A.POr):
            alts = []
            for a in p.alts:
                before = len(self.inst.locals)
                alts.append(self.pattern(a, ty, borrowed, move_root))
                if len(self.inst.locals) != before:
                    self.err("alternatives in an or-pattern cannot bind names", a.span)
            return E("por", ty, p.span, alts=alts)
        if isinstance(p, A.PVariant):
            if not (isinstance(ty, NamedTy) and ty.is_enum):
                self.err(f"variant pattern '{'.'.join(p.path)}' used on a value of type {ty}", p.span)
            info = ty.info
            name = p.path[-1]
            if len(p.path) > 1 and p.path[-2] != info.decl.name:
                self.err(f"'{'.'.join(p.path[:-1])}' is not {info.decl.name}", p.span)
            if name not in info.vindex:
                self.err(f"{info.ty} has no variant '{name}'", p.span,
                         hint="variants: " + ", ".join(n for n, _ in info.variants))
            vi = info.vindex[name]
            fields = info.variants[vi][1]
            subs = p.subs or []
            if p.subs is not None and len(subs) != len(fields):
                self.err(f"variant '{name}' has {len(fields)} field(s), pattern has {len(subs)}", p.span)
            return E("pvariant", ty, p.span, info=info, vidx=vi,
                     subs=[self.pattern(s, ft, borrowed, move_root) for s, (_, ft) in zip(subs, fields)])
        self.err("unsupported pattern", p.span)

    # ---- conditions with `is` bindings ----
    def cond(self, e):
        c, pre = self.cond_with_bindings(e)
        if pre:
            # bindings in a guard/assert still need declarations
            return E("seq", BOOL, e.span, stmts=[S("let", e.span, var=v, value=None) for v in pre], result=c)
        return c

    def cond_with_bindings(self, e):
        """Check a condition; `x is P(v)` binders become visible in the guarded block.
        Returns (cond IR, list of vars to pre-declare)."""
        before = len(self.inst.locals)
        c = self.cond_expr(e)
        pre = [v for v in self.inst.locals[before:] if getattr(v, "is_binding", False)]
        return c, pre

    def cond_expr(self, e):
        if isinstance(e, A.Binary) and e.op == "and":
            l = self.cond_expr(e.left)
            r = self.cond_expr(e.right)
            return E("logic", BOOL, e.span, op="and", left=l, right=r)
        c = self.expr(e, BOOL)
        self.expect_type(c, BOOL, e.span)
        return c

    def is_expr(self, e):
        subj = self.expr(e.expr, None)
        pre = []
        if is_place(subj):
            src, by_ref = subj, True
        else:
            tv = self.temp(subj.ty, e.span)
            tv.is_binding = True
            src, by_ref = E("local", subj.ty, e.span, var=tv), False
            pre = [tv]
            subj_init = subj
        before = len(self.inst.locals)
        pat = self.pattern(e.pattern, src.ty, borrowed=by_ref)
        for v in self.inst.locals[before:]:
            v.is_binding = True
        r = E("is", BOOL, e.span, src=src, pattern=pat)
        if pre:
            r.init = subj_init
            r.init_var = pre[0]
        return r

    # ---- moves & mutation ----
    def consume(self, e, span):
        """Mark e as moved if it is a place of a non-Copy type."""
        if is_copy(e.ty) or not is_place(e):
            return e
        if e.kind == "local":
            v = e.var
            if getattr(v, "captured", False):
                self.err(f"cannot move captured variable '{v.name}' out of a lambda", span,
                         hint=f"use `{v.name}.clone()`; a lambda can run many times")
            if v.borrowed and self.has_deco(self.inst.decl, "views"):
                return e    # prelude helpers lend views to lambdas, which cannot keep them
            if v.borrowed:
                self.err(f"cannot move '{v.name}': it is a borrowed view", span,
                         hint=f"use `{v.name}.clone()` to get an owned copy")
            if v.is_ref:
                self.err(f"cannot move out of reference parameter '{v.name}'", span,
                         hint=f"use `{v.name}.clone()`")
            if v.id in self.frozen:
                self.err(f"cannot move '{v.name}' while {self.frozen[v.id]}", span)
            self.moved[v.id] = span
            if getattr(v, "move_root", None) is not None:
                self.moved[v.move_root.id] = span
            for lp in self.loops:
                lp.moved_any.add(v.id)
                if getattr(v, "move_root", None) is not None:
                    lp.moved_any.add(v.move_root.id)
            return e
        self.err("cannot move a value out of a field or index", span,
                 hint="use `.clone()`, `take(&mut place)` or `swap(&mut a, &mut b)`")

    def mutate(self, place, span, whole=False):
        v = root_var(place)
        if v is None:
            self.err("cannot assign to a temporary value", span)
        if getattr(v, "captured", False):
            self.err(f"cannot modify captured variable '{v.name}'", span,
                     hint="lambdas capture by value and their captures are read-only")
        if place.kind == "index" and place.base.ty == STR:
            self.err("strings are immutable", span, hint="build a new string with + or an f-string")
        if v.borrowed:
            self.err(f"cannot modify '{v.name}': it is a borrowed view", span)
        if not v.mutable:
            what = "parameter" if v.is_ref or v in getattr(self.inst, "param_vars", []) else "variable"
            hint = f"declare it with `var {v.name}`" if what == "variable" else (
                "take `mut self`" if v.name == "self" else "take the parameter as `&mut`")
            self.err(f"cannot modify immutable {what} '{v.name}'", span, hint=hint)
        if v.id in self.frozen:
            self.err(f"cannot modify '{v.name}' while {self.frozen[v.id]}", span)
        if getattr(v, "move_root", None) is not None:
            self.moved[v.move_root.id] = span
            for lp in self.loops:
                lp.moved_any.add(v.move_root.id)
        if whole and place.kind == "local":
            self.moved.pop(v.id, None)
        if region_bearing(v.ty):
            for lp in self.loops[v.loop_depth:]:
                lp.carry[v.id] = v
