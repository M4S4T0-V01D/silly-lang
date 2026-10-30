"""C code for builtin functions and methods (E("bi", name=...))."""

from .ir import is_place
from .types import ListTy, ArrayTy, MapTy, TupleTy, STR, CHAR, BOOL, VOID, NEVER, is_int, is_float, is_signed
from .cg_expr import LIT_KINDS


class BuiltinsMixin:
    # ---- helpers ----
    def opt_some(self, t, v):
        info = t.info
        i = info.vindex["Some"]
        return f"(({self.ctype(t)}){{.tag = {i}, .u.v{i} = {{{v}}}}})"

    def opt_none(self, t):
        return f"(({self.ctype(t)}){{.tag = {t.info.vindex['None']}}})"

    def res(self, t, ok, v):
        i = t.info.vindex["Ok" if ok else "Err"]
        return f"(({self.ctype(t)}){{.tag = {i}, .u.v{i} = {{{v}}}}})"

    def list_ptr(self, recv, pre):
        """A `sl_list *` C expression for a list place, hoisted when it is not trivially re-evaluable."""
        if self.simple_place(recv):
            return f"(&{self.expr(recv)})"
        p = self.tmp("_lp")
        pre.append(f"sl_list *{p} = &{self.expr(recv)};")
        return p

    def seq_view(self, recv, pre):
        """(element pointer, length) for reading a list or array."""
        t = recv.ty
        ec = self.ctype(t.elem)
        if isinstance(t, ArrayTy):
            if is_place(recv):
                p = self.tmp("_ap")
                pre.append(f"{self.ctype(t)} *{p} = &{self.expr(recv)};")
                return f"{p}->a", str(t.size)
            a = self.tmp("_a")
            pre.append(f"{self.ctype(t)} {a} = {self.value(recv)};")
            return f"{a}.a", str(t.size)
        if self.simple_place(recv):
            v = self.expr(recv)
        else:
            v = self.tmp("_s")
            pre.append(f"sl_list {v} = {self.value(recv)};")
        return f"(({ec} *){v}.p)", f"{v}.n"

    def args_seq(self, e, start=0):
        return self.eval_seq(e.args[start:])

    # ---- tasks ----
    def task_join_fn(self, r):
        """R join_K(sl_task *t): wait, copy the result into this thread's stack, free the task."""
        def make(name):
            if r in (VOID, NEVER):
                return (f"static void {name}(sl_task *t)",
                        "{\n    sl_task_wait(t);\n    sl_task_free(t);\n}")
            c = self.ctype(r)
            reloc = self.reloc_stmt(r, "&v")
            return (f"static {c} {name}(sl_task *t)",
                    f"{{\n    sl_task_wait(t);\n    {c} v = *({c} *)t->out;\n"
                    f"    const uint8_t *lo = t->ds.base, *hi = t->ds.end;\n    (void)lo; (void)hi;\n"
                    f"    {reloc}\n    sl_task_free(t);\n    return v;\n}}")
        return self.helper("join", r, make)

    def bi_spawn(self, e):
        f = e.args[0]
        ft = f.ty
        r = ft.ret

        def make(name):
            call = f"(({self.fnptr(ft)})t->f.code)(t->f.env)"
            body = call + ";" if r in (VOID, NEVER) else f"*({self.ctype(r)} *)t->out = {call};"
            return f"static void {name}(sl_task *t)", "{\n    " + body + "\n}"
        run = self.helper("taskrun", r, make)
        size = "0" if r in (VOID, NEVER) else f"sizeof({self.ctype(r)})"
        return f"sl_task_new({self.value(f)}, {size}, {run})"

    def bi_task_join(self, e):
        return f"{self.task_join_fn(e.args[0].ty.ret)}({self.value(e.args[0])})"

    def bi_task_done(self, e):
        return f"sl_task_done({self.value(e.args[0])})"

    def bi_cpu_count(self, e):
        return "sl_cpu_count()"

    def bi_join_all(self, e):
        r = e.args[0].ty.elem.ret
        j = self.task_join_fn(r)

        def make(name):
            if r in (VOID, NEVER):
                return (f"static void {name}(sl_list ts)",
                        f"{{\n    for (int64_t i = 0; i < ts.n; i++) {j}(((sl_task **)ts.p)[i]);\n}}")
            c = self.ctype(r)
            return (f"static sl_list {name}(sl_list ts)",
                    f"{{\n    sl_list r = {{0}};\n    if (ts.n) sl_list_grow_to(&r, ts.n, sizeof({c}));\n"
                    f"    for (int64_t i = 0; i < ts.n; i++) (({c} *)r.p)[i] = {j}(((sl_task **)ts.p)[i]);\n"
                    f"    r.n = ts.n;\n    return r;\n}}")
        return f"{self.helper('joinall', r, make)}({self.value(e.args[0])})"

    # ---- output ----
    def print_code(self, e, stream):
        pre, body = [], []
        sep = e.sep
        if sep is not None and not (sep.kind == "str"):
            t = self.tmp()
            pre.append(f"sl_str {t} = {self.value(sep)};")
            sep_w = f"sl_w_str({t});"
        else:
            sb = b" " if sep is None else (sep.value if isinstance(sep.value, bytes) else sep.value.encode())
            sep_w = f"sl_w({self.c_str(sb)}, {len(sb)});" if sb else ""
        for i, x in enumerate(e.args):
            v = self.value(x)
            if not (x.kind in LIT_KINDS or (self.pure(x) and self.simple_place(x))):
                t = self.tmp()
                pre.append(f"{self.value_ctype(x.ty)} {t} = {v};")
                v = t
            if i and sep_w:
                body.append(sep_w)
            body.append(self.write_stmt(x.ty, v))
        end = e.end
        if end is not None and end.kind != "str":
            t = self.tmp()
            pre.append(f"sl_str {t} = {self.value(end)};")
            body.append(f"sl_w_str({t});")
        else:
            eb = b"\n" if end is None else (end.value if isinstance(end.value, bytes) else end.value.encode())
            if eb:
                body.append(f"sl_w({self.c_str(eb)}, {len(eb)});")
        b = self.tmp("_sb")
        return self.wrap(pre + [f"sl_sb {b} = sl_sb_begin();"] + body +
                         [f"sl_out({stream}, sl_sb_end({b})); sl_ds.top = {b}.start;"], "(void)0")

    def c_str(self, b):
        from .cg_expr import c_string
        return c_string(b)

    def bi_print(self, e):
        return self.print_code(e, "stdout")

    def bi_eprint(self, e):
        return self.print_code(e, "stderr")

    def bi_str(self, e):
        x = e.args[0]
        if x.ty == STR:
            return self.value(x)
        if x.ty == CHAR:
            return f"sl_char_str({self.value(x)})"
        pre = []
        v = self.value(x)
        if not (x.kind in LIT_KINDS or (self.pure(x) and self.simple_place(x))):
            t = self.tmp()
            pre.append(f"{self.value_ctype(x.ty)} {t} = {v};")
            v = t
        b = self.tmp("_sb")
        return self.wrap(pre + [f"sl_sb {b} = sl_sb_begin();", self.write_stmt(x.ty, v)], f"sl_sb_end({b})")

    # ---- numbers ----
    def bi_len(self, e):
        x = e.args[0]
        if isinstance(x.ty, ArrayTy):
            if self.pure(x):
                return f"((int64_t){x.ty.size})"
            return f"({{ {self.value(x)}; (int64_t){x.ty.size}; }})"
        return f"({self.expr(x)}).n"

    def bi_is_empty(self, e):
        return f"(({self.expr(e.args[0])}).n == 0)"

    def bi_abs(self, e):
        x = e.args[0]
        if is_float(x.ty):
            return f"{'fabsf' if x.ty.name == 'f32' else 'fabs'}({self.value(x)})"
        ct = self.ctype(x.ty)
        t = self.tmp()
        return f"({{ {ct} {t} = {self.value(x)}; {t} < 0 ? ({ct})(0 - {t}) : {t}; }})"

    def minmax(self, e, op):
        t = e.ty
        ct = self.value_ctype(t)
        pre, vals = self.args_seq(e)
        r = self.tmp("_m")
        pre.append(f"{ct} {r} = {vals[0]};")
        for v in vals[1:]:
            x = self.tmp()
            pre.append(f"{ct} {x} = {v};")
            cond = self.compare_code(op, t, x, r)
            if is_float(t):
                # A NaN argument makes the result NaN.
                cond = f"({cond} || {x} != {x})"
            pre.append(f"if ({cond}) {r} = {x};")
        return self.wrap(pre, r)

    def bi_min(self, e):
        return self.minmax(e, "<")

    def bi_max(self, e):
        return self.minmax(e, ">")

    def minmax_list(self, e, op, what):
        pre = []
        p, n = self.seq_view(e.args[0], pre)
        ct = self.ctype(e.ty)
        r, nt = self.tmp("_m"), self.tmp("_n")
        pre.append(f"int64_t {nt} = {n}; if ({nt} == 0) sl_empty(\"{what}()\", {self.loc(e.span)});")
        pre.append(f"{ct} {r} = {p}[0];")
        pre.append(f"for (int64_t _i = 1; _i < {nt}; _i++) if ({p}[_i] {op} {r}) {r} = {p}[_i];")
        return self.wrap(pre, r)

    def bi_min_list(self, e):
        return self.minmax_list(e, "<", "min")

    def bi_max_list(self, e):
        return self.minmax_list(e, ">", "max")

    def bi_sum(self, e):
        pre = []
        p, n = self.seq_view(e.args[0], pre)
        ct = self.ctype(e.ty)
        r, nt = self.tmp("_m"), self.tmp("_n")
        pre.append(f"int64_t {nt} = {n}; {ct} {r} = 0;")
        add = f"{r} += {p}[_i]" if is_float(e.ty) else f"{r} = ({ct})({r} + {p}[_i])"
        pre.append(f"for (int64_t _i = 0; _i < {nt}; _i++) {add};")
        return self.wrap(pre, r)

    def bi_float_sqrt(self, e):
        return self.fcall(e, "sqrt")

    def bi_float_floor(self, e):
        return self.fcall(e, "floor")

    def bi_float_ceil(self, e):
        return self.fcall(e, "ceil")

    def bi_float_abs(self, e):
        return self.fcall(e, "fabs")

    def bi_float_round(self, e):
        return self.fcall(e, "round")

    def bi_float_trunc(self, e):
        return self.fcall(e, "trunc")

    def fcall(self, e, f):
        x = e.args[0]
        return f"{f}{'f' if x.ty.name == 'f32' else ''}({self.value(x)})"

    def bi_float_is_nan(self, e):
        return f"isnan({self.value(e.args[0])})"

    def bi_clone(self, e):
        x = e.args[0]
        if x.ty == STR:
            return f"sl_str_clone({self.value(x)})"
        return self.clone_code(x.ty, self.value(x))

    # ---- chars ----
    def char_pred(self, e, f):
        return f"{f}({self.value(e.args[0])})"

    def bi_char_is_digit(self, e):
        return self.char_pred(e, "sl_char_is_digit")

    def bi_char_is_alpha(self, e):
        return self.char_pred(e, "sl_char_is_alpha")

    def bi_char_is_alnum(self, e):
        return self.char_pred(e, "sl_char_is_alnum")

    def bi_char_is_space(self, e):
        return self.char_pred(e, "sl_char_is_space")

    def bi_char_is_upper(self, e):
        return self.char_pred(e, "sl_char_is_upper")

    def bi_char_is_lower(self, e):
        return self.char_pred(e, "sl_char_is_lower")

    def bi_char_upper(self, e):
        return self.char_pred(e, "sl_char_upper")

    def bi_char_lower(self, e):
        return self.char_pred(e, "sl_char_lower")

    # ---- process & I/O ----
    def bi_panic(self, e):
        loc = self.loc(e.span)
        if e.args:
            return f"sl_panic_str({loc}, {self.value(e.args[0])})"
        return f"sl_panic({loc}, \"explicit panic\")"

    def bi_exit(self, e):
        return f"({{ fflush(stdout); exit((int)({self.value(e.args[0])})); }})"

    def bi_input(self, e):
        s = self.tmp("_in")
        if e.args:
            call = f"sl_input(true, {self.value(e.args[0])}, &{s})"
        else:
            call = f"sl_input(false, (sl_str){{0}}, &{s})"
        return f"({{ sl_str {s}; {call} ? {self.opt_some(e.ty, s)} : {self.opt_none(e.ty)}; }})"

    def bi_read_file(self, e):
        s = self.tmp("_rf")
        return (f"({{ sl_str {s}; sl_read_file({self.value(e.args[0])}, &{s}) ? "
                f"{self.res(e.ty, True, s)} : {self.res(e.ty, False, s)}; }})")

    def bi_write_file(self, e):
        pre, (a, b) = self.args_seq(e)
        return self.wrap(pre, f"sl_write_file({a}, {b})")

    def bi_args(self, e):
        return "sl_args()"

    def bi_clock(self, e):
        return "sl_clock()"

    def bi_take(self, e):
        x = e.args[0]
        ct = self.value_ctype(x.ty)
        p, v = self.tmp("_p"), self.tmp()
        return f"({{ {ct} *{p} = &{self.expr(x)}; {ct} {v} = *{p}; *{p} = ({ct}){{0}}; {v}; }})"

    def bi_swap(self, e):
        a, b = e.args
        ct = self.value_ctype(a.ty)
        p, q, t = self.tmp("_p"), self.tmp("_p"), self.tmp()
        return (f"({{ {ct} *{p} = &{self.expr(a)}; {ct} *{q} = &{self.expr(b)}; "
                f"{ct} {t} = *{p}; *{p} = *{q}; *{q} = {t}; (void)0; }})")

    # ---- maps ----
    def map_ptr(self, recv, pre):
        """A `sl_map *` C expression for recv, hoisted when it is not trivially re-evaluable."""
        if self.simple_place(recv):
            return f"(&{self.expr(recv)})"
        p = self.tmp("_mp")
        if is_place(recv):
            pre.append(f"sl_map *{p} = &{self.expr(recv)};")
        else:
            pre.append(f"sl_map {p}v = {self.value(recv)}; sl_map *{p} = &{p}v;")
        return p

    def map_key(self, t, k, pre):
        kc = self.ctype(t.k)
        if k.kind in LIT_KINDS:
            return self.value(k, kc)
        v = self.tmp("_k")
        pre.append(f"{kc} {v} = {self.value(k, kc)};")
        return v

    def bi_map_len(self, e):
        return f"({self.expr(e.args[0])}).live"

    def bi_map_is_empty(self, e):
        return f"(({self.expr(e.args[0])}).live == 0)"

    def bi_map_contains(self, e):
        recv, k = e.args
        pre = []
        mp = self.map_ptr(recv, pre)
        kv = self.map_key(recv.ty, k, pre)
        return self.wrap(pre, f"({self.map_find_fn(recv.ty)}({mp}, {kv}) >= 0)")

    def bi_map_get(self, e):
        recv, k = e.args
        t = recv.ty
        pre = []
        mp = self.map_ptr(recv, pre)
        kv = self.map_key(t, k, pre)
        i, en = self.tmp("_i"), self.entry_ctype(t)
        pre.append(f"int64_t {i} = {self.map_find_fn(t)}({mp}, {kv});")
        return self.wrap(pre, f"{i} >= 0 ? {self.opt_some(e.ty, f'(({en} *){mp}->p)[{i}].v')} : {self.opt_none(e.ty)}")

    def bi_map_get_or(self, e):
        recv, k, d = e.args
        t = recv.ty
        pre = []
        mp = self.map_ptr(recv, pre)
        kv = self.map_key(t, k, pre)
        i, dv, en = self.tmp("_i"), self.tmp("_d"), self.entry_ctype(t)
        pre.append(f"{self.value_ctype(t.v)} {dv} = {self.value(d)};")
        pre.append(f"int64_t {i} = {self.map_find_fn(t)}({mp}, {kv});")
        return self.wrap(pre, f"{i} >= 0 ? (({en} *){mp}->p)[{i}].v : {dv}")

    def bi_map_insert(self, e):
        recv, k, x = e.args
        t = recv.ty
        vc = self.field_ctype(t.v)
        pre = []
        # Value and key first: they may allocate, which must happen before the
        # map takes its slot (a rehash allocates the new table on top).
        v = self.tmp("_v")
        pre.append(f"{vc} {v} = {self.value(x, vc)};")
        kv = self.map_key(t, k, pre)
        mp = self.map_ptr(recv, pre)
        f, slot, old = self.tmp("_f"), self.tmp("_s"), self.tmp("_o")
        pre.append(f"bool {f}; {vc} *{slot} = {self.map_put_fn(t)}({mp}, {kv}, &{f});")
        pre.append(f"{self.ctype(e.ty)} {old} = {f} ? {self.opt_none(e.ty)} : {self.opt_some(e.ty, f'*{slot}')};")
        pre.append(f"*{slot} = {v};")
        return self.wrap(pre, old)

    def bi_map_remove(self, e):
        recv, k = e.args
        t = recv.ty
        vc = self.field_ctype(t.v)
        pre = []
        kv = self.map_key(t, k, pre)
        mp = self.map_ptr(recv, pre)
        o = self.tmp("_o")
        pre.append(f"{vc} {o};")
        return self.wrap(pre, f"{self.map_del_fn(t)}({mp}, {kv}, &{o}) ? {self.opt_some(e.ty, o)} : {self.opt_none(e.ty)}")

    def bi_map_clear(self, e):
        recv = e.args[0]
        pre = []
        mp = self.map_ptr(recv, pre)
        return self.wrap(pre, f"sl_map_clear({mp}, sizeof({self.entry_ctype(recv.ty)}))")

    def map_list(self, e, part):
        recv = e.args[0]
        t = recv.ty
        en, ec = self.entry_ctype(t), self.ctype(e.ty.elem)
        pre = []
        mp = self.map_ptr(recv, pre)
        r, q, j, es = self.tmp("_l"), self.tmp("_q"), self.tmp("_j"), self.tmp("_e")
        val = {"keys": f"{es}[{q}].k", "values": f"{es}[{q}].v",
               "items": f"({ec}){{{es}[{q}].k, {es}[{q}].v}}"}[part]
        pre += [f"sl_list {r} = sl_list_new({mp}->live, sizeof({ec}));",
                f"{en} *{es} = ({en} *){mp}->p;",
                f"for (int64_t {q} = 0, {j} = 0; {q} < {mp}->n; {q}++) "
                f"if ({es}[{q}].h) (({ec} *){r}.p)[{j}++] = {val};"]
        return self.wrap(pre, r)

    def bi_map_keys(self, e):
        return self.map_list(e, "keys")

    def bi_map_values(self, e):
        return self.map_list(e, "values")

    def bi_map_items(self, e):
        return self.map_list(e, "items")

    # ---- lists ----
    def bi_list_push(self, e):
        recv, x = e.args
        ec = self.ctype(recv.ty.elem)
        v = self.tmp()
        # The value is computed first: it may allocate, after which the list is
        # no longer on top and growing it moves the buffer.
        pre = [f"{ec} {v} = {self.value(x, ec)};"]
        lp = self.list_ptr(recv, pre)
        pre.append(f"sl_list_reserve({lp}, {lp}->n + 1, sizeof({ec}));")
        pre.append(f"(({ec} *){lp}->p)[{lp}->n++] = {v};")
        return self.wrap(pre, "(void)0")

    def bi_list_pop(self, e):
        recv = e.args[0]
        ec = self.ctype(recv.ty.elem)
        pre = []
        lp = self.list_ptr(recv, pre)
        pre.append(f"if ({lp}->n == 0) sl_empty(\"pop()\", {self.loc(e.span)});")
        return self.wrap(pre, f"(({ec} *){lp}->p)[--{lp}->n]")

    def bi_list_insert(self, e):
        recv, i, x = e.args
        ec = self.ctype(recv.ty.elem)
        pre, (iv, xv) = self.eval_seq([i, x], ["int64_t", ec])
        it, v = self.tmp("_i"), self.tmp()
        pre.append(f"int64_t {it} = (int64_t)({iv}); {ec} {v} = {xv};")
        lp = self.list_ptr(recv, pre)
        pre.append(f"if ({it} < 0) {it} += {lp}->n;")
        pre.append(f"sl_list_insert_gap({lp}, {it}, sizeof({ec}), {self.loc(e.span)});")
        pre.append(f"(({ec} *){lp}->p)[{it}] = {v};")
        return self.wrap(pre, "(void)0")

    def bi_list_remove(self, e):
        recv, i = e.args
        ec = self.ctype(recv.ty.elem)
        it, r = self.tmp("_i"), self.tmp("_r")
        pre = [f"int64_t {it} = (int64_t)({self.value(i)});"]
        lp = self.list_ptr(recv, pre)
        pre.append(f"{it} = sl_idx({it}, {lp}->n, {self.loc(e.span)});")
        pre.append(f"{ec} *_e{it} = ({ec} *){lp}->p; {ec} {r} = _e{it}[{it}];")
        pre.append(f"memmove(_e{it} + {it}, _e{it} + {it} + 1, (size_t)({lp}->n - {it} - 1) * sizeof({ec})); {lp}->n--;")
        return self.wrap(pre, r)

    def bi_list_swap(self, e):
        recv, i, j = e.args
        ec = self.ctype(recv.ty.elem)
        pre, (iv, jv) = self.eval_seq([i, j])
        lp = self.list_ptr(recv, pre)
        loc = self.loc(e.span)
        a, b, t = self.tmp("_i"), self.tmp("_i"), self.tmp()
        pre.append(f"int64_t {a} = sl_idx((int64_t)({iv}), {lp}->n, {loc}), {b} = sl_idx((int64_t)({jv}), {lp}->n, {loc});")
        pre.append(f"{ec} *_e{a} = ({ec} *){lp}->p; {ec} {t} = _e{a}[{a}]; _e{a}[{a}] = _e{a}[{b}]; _e{a}[{b}] = {t};")
        return self.wrap(pre, "(void)0")

    def bi_list_truncate(self, e):
        recv, n = e.args
        nt = self.tmp("_n")
        pre = [f"int64_t {nt} = (int64_t)({self.value(n)});"]
        lp = self.list_ptr(recv, pre)
        pre.append(f"if ({nt} < 0) {nt} = 0; if ({nt} < {lp}->n) {lp}->n = {nt};")
        return self.wrap(pre, "(void)0")

    def bi_list_clear(self, e):
        pre = []
        lp = self.list_ptr(e.args[0], pre)
        pre.append(f"{lp}->n = 0;")
        return self.wrap(pre, "(void)0")

    def reverse_code(self, p, n, ec):
        return (f"for (int64_t _i = 0, _j = ({n}) - 1; _i < _j; _i++, _j--) "
                f"{{ {ec} _x = {p}[_i]; {p}[_i] = {p}[_j]; {p}[_j] = _x; }}")

    def bi_list_reverse(self, e):
        recv = e.args[0]
        ec = self.ctype(recv.ty.elem)
        pre = []
        lp = self.list_ptr(recv, pre)
        pre.append(self.reverse_code(f"(({ec} *){lp}->p)", f"{lp}->n", ec))
        return self.wrap(pre, "(void)0")

    def bi_array_reverse(self, e):
        recv = e.args[0]
        ec = self.ctype(recv.ty.elem)
        return self.wrap([self.reverse_code(f"({self.expr(recv)}).a", str(recv.ty.size), ec)], "(void)0")

    def bi_list_sort(self, e):
        recv = e.args[0]
        et = recv.ty.elem
        ec = self.ctype(et)
        f = self.sort_fn(et)
        pre = []
        lp = self.list_ptr(recv, pre)
        pre.append(f"{f}(({ec} *){lp}->p, {lp}->n);")
        return self.wrap(pre, "(void)0")

    def bi_array_sort(self, e):
        recv = e.args[0]
        f = self.sort_fn(recv.ty.elem)
        return self.wrap([f"{f}(({self.expr(recv)}).a, {recv.ty.size});"], "(void)0")

    def bi_list_extend(self, e):
        recv, x = e.args
        ec = self.ctype(recv.ty.elem)
        b = self.tmp("_b")
        pre = [f"sl_list {b} = {self.value(x)};"]
        lp = self.list_ptr(recv, pre)
        pre.append(f"sl_list_reserve({lp}, {lp}->n + {b}.n, sizeof({ec}));")
        pre.append(f"if ({b}.n) memcpy(({ec} *){lp}->p + {lp}->n, {b}.p, (size_t){b}.n * sizeof({ec}));")
        pre.append(f"{lp}->n += {b}.n;")
        return self.wrap(pre, "(void)0")

    def bi_contains(self, e):
        recv, x = e.args
        pre, (c, v) = self.eval_seq([recv, x])
        return self.wrap(pre, self.in_code(x.ty, recv.ty, v, c))

    def bi_index_of(self, e):
        recv, x = e.args
        pre = []
        p, n = self.seq_view(recv, pre)
        ec = self.ctype(recv.ty.elem)
        xv, r = self.tmp(), self.tmp("_r")
        pre.append(f"{ec} {xv} = {self.value(x, ec)};")
        pre.append(f"int64_t {r} = {self.find_fn(recv.ty.elem)}({p}, {n}, {xv});")
        return self.wrap(pre, f"({r} >= 0 ? {self.opt_some(e.ty, r)} : {self.opt_none(e.ty)})")

    def list_opt(self, e, idx):
        pre = []
        p, n = self.seq_view(e.args[0], pre)
        nt = self.tmp("_n")
        pre.append(f"int64_t {nt} = {n};")
        if idx == "get":
            it = self.tmp("_i")
            pre.append(f"int64_t {it} = (int64_t)({self.value(e.args[1])}); if ({it} < 0) {it} += {nt};")
            cond, at = f"{it} >= 0 && {it} < {nt}", it
        else:
            cond, at = f"{nt} > 0", "0" if idx == "first" else f"{nt} - 1"
        return self.wrap(pre, f"(({cond}) ? {self.opt_some(e.ty, f'{p}[{at}]')} : {self.opt_none(e.ty)})")

    def bi_list_get(self, e):
        return self.list_opt(e, "get")

    def bi_list_first(self, e):
        return self.list_opt(e, "first")

    def bi_list_last(self, e):
        return self.list_opt(e, "last")

    # ---- strings ----
    def str2(self, e, f):
        pre, (a, b) = self.args_seq(e)
        return self.wrap(pre, f"{f}({a}, {b})")

    def bi_str_starts_with(self, e):
        return self.str2(e, "sl_str_starts")

    def bi_str_ends_with(self, e):
        return self.str2(e, "sl_str_ends")

    def bi_str_count(self, e):
        return self.str2(e, "sl_str_count")

    def bi_str_find(self, e):
        pre, (a, b) = self.args_seq(e)
        r = self.tmp("_r")
        pre.append(f"int64_t {r} = sl_str_find({a}, {b});")
        return self.wrap(pre, f"({r} >= 0 ? {self.opt_some(e.ty, r)} : {self.opt_none(e.ty)})")

    def bi_str_split(self, e):
        if len(e.args) == 1:
            return f"sl_str_split({self.value(e.args[0])}, (sl_str){{0}}, true)"
        pre, (a, b) = self.args_seq(e)
        return self.wrap(pre, f"sl_str_split({a}, {b}, false)")

    def str1(self, e, f, extra=""):
        return f"{f}({self.value(e.args[0])}{extra})"

    def bi_str_trim(self, e):
        return self.str1(e, "sl_str_trim")

    def bi_str_trim_start(self, e):
        return self.str1(e, "sl_str_trim_start")

    def bi_str_trim_end(self, e):
        return self.str1(e, "sl_str_trim_end")

    def bi_str_upper(self, e):
        return self.str1(e, "sl_str_map_case", ", 1")

    def bi_str_lower(self, e):
        return self.str1(e, "sl_str_map_case", ", 0")

    def bi_str_clone(self, e):
        return self.str1(e, "sl_str_clone")

    def bi_str_chars(self, e):
        return self.str1(e, "sl_str_chars")

    def bi_str_bytes(self, e):
        return self.str1(e, "sl_str_bytes")

    def bi_str_lines(self, e):
        return self.str1(e, "sl_str_lines")

    def bi_str_replace(self, e):
        pre, (s, a, b) = self.args_seq(e)
        return self.wrap(pre, f"sl_str_replace({s}, {a}, {b})")

    def bi_str_join(self, e):
        sep, xs = e.args
        pre, s = [], self.value(sep)
        if not self.pure(xs) and not self.is_const(sep):
            t = self.tmp()
            pre.append(f"sl_str {t} = {s};")
            s = t
        p, n = self.seq_view(xs, pre)
        return self.wrap(pre, f"sl_str_join({s}, {p}, {n})")

    def bi_str_parse_int(self, e):
        r = self.tmp("_r")
        return (f"({{ int64_t {r}; sl_parse_int({self.value(e.args[0])}, &{r}) ? "
                f"{self.opt_some(e.ty, r)} : {self.opt_none(e.ty)}; }})")

    def bi_str_parse_float(self, e):
        r = self.tmp("_r")
        return (f"({{ double {r}; sl_parse_float({self.value(e.args[0])}, &{r}) ? "
                f"{self.opt_some(e.ty, r)} : {self.opt_none(e.ty)}; }})")
