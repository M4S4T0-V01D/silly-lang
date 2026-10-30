"""C code for statements, loops and function frames.

Memory: a function saves the data-stack top on entry (`_fb`) and restores it
on return, unless it is transparent (its result or a `&mut` argument owns
storage in the frame). Loops whose iterations leave nothing behind restore
the top at the start of every iteration (`_lr`).
"""

from .types import RefTy, ArrayTy, ListTy, MapTy, VOID, NEVER, STR, region_bearing
from .cg_expr import c_string

GROWING = {"list.push", "list.insert", "list.extend", "map.insert"}
IND = "    "


def mut_region_inst(inst):
    if any(isinstance(pt, RefTy) and pt.mut and region_bearing(pt.inner) for _, pt in inst.params):
        return True
    st = inst.self_ty
    return isinstance(st, RefTy) and st.mut and region_bearing(st.inner)


class StmtMixin:
    # ---- data-stack safety for discarded results ----
    def keeps_storage(self, e):
        """True when e may write data-stack storage into memory that outlives it."""
        k = getattr(e, "kind", None)
        if k is None:
            return False
        if k == "call" and mut_region_inst(e.inst):
            return True
        if k == "call_ind" and any(isinstance(p, RefTy) and p.mut for p in e.fn.ty.params):
            return True
        if k == "bi" and e.name in GROWING:
            return True
        if k == "seq":
            return True
        for name, sub in vars(e).items():
            if name in ("ty", "span", "inst", "info", "var", "init_var"):
                continue
            if hasattr(sub, "kind") and not isinstance(sub, type):
                if self.keeps_storage(sub):
                    return True
            elif isinstance(sub, (list, tuple)):
                for x in sub:
                    if isinstance(x, tuple):
                        if any(self.keeps_storage(y) for y in x if hasattr(y, "kind")):
                            return True
                    elif hasattr(x, "kind") and self.keeps_storage(x):
                        return True
        return False

    # ---- blocks ----
    def block(self, stmts, ind):
        out = []
        for s in stmts:
            out += self.stmt(s, ind)
        return out

    def stmt(self, s, ind):
        p = IND * ind
        return [p + line for line in getattr(self, "s_" + s.kind)(s, ind)]

    def sub(self, stmts, ind):
        """Lines of a nested block, already indented relative to the caller's level."""
        return [IND + line for line in self.block_raw(stmts)]

    def block_raw(self, stmts):
        out = []
        for s in stmts:
            out += getattr(self, "s_" + s.kind)(s, 0)
        return out

    # ---- simple statements ----
    def s_expr(self, s, ind):
        e = s.e
        c = self.value(e) if e.ty != NEVER else self.expr(e)
        if e.ty == NEVER or self.pure(e) or self.keeps_storage(e) or e.kind == "bi" and e.name in ("print", "eprint"):
            return [c + ";"]
        t = self.tmp("_s")
        return [f"{{ uint8_t *{t} = sl_ds.top; {c}; SL_RESET({t}); }}"]

    def s_let(self, s, ind):
        if s.value is None:
            return []
        v = s.var
        return [f"{v.cname} = {self.value(s.value, self.value_ctype(v.ty))};"]

    def s_assign(self, s, ind):
        place, value = s.place, s.value
        ct = self.value_ctype(place.ty)
        if self.pure(value) or (self.simple_place(place) and place.kind == "local"):
            return [f"{self.expr(place)} = {self.value(value, ct)};"]
        t = self.tmp("_v")
        return [f"{{ {ct} {t} = {self.value(value, ct)}; {self.expr(place)} = {t}; }}"]

    def s_map_set(self, s, ind):
        place, value = s.place, s.value
        t = place.base.ty
        vc = self.field_ctype(t.v)
        v, f = self.tmp("_v"), self.tmp("_f")
        # The value is computed before the map takes its slot (it may allocate).
        pre = [f"{vc} {v} = {self.value(value, vc)};"]
        kv = self.map_key(t, place.key, pre)
        mp = self.map_ptr(place.base, pre)
        pre.append(f"bool {f}; *{self.map_put_fn(t)}({mp}, {kv}, &{f}) = {v};")
        return ["{ " + " ".join(pre) + " }"]

    def s_assign_op(self, s, ind):
        place, value = s.place, s.value
        t = place.ty
        pre = []
        v = self.value(value)
        if not self.pure(value) and not self.is_const(value):
            tv = self.tmp("_v")
            pre.append(f"{self.value_ctype(value.ty)} {tv} = {v};")
            v = tv
        if self.simple_place(place):
            dst = self.expr(place)
        else:
            pp = self.tmp("_p")
            pre.append(f"{self.ctype(t)} *{pp} = &{self.expr(place)};")
            dst = f"(*{pp})"
        code = f"{dst} = {self.binop(s.op, t, dst, v, value.ty, s.span)};"
        if pre:
            return ["{ " + " ".join(pre) + " " + code + " }"]
        return [code]

    def return_code(self, out):
        """A C statement that returns the C value `out` (None for void) from the current function."""
        inst = self.cur
        if out is None:
            return "return;" if inst.transparent else "{ SL_RESET(_fb); return; }"
        if inst.transparent:
            return f"return {out};"
        rc = self.value_ctype(inst.ret)
        if inst.compact and region_bearing(inst.ret):
            return f"{{ {rc} _r = {out}; {self.compact_fn(inst.ret)}(&_r, _fb); return _r; }}"
        return f"{{ {rc} _r = {out}; SL_RESET(_fb); return _r; }}"

    def s_return(self, s, ind):
        if s.value is None:
            return [self.return_code(None)]
        if s.value.ty == NEVER:
            return [self.expr(s.value) + ";"]
        return [self.return_code(self.value(s.value, self.value_ctype(self.cur.ret)))]

    def s_break(self, s, ind):
        return ["break;"]

    def s_continue(self, s, ind):
        return ["continue;"]

    def s_assert(self, s, ind):
        loc = self.loc(s.span)
        if s.msg is not None:
            fail = f"sl_panic_str({loc}, {self.value(s.msg)});"
        else:
            fail = f'sl_panic({loc}, "assertion failed: %s", {c_string(s.text.encode())});'
        return [f"if (SL_UNLIKELY(!({self.value(s.cond)}))) {fail}"]

    # ---- branching ----
    def s_if(self, s, ind):
        out = []
        for i, (cond, pre, body) in enumerate(s.branches):
            kw = "if" if i == 0 else "} else if"
            out.append(f"{kw} ({self.value(cond)}) {{")
            out += self.sub(body, ind)
        if s.orelse:
            out.append("} else {")
            out += self.sub(s.orelse, ind)
        out.append("}")
        return out

    def s_match(self, s, ind):
        subj = s.subject
        out = []
        if self.simple_place(subj):
            sc = self.expr(subj)
        else:
            m = self.tmp("_m")
            out.append(f"{self.ctype(subj.ty)} *{m} = &{self.expr(subj)};")
            sc = f"(*{m})"
        chain = []
        closed = False
        for pat, guard, body in s.arms:
            cond = self.pat(pat, sc)
            if guard is None and (cond == "1" or pat.kind == "pbind"):
                bind = [IND + cond + ";"] if pat.kind == "pbind" else []
                chain += (["} else {"] if chain else ["{"]) + bind + self.sub(body, ind)
                closed = True
                break
            if guard is not None:
                cond = self.value(guard) if cond == "1" else f"{cond} && {self.value(guard)}"
            chain.append(f"{'} else if' if chain else 'if'} ({cond}) {{")
            chain += self.sub(body, ind)
        if not chain:
            return out
        if not closed:
            chain += ["} else {", IND + f'sl_panic({self.loc(s.span)}, "no case matched the value");']
        chain.append("}")
        if out:
            return ["{"] + [IND + l for l in out + chain] + ["}"]
        return chain

    # ---- loops ----
    def loop_frame(self, reset, carry=None):
        """(before-loop lines, per-iteration lines, after-loop lines) for the data-stack reset.

        A loop whose body changes outer variables that hold storage ("carried" variables)
        can't simply reset each iteration. Instead, once the iteration region holds more
        than twice what survived the last compaction (plus SL_CARRY_SLACK), the carried
        values are relocated to the bottom of the region and everything else is freed.
        The doubling keeps the copying amortised linear in what the loop allocates."""
        if not reset:
            return [], [], []
        lr = self.tmp("_lr")
        if not carry:
            return [f"uint8_t *{lr} = sl_ds.top;"], [f"SL_RESET({lr});"], [f"SL_RESET({lr});"]
        lk = self.tmp("_lk")
        ptrs = [(v.ty.inner if isinstance(v.ty, RefTy) else v.ty, v.cname if v.is_ref else f"&{v.cname}")
                for v in carry]
        out = " ".join(self.reloc_stmt(t, p) for t, p in ptrs)
        back = " ".join(self.reloc_stmt(t, p).replace("lo, hi)", "xb, xt)") for t, p in ptrs)
        each = [f"if (SL_UNLIKELY((size_t)(sl_ds.top - {lr}) > {lk})) {{",
                IND + "uint8_t *lo = " + lr + ", *hi = sl_ds.top;",
                IND + "sl_swap_arenas(); uint8_t *xb = sl_ds.top;",
                IND + out,
                IND + "uint8_t *xt = sl_ds.top; sl_swap_arenas();",
                IND + f"SL_RESET({lr});",
                IND + back,
                IND + "sl_xs.top = xb; sl_str_end = NULL;",
                IND + f"{lk} = 2 * (size_t)(sl_ds.top - {lr}) + SL_CARRY_SLACK;",
                "}"]
        # After the loop the carried values may have been moved out, so nothing is relocated
        # there; the last iteration's leftovers go when the enclosing scope ends.
        return [f"uint8_t *{lr} = sl_ds.top; size_t {lk} = SL_CARRY_SLACK;"], each, []

    def wrap_loop(self, before, loop, after):
        if not before and not after:
            return loop
        return ["{"] + [IND + l for l in before + loop + after] + ["}"]

    def s_while(self, s, ind):
        before, each, after = self.loop_frame(s.reset, getattr(s, "carry", None))
        body = [IND + l for l in each] + [IND + f"if (!({self.value(s.cond)})) break;"] + self.sub(s.body, ind)
        return self.wrap_loop(before, ["for (;;) {"] + body + ["}"], after)

    def s_loop(self, s, ind):
        before, each, after = self.loop_frame(s.reset, getattr(s, "carry", None))
        body = [IND + l for l in each] + self.sub(s.body, ind)
        return self.wrap_loop(before, ["for (;;) {"] + body + ["}"], after)

    def s_for_each(self, s, ind):
        before, each, after = self.loop_frame(s.reset, getattr(s, "carry", None))
        src = s.src
        st = src.ty
        j = self.tmp("_j")
        head = [IND + l for l in each]
        if s.idx is not None:
            head.append(IND + f"{s.idx.cname} = {j};")
        var = s.var.cname
        if st == STR:
            sv, k = self.tmp("_s"), self.tmp("_k")
            before = before + [f"sl_str {sv} = {self.expr(src)};"]
            loop = [f"for (int64_t {k} = 0, {j} = 0; {k} < {sv}.n; {j}++) {{"]
            head.append(IND + f"{var} = sl_utf8_next({sv}.p, {sv}.n, &{k});")
        elif isinstance(st, ListTy):
            lv = self.tmp("_l")
            ec = self.ctype(st.elem)
            before = before + [f"sl_list {lv}h = {self.expr(src)}; {ec} *{lv} = ({ec} *){lv}h.p;"]
            loop = [f"for (int64_t {j} = 0; {j} < {lv}h.n; {j}++) {{"]
            head.append(IND + f"{var} = {lv}[{j}];")
        elif isinstance(st, MapTy):
            mv, q = self.tmp("_m"), self.tmp("_q")
            en = self.entry_ctype(st)
            before = before + [f"sl_map {mv}h = {self.expr(src)}; {en} *{mv} = ({en} *){mv}h.p;"]
            loop = [f"for (int64_t {q} = 0, {j} = -1; {q} < {mv}h.n; {q}++) {{",
                    IND + f"if (!{mv}[{q}].h) continue;", IND + f"{j}++;"]
            if s.mode == "items":
                head.append(IND + f"{var} = ({self.ctype(s.var.ty)}){{{mv}[{q}].k, {mv}[{q}].v}};")
            else:
                head.append(IND + f"{var} = {mv}[{q}].k;")
        else:
            assert isinstance(st, ArrayTy)
            av = self.tmp("_a")
            ec = self.ctype(st.elem)
            before = before + [f"{ec} *{av} = {self.expr(src)}.a;"]
            loop = [f"for (int64_t {j} = 0; {j} < {st.size}; {j}++) {{"]
            head.append(IND + f"{var} = {av}[{j}];")
        return self.wrap_loop(before, loop + head + self.sub(s.body, ind) + ["}"], after)

    def s_for_range(self, s, ind):
        before, each, after = self.loop_frame(s.reset, getattr(s, "carry", None))
        t = s.var.ty
        ct = self.ctype(t)
        var = s.var.cname
        lo = self.value(s.lo)
        hi = self.value(s.hi)
        h = self.tmp("_h")
        i = self.tmp("_i")
        body = self.sub(s.body, ind)
        each = [IND + l for l in each]
        if s.step is None and not s.inclusive:
            before = before + [f"{ct} {i} = {lo}; {ct} {h} = {hi};"]
            loop = [f"for (; {i} < {h}; {i}++) {{"] + each + [IND + f"{var} = {i};"] + body + ["}"]
            return ["{"] + [IND + l for l in before + loop + after] + ["}"]
        go = self.tmp("_go")
        if s.step is None:
            before = before + [f"{ct} {i} = {lo}; {ct} {h} = {hi}; bool {go} = {i} <= {h};"]
            step_lines = [IND + f"{go} = {i} != {h};", IND + f"if ({go}) {i}++;"]
        else:
            stv = self.tmp("_st")
            cmp_eq = "=" if s.inclusive else ""
            before = before + [
                f"{ct} {i} = {lo}; {ct} {h} = {hi}; {ct} {stv} = {self.value(s.step)};",
                f'if (SL_UNLIKELY({stv} == 0)) sl_panic({self.loc(s.step.span)}, "range() step must not be zero");',
                f"bool {go} = {stv} > 0 ? {i} <{cmp_eq} {h} : {i} >{cmp_eq} {h};"]
            d, m = self.tmp("_d"), self.tmp("_n")
            step_lines = [
                IND + f"uint64_t {d} = {stv} > 0 ? (uint64_t){h} - (uint64_t){i} : (uint64_t){i} - (uint64_t){h};",
                IND + f"uint64_t {m} = {stv} > 0 ? (uint64_t){stv} : -(uint64_t){stv};",
                IND + f"{go} = {d} {'>=' if s.inclusive else '>'} {m};",
                IND + f"if ({go}) {i} = ({ct})({i} + {stv});"]
        loop = [f"while ({go}) {{"] + each + [IND + f"{var} = {i};"] + step_lines + body + ["}"]
        return ["{"] + [IND + l for l in before + loop + after] + ["}"]
