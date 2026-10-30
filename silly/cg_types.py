"""C type mapping and per-type helper functions (eq, cmp, clone, reloc, fmt, find, sort)."""

from .types import (TaskTy, Prim, ListTy, MapTy, ArrayTy, TupleTy, FnTy, RefTy, NamedTy, VOID, NEVER, STR, CHAR, BOOL,
                    is_int, is_float, is_signed, has_list, region_bearing, mangle, int_bits)

INT_C = {"i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
         "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t"}
PRIM_C = dict(INT_C, f64="double", f32="float", bool="bool", char="uint32_t", str="sl_str", void="void",
              never="void")


def is_scalar(t):
    return isinstance(t, Prim) and t.name not in ("str", "void", "never")


class TypesMixin:
    def init_types(self):
        self.forward = []       # typedef struct X X;
        self.fn_typedefs = []   # function-pointer typedefs
        self.bodies = []        # struct definitions in dependency order
        self.protos = []        # helper prototypes
        self.helper_defs = []   # helper bodies
        self.type_state = {}
        self.cnames = {}
        self.helpers = {}
        self.emitted = set()    # types whose struct body is in self.bodies
        self.deferred = []      # (key, body, deps) waiting for a by-value dependency

    # ---- naming ----
    def ctype(self, t):
        if isinstance(t, Prim):
            return PRIM_C[t.name]
        if isinstance(t, ListTy):
            self.ensure_type(t.elem)
            return "sl_list"
        if isinstance(t, MapTy):
            self.entry_ctype(t)
            return "sl_map"
        if isinstance(t, RefTy):
            return self.ctype(t.inner) + " *"
        if isinstance(t, FnTy):
            self.fnptr(t)
            return "sl_fn"
        if isinstance(t, TaskTy):
            return "sl_task *"
        name = self.cnames.get(t)
        if name is None:
            prefix = {TupleTy: "tup_", ArrayTy: "arr_", NamedTy: "t_"}[type(t)]
            name = prefix + mangle(t)
            self.cnames[t] = name
            self.ensure_type(t)
        return name

    def fnptr(self, t):
        """The C type of a function value's code pointer: R (*)(sl_env *, P...)."""
        name = self.cnames.get(t)
        if name is None:
            name = "fnp_" + mangle(t)
            self.cnames[t] = name
            ps = "".join(", " + self.field_ctype(p) for p in t.params)
            self.fn_typedefs.append(f"typedef {self.ctype(t.ret)} (*{name})(sl_env *{ps});")
        return name

    def ensure_type(self, t):
        """Emit the definition of t (and everything it embeds by value)."""
        if isinstance(t, (Prim, RefTy, TaskTy)):
            return
        if isinstance(t, FnTy):
            self.fnptr(t)
            return
        if isinstance(t, ListTy):
            return self.ensure_type(t.elem)
        if isinstance(t, MapTy):
            self.entry_ctype(t)
            return
        if t not in self.cnames:
            self.ctype(t)   # names t, then re-enters here
            return
        state = self.type_state.get(t)
        if state is not None:
            return
        self.type_state[t] = "busy"
        name = self.ctype(t) if t in self.cnames else None
        if name is None:
            return  # ctype() re-entered us and finished the work
        self.forward.append(f"typedef struct {name} {name};")
        lines = []
        deps = []
        if isinstance(t, TupleTy):
            deps = list(t.elems)
            for i, e in enumerate(t.elems):
                lines.append(f"    {self.field_ctype(e)} _{i};")
        elif isinstance(t, ArrayTy):
            deps = [t.elem]
            lines.append(f"    {self.field_ctype(t.elem)} a[{t.size}];")
        else:
            info = t.info
            if info.is_enum:
                lines.append("    int32_t tag;")
                arms = []
                for vi, (_, fs) in enumerate(info.variants):
                    deps += [ft for _, ft in fs]
                    if fs:
                        inner = " ".join(f"{self.field_ctype(ft)} f{k};" for k, (_, ft) in enumerate(fs))
                        arms.append(f"        struct {{ {inner} }} v{vi};")
                if arms:
                    lines.append("    union {")
                    lines += arms
                    lines.append("    } u;")
            else:
                for fname, ft in info.fields:
                    deps.append(ft)
                    lines.append(f"    {self.field_ctype(ft)} f_{fname};")
        if not lines:
            lines.append("    char _unused;")
        self.type_state[t] = "done"
        self.emit_body(t, f"struct {name} {{\n" + "\n".join(lines) + "\n};", deps)

    def entry_ctype(self, t):
        """Struct of one map entry: {u64 h; K k; V v;}."""
        key = ("entry", t)
        name = self.cnames.get(key)
        if name is None:
            name = f"ment_{mangle(t)}"
            self.cnames[key] = name
            kc, vc = self.field_ctype(t.k), self.field_ctype(t.v)
            self.forward.append(f"typedef struct {name} {name};")
            self.emit_body(key, f"struct {name} {{\n    uint64_t h;\n    {kc} k;\n    {vc} v;\n}};", [t.k, t.v])
        return name

    def body_ready(self, t):
        if isinstance(t, (Prim, RefTy, TaskTy, FnTy, ListTy, MapTy)):
            return True
        return t in self.emitted

    def emit_body(self, key, body, deps):
        """Append a struct body once every type it holds by value is defined.
        Recursive types (an enum holding map[str, Self]) would otherwise put
        the inner struct first and C would see an incomplete type."""
        if not all(self.body_ready(d) for d in deps):
            self.deferred.append((key, body, deps))
            return
        self.bodies.append(body)
        self.emitted.add(key)
        progress = True
        while progress:
            progress = False
            for item in list(self.deferred):
                k, b, ds = item
                if all(self.body_ready(d) for d in ds):
                    self.deferred.remove(item)
                    self.bodies.append(b)
                    self.emitted.add(k)
                    progress = True

    def field_ctype(self, t):
        if t in (VOID, NEVER):
            return "char"
        c = self.ctype(t)
        self.ensure_type(t)
        return c

    def value_ctype(self, t):
        """Type usable for a variable (void becomes a dummy char)."""
        return "char" if t in (VOID, NEVER) else self.ctype(t)

    # ---- helper registry ----
    def helper(self, kind, t, make):
        key = (kind, t)
        name = self.helpers.get(key)
        if name is None:
            name = f"{kind}_{mangle(t)}"
            self.helpers[key] = name
            proto, body = make(name)
            self.protos.append(proto + ";")
            self.helper_defs.append(proto + " " + body)
        return name

    # ---- equality ----
    def eq_code(self, t, a, b):
        if is_scalar(t):
            return f"({a} == {b})"
        if t == STR:
            return f"sl_str_eq({a}, {b})"
        if isinstance(t, FnTy):
            return f"sl_fn_eq({a}, {b})"
        if t in (VOID, NEVER):
            return "true"
        return f"{self.eq_fn(t)}({a}, {b})"

    def eq_fn(self, t):
        c = self.ctype(t)

        def make(name):
            proto = f"static bool {name}({c} a, {c} b)"
            body = []
            if isinstance(t, MapTy):
                en, fnd = self.entry_ctype(t), self.map_find_fn(t)
                body.append("if (a.live != b.live) return false;")
                body.append(f"for (int64_t i = 0; i < a.n; i++) {{\n        {en} *e = ({en} *)a.p + i;")
                body.append("    if (!e->h) continue;")
                body.append(f"    int64_t j = {fnd}(&b, e->k);")
                body.append(f"    if (j < 0 || !{self.eq_code(t.v, 'e->v', f'(({en} *)b.p)[j].v')}) return false;\n    }}")
                body.append("return true;")
            elif isinstance(t, ListTy):
                ec = self.ctype(t.elem)
                body.append("if (a.n != b.n) return false;")
                body.append(f"for (int64_t i = 0; i < a.n; i++) if (!{self.eq_code(t.elem, f'(({ec} *)a.p)[i]', f'(({ec} *)b.p)[i]')}) return false;")
                body.append("return true;")
            elif isinstance(t, ArrayTy):
                body.append(f"for (int64_t i = 0; i < {t.size}; i++) if (!{self.eq_code(t.elem, 'a.a[i]', 'b.a[i]')}) return false;")
                body.append("return true;")
            elif isinstance(t, TupleTy):
                parts = [self.eq_code(e, f"a._{i}", f"b._{i}") for i, e in enumerate(t.elems)]
                body.append("return " + (" && ".join(parts) or "true") + ";")
            else:
                info = t.info
                if info.is_enum:
                    body.append("if (a.tag != b.tag) return false;")
                    body.append("switch (a.tag) {")
                    for vi, (_, fs) in enumerate(info.variants):
                        if fs:
                            parts = [self.eq_code(ft, f"a.u.v{vi}.f{k}", f"b.u.v{vi}.f{k}") for k, (_, ft) in enumerate(fs)]
                            body.append(f"case {vi}: return {' && '.join(parts)};")
                    body.append("default: return true;\n}")
                else:
                    parts = [self.eq_code(ft, f"a.f_{fn}", f"b.f_{fn}") for fn, ft in info.fields]
                    body.append("return " + (" && ".join(parts) or "true") + ";")
            return proto, "{\n    " + "\n    ".join(body) + "\n}"
        return self.helper("eq", t, make)

    # ---- ordering ----
    def cmp_code(self, t, a, b):
        """An int < 0, == 0 or > 0."""
        if is_scalar(t):
            return f"sl_cmp3({a}, {b})"
        if t == STR:
            return f"sl_str_cmp({a}, {b})"
        return f"{self.cmp_fn(t)}({a}, {b})"

    def cmp_fn(self, t):
        c = self.ctype(t)

        def make(name):
            proto = f"static int {name}({c} a, {c} b)"
            body = ["int r;"]
            for i, e in enumerate(t.elems):
                body.append(f"if ((r = {self.cmp_code(e, f'a._{i}', f'b._{i}')}) != 0) return r;")
            body.append("return 0;")
            return proto, "{\n    " + "\n    ".join(body) + "\n}"
        return self.helper("cmp", t, make)

    def less_code(self, t, a, b):
        if is_scalar(t):
            return f"({a} < {b})"
        return f"({self.cmp_code(t, a, b)} < 0)"

    # ---- clone ----
    def clone_code(self, t, v):
        if not has_list(t):
            return v
        return f"{self.clone_fn(t)}({v})"

    def clone_fn(self, t):
        c = self.ctype(t)

        def make(name):
            proto = f"static {c} {name}({c} v)"
            body = []
            if isinstance(t, MapTy):
                en = self.entry_ctype(t)
                body.append(f"sl_map r = sl_map_copy(v, sizeof({en}));")
                if has_list(t.k) or has_list(t.v):
                    body.append(f"for (int64_t i = 0; i < r.n; i++) {{\n        {en} *e = ({en} *)r.p + i;")
                    if has_list(t.k):
                        body.append(f"    e->k = {self.clone_code(t.k, 'e->k')};")
                    if has_list(t.v):
                        body.append(f"    e->v = {self.clone_code(t.v, 'e->v')};")
                    body.append("}")
                body.append("return r;")
            elif isinstance(t, ListTy):
                ec = self.ctype(t.elem)
                body.append(f"sl_list r = sl_list_copy(v, sizeof({ec}));")
                if has_list(t.elem):
                    body.append(f"for (int64_t i = 0; i < r.n; i++) (({ec} *)r.p)[i] = {self.clone_code(t.elem, f'(({ec} *)r.p)[i]')};")
                body.append("return r;")
            elif isinstance(t, ArrayTy):
                body.append(f"for (int64_t i = 0; i < {t.size}; i++) v.a[i] = {self.clone_code(t.elem, 'v.a[i]')};")
                body.append("return v;")
            elif isinstance(t, TupleTy):
                for i, e in enumerate(t.elems):
                    if has_list(e):
                        body.append(f"v._{i} = {self.clone_code(e, f'v._{i}')};")
                body.append("return v;")
            else:
                info = t.info
                if info.is_enum:
                    body.append("switch (v.tag) {")
                    for vi, (_, fs) in enumerate(info.variants):
                        stm = [f"v.u.v{vi}.f{k} = {self.clone_code(ft, f'v.u.v{vi}.f{k}')};"
                               for k, (_, ft) in enumerate(fs) if has_list(ft)]
                        if stm:
                            body.append(f"case {vi}: " + " ".join(stm) + " break;")
                    body.append("default: break;\n}")
                else:
                    for fn, ft in info.fields:
                        if has_list(ft):
                            body.append(f"v.f_{fn} = {self.clone_code(ft, f'v.f_{fn}')};")
                body.append("return v;")
            return proto, "{\n    " + "\n    ".join(body) + "\n}"
        return self.helper("clone", t, make)

    # ---- relocation (for @compact) ----
    def reloc_stmt(self, t, ptr):
        """Statement relocating *ptr's storage that lies in [lo, hi)."""
        if not region_bearing(t):
            return ""
        return f"{self.reloc_fn(t)}({ptr}, lo, hi);"

    def reloc_fn(self, t):
        c = self.ctype(t)

        def make(name):
            proto = f"static void {name}({c} *v, const uint8_t *lo, const uint8_t *hi)"
            body = []
            if isinstance(t, FnTy):
                body.append("sl_fn_reloc(v, lo, hi);")
            elif t == STR:
                body.append("if (v->n && sl_in(v->p, (size_t)v->n, lo, hi)) {")
                body.append("    uint8_t *q = (uint8_t *)sl_alloc((size_t)v->n);")
                body.append("    memcpy(q, v->p, (size_t)v->n);")
                body.append("    v->p = q;\n    }")
            elif isinstance(t, MapTy):
                en = self.entry_ctype(t)
                body.append(f"if (v->p && sl_in(v->p, sl_map_bytes(v->cap, sizeof({en})), lo, hi)) {{")
                body.append(f"    *v = sl_map_copy(*v, sizeof({en}));\n    }}")
                inner = [self.reloc_stmt(x, f"&e->{f}") for x, f in ((t.k, "k"), (t.v, "v")) if region_bearing(x)]
                if inner:
                    body.append(f"for (int64_t i = 0; i < v->n; i++) {{\n        {en} *e = ({en} *)v->p + i;")
                    body.append("    if (!e->h) continue;")
                    body.append("    " + " ".join(inner) + "\n    }")
            elif isinstance(t, ListTy):
                ec = self.ctype(t.elem)
                body.append(f"if (v->p && sl_in(v->p, (size_t)v->cap * sizeof({ec}), lo, hi)) {{")
                body.append(f"    *v = sl_list_relocated(*v, sizeof({ec}));\n    }}")
                if region_bearing(t.elem):
                    body.append(f"for (int64_t i = 0; i < v->n; i++) {self.reloc_stmt(t.elem, f'(({ec} *)v->p) + i')}")
            elif isinstance(t, ArrayTy):
                body.append(f"for (int64_t i = 0; i < {t.size}; i++) {self.reloc_stmt(t.elem, '&v->a[i]')}")
            elif isinstance(t, TupleTy):
                for i, e in enumerate(t.elems):
                    if region_bearing(e):
                        body.append(self.reloc_stmt(e, f"&v->_{i}"))
            else:
                info = t.info
                if info.is_enum:
                    body.append("switch (v->tag) {")
                    for vi, (_, fs) in enumerate(info.variants):
                        stm = [self.reloc_stmt(ft, f"&v->u.v{vi}.f{k}") for k, (_, ft) in enumerate(fs)
                               if region_bearing(ft)]
                        if stm:
                            body.append(f"case {vi}: " + " ".join(stm) + " break;")
                    body.append("default: break;\n}")
                else:
                    for fn, ft in info.fields:
                        if region_bearing(ft):
                            body.append(self.reloc_stmt(ft, f"&v->f_{fn}"))
            return proto, "{\n    " + "\n    ".join(body) + "\n}"
        return self.helper("reloc", t, make)

    def compact_fn(self, t):
        """Move everything t owns in [base, top) down to base; the rest of the frame is freed."""
        c = self.ctype(t)

        def make(name):
            r = self.reloc_fn(t)
            proto = f"static void {name}({c} *v, uint8_t *base)"
            body = """{
    uint8_t *hi = sl_ds.top;
    if (hi == base) return;
    sl_swap_arenas();
    uint8_t *xb = sl_ds.top;
    %s(v, base, hi);
    uint8_t *xt = sl_ds.top;
    sl_swap_arenas();
    SL_RESET(base);
    %s(v, xb, xt);
    sl_xs.top = xb;
    sl_str_end = NULL;
}""" % (r, r)
            return proto, body
        return self.helper("compact", t, make)

    # ---- formatting (writes into the open string builder) ----
    def write_stmt(self, t, v, top=True):
        if t == STR:
            return f"sl_w_str({v});" if top else f"sl_w_repr_str({v});"
        if t == CHAR:
            return f"sl_w_char({v});" if top else f"sl_w_repr_char({v});"
        if t == BOOL:
            return f"sl_w_bool({v});"
        if is_int(t):
            return f"sl_w_i64((int64_t){v});" if is_signed(t) else f"sl_w_u64((uint64_t){v});"
        if is_float(t):
            return f"sl_w_f64({v});" if t.name == "f64" else f"sl_w_f32({v});"
        if t in (VOID, NEVER):
            return 'SL_WLIT("()");'
        if isinstance(t, FnTy):
            return f'SL_WLIT("<fn {t}>");'
        return f"{self.write_fn(t)}({v});"

    def write_fn(self, t):
        c = self.ctype(t)

        def lit(s):
            return f'SL_WLIT("{s}");'

        def make(name):
            proto = f"static void {name}({c} v)"
            body = []
            if isinstance(t, MapTy):
                en = self.entry_ctype(t)
                body.append("sl_wc('{'); bool first = true;")
                body.append(f"for (int64_t i = 0; i < v.n; i++) {{\n        {en} *e = ({en} *)v.p + i;")
                body.append("    if (!e->h) continue;")
                body.append("    if (!first) SL_WLIT(\", \");\n        first = false;")
                body.append(f"    {self.write_stmt(t.k, 'e->k', False)} SL_WLIT(\": \");")
                body.append(f"    {self.write_stmt(t.v, 'e->v', False)}\n    }}")
                body.append("sl_wc('}');")
            elif isinstance(t, ListTy):
                ec = self.ctype(t.elem)
                body.append("sl_wc('[');")
                body.append("for (int64_t i = 0; i < v.n; i++) {")
                body.append("    if (i) SL_WLIT(\", \");")
                body.append(f"    {self.write_stmt(t.elem, f'(({ec} *)v.p)[i]', False)}\n    }}")
                body.append("sl_wc(']');")
            elif isinstance(t, ArrayTy):
                body.append("sl_wc('[');")
                body.append(f"for (int64_t i = 0; i < {t.size}; i++) {{")
                body.append("    if (i) SL_WLIT(\", \");")
                body.append(f"    {self.write_stmt(t.elem, 'v.a[i]', False)}\n    }}")
                body.append("sl_wc(']');")
            elif isinstance(t, TupleTy):
                body.append("sl_wc('(');")
                for i, e in enumerate(t.elems):
                    if i:
                        body.append(lit(", "))
                    body.append(self.write_stmt(e, f"v._{i}", False))
                if len(t.elems) == 1:
                    body.append("sl_wc(',');")
                body.append("sl_wc(')');")
            else:
                info = t.info
                tname = t.decl.name
                if info.is_enum:
                    body.append("switch (v.tag) {")
                    for vi, (vn, fs) in enumerate(info.variants):
                        stm = [lit(vn)]
                        if fs:
                            stm.append("sl_wc('(');")
                            for k, (fname, ft) in enumerate(fs):
                                if k:
                                    stm.append(lit(", "))
                                if fname:
                                    stm.append(lit(fname + "="))
                                stm.append(self.write_stmt(ft, f"v.u.v{vi}.f{k}", False))
                            stm.append("sl_wc(')');")
                        body.append(f"case {vi}: " + " ".join(stm) + " break;")
                    body.append("default: break;\n}")
                else:
                    body.append(lit(tname + "("))
                    for i, (fn, ft) in enumerate(info.fields):
                        if i:
                            body.append(lit(", "))
                        body.append(lit(fn + "="))
                        body.append(self.write_stmt(ft, f"v.f_{fn}", False))
                    body.append("sl_wc(')');")
            return proto, "{\n    " + "\n    ".join(body) + "\n}"
        return self.helper("write", t, make)

    # ---- hashing & map operations ----
    def hash_code(self, t, v):
        """A well-mixed u64 hash of v."""
        if t == STR:
            return f"sl_hash_bytes({v}.p, {v}.n)"
        if is_scalar(t):
            return f"sl_mix((uint64_t)({v}))"
        c = self.ctype(t)

        def make(name):
            parts = ["uint64_t h = 0x2545f4914f6cdd1dull;"]
            for i, e in enumerate(t.elems):
                parts.append(f"h = sl_mix(h ^ {self.hash_code(e, f'v._{i}')}) + {i + 1};")
            return f"static uint64_t {name}({c} v)", "{\n    " + "\n    ".join(parts + ["return h;"]) + "\n}"
        return f"{self.helper('hash', t, make)}({v})"

    def map_probe(self, t):
        """Shared prologue: h, idx, mask, s and es for key k in map m."""
        en = self.entry_ctype(t)
        return (f"uint64_t h = {self.hash_code(t.k, 'k')} | SL_LIVE;\n"
                f"    uint32_t *idx = SL_MAP_IDX(m, sizeof({en}));\n"
                f"    uint64_t mask = (uint64_t)m->cap * 2 - 1, s = h & mask;\n"
                f"    {en} *es = ({en} *)m->p;\n"
                f"    uint32_t j;\n"
                f"    while ((j = idx[s]) != 0) {{\n"
                f"        if (es[j - 1].h == h && {self.eq_code(t.k, 'es[j - 1].k', 'k')}) %s\n"
                f"        s = (s + 1) & mask;\n    }}")

    def map_find_fn(self, t):
        """int64_t find(const sl_map *m, K k): entry number of k or -1."""
        kc = self.ctype(t.k)

        def make(name):
            proto = f"static int64_t {name}(const sl_map *m, {kc} k)"
            return proto, ("{\n    if (!m->cap) return -1;\n    " + self.map_probe(t) % "return (int64_t)(j - 1);"
                           + "\n    return -1;\n}")
        return self.helper("mfind", t, make)

    def map_put_fn(self, t):
        """V *put(sl_map *m, K k): the value slot for k, inserting an entry when k is new."""
        kc, vc, en = self.ctype(t.k), self.field_ctype(t.v), self.entry_ctype(t)

        def make(name):
            proto = f"static {vc} *{name}(sl_map *m, {kc} k, bool *fresh)"
            body = f"""{{
    if (m->n == m->cap) {{
        if (m->cap) {{
            int64_t i = {self.map_find_fn(t)}(m, k);
            if (i >= 0) {{ *fresh = false; return &(({en} *)m->p)[i].v; }}
        }}
        sl_map_room(m, sizeof({en}));
    }}
    {self.map_probe(t) % "{ *fresh = false; return &es[j - 1].v; }"}
    {en} *e = &es[m->n];
    e->h = h;
    e->k = k;
    idx[s] = (uint32_t)(++m->n);
    m->live++;
    *fresh = true;
    return &e->v;
}}"""
            return proto, body
        return self.helper("mput", t, make)

    def map_at_fn(self, t):
        """V *at(sl_map *m, K k, loc): the value slot for k; panics when k is missing."""
        kc, vc, en = self.ctype(t.k), self.field_ctype(t.v), self.entry_ctype(t)

        def make(name):
            proto = f"static {vc} *{name}(const sl_map *m, {kc} k, const char *loc)"
            body = (f"{{\n    int64_t i = {self.map_find_fn(t)}(m, k);\n"
                    f"    if (SL_UNLIKELY(i < 0)) sl_no_key(loc);\n"
                    f"    return &(({en} *)m->p)[i].v;\n}}")
            return proto, body
        return self.helper("mat", t, make)

    def map_del_fn(self, t):
        """bool del(sl_map *m, K k, V *out): remove k, storing its value in *out (if non-null)."""
        kc, vc, en = self.ctype(t.k), self.field_ctype(t.v), self.entry_ctype(t)

        def make(name):
            proto = f"static bool {name}(sl_map *m, {kc} k, {vc} *out)"
            body = (f"{{\n    int64_t i = {self.map_find_fn(t)}(m, k);\n"
                    f"    if (i < 0) return false;\n"
                    f"    {en} *e = ({en} *)m->p + i;\n"
                    f"    if (out) *out = e->v;\n"
                    f"    e->h = 0;\n    m->live--;\n"
                    f"    if (i == m->n - 1 && !m->live) sl_map_clear(m, sizeof({en}));\n"
                    f"    return true;\n}}")
            return proto, body
        return self.helper("mdel", t, make)

    # ---- search & sort ----
    def find_fn(self, et):
        """int64_t find(const E *p, int64_t n, E x): first index of x or -1."""
        ec = self.ctype(et)

        def make(name):
            proto = f"static int64_t {name}(const {ec} *p, int64_t n, {ec} x)"
            body = f"{{\n    for (int64_t i = 0; i < n; i++) if ({self.eq_code(et, 'p[i]', 'x')}) return i;\n    return -1;\n}}"
            return proto, body
        return self.helper("find", et, make)

    def sort_fn(self, et):
        ec = self.ctype(et)
        key = ("sort", et)
        name = self.helpers.get(key)
        if name is None:
            name = f"sort_{mangle(et)}"
            self.helpers[key] = name
            if is_scalar(et):
                self.helper_defs.append(f"SL_DEF_QSORT({name}, {ec})")
            else:
                lt = f"lt_{mangle(et)}"
                self.helper_defs.append(f"#define {lt}(x, y) {self.less_code(et, '(*(x))', '(*(y))')}\n"
                                        f"SL_DEF_SORT({name}, {ec}, {lt})")
        return name

    def int_bits_of(self, t):
        return int_bits(t)
