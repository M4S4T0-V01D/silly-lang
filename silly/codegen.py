"""Turns a checked Program into one self-contained GNU C11 translation unit."""

import os

from .types import VOID, NEVER, I64
from .cg_types import TypesMixin
from .cg_expr import ExprMixin, c_string
from .cg_builtins import BuiltinsMixin
from .cg_stmt import StmtMixin, IND

RUNTIME = os.path.join(os.path.dirname(__file__), "runtime", "silly_rt.h")


class CodeGen(TypesMixin, ExprMixin, BuiltinsMixin, StmtMixin):
    def __init__(self, prog):
        self.prog = prog
        self.init_types()
        self.init_expr()
        self.queued = set()
        self.queue = []
        self.fn_protos = []
        self.fn_defs = []
        self.cur = None

    def rel(self, path):
        return path

    def use_fn(self, inst):
        if inst.is_extern or id(inst) in self.queued:
            return
        self.queued.add(id(inst))
        self.queue.append(inst)

    # ---- functions ----
    def signature(self, inst):
        params = ["sl_env *_env"] if getattr(inst, "is_lambda", False) else []
        for v in inst.param_vars:
            ct = self.ctype(v.ty)
            params.append(f"{ct} *{v.cname}" if v.is_ref else f"{ct} {v.cname}")
        decos = {d[0] for d in inst.decl.decorators}
        attrs = "static "
        if "inline" in decos:
            attrs += "inline __attribute__((always_inline)) "
        if "cold" in decos:
            attrs += "__attribute__((cold, noinline)) "
        if inst.ret == NEVER:
            attrs += "__attribute__((noreturn)) "
        return f"{attrs}{self.ctype(inst.ret)} {inst.cname}({', '.join(params) or 'void'})"

    def gen_fn(self, inst):
        self.cur = inst
        sig = self.signature(inst)
        self.fn_protos.append(sig + ";")
        lines = [sig + " {"]
        if not inst.transparent:
            lines.append(IND + "uint8_t *_fb = sl_ds.top;")
        params = {id(v) for v in inst.param_vars}
        for v in inst.locals:
            if id(v) not in params:
                lines.append(IND + f"{self.value_ctype(v.ty)} {v.cname} = {{0}};")
        if getattr(inst, "captures", None):
            env = self.env_type(inst)
            for k, v in enumerate(inst.captures):
                lines.append(IND + f"{v.cname} = (({env} *)_env)->c{k};")
        elif getattr(inst, "is_lambda", False):
            lines.append(IND + "(void)_env;")
        lines += self.block(inst.body, 1)
        if inst.ret == VOID:
            if not inst.transparent:
                lines.append(IND + "SL_RESET(_fb);")
        else:
            lines.append(IND + "__builtin_unreachable();")
        lines.append("}")
        self.fn_defs.append("\n".join(lines))
        self.cur = None

    def drain(self):
        while self.queue:
            self.gen_fn(self.queue.pop(0))

    # ---- program ----
    def generate(self, main, tests=(), test_mode=False):
        if test_mode:
            for t in tests:
                self.use_fn(t)
        else:
            self.use_fn(main)
        self.drain()
        if test_mode:
            entry = self.test_main(tests)
        else:
            call = f"{main.cname}()"
            if main.ret == I64:
                entry = (f"int main(int argc, char **argv) {{\n{IND}sl_init(argc, argv);\n"
                         f"{IND}int64_t r = {call};\n{IND}fflush(stdout);\n{IND}return (int)r;\n}}")
            else:
                entry = (f"int main(int argc, char **argv) {{\n{IND}sl_init(argc, argv);\n"
                         f"{IND}{call};\n{IND}fflush(stdout);\n{IND}return 0;\n}}")
        with open(RUNTIME, encoding="utf-8") as f:
            runtime = f.read()
        link = [fl for _, fls in self.prog.natives.values() for fl in fls]
        parts = [f"/* silly-link: {' '.join(link)} */"] if link else []
        parts.append(runtime)
        if test_mode:
            parts.append("#include <sys/wait.h>")
        natives = [f"/* ---- native: {os.path.basename(p)} ---- */\n{src}" for p, (src, _) in self.prog.natives.items()]
        for section in (self.forward, self.fn_typedefs, self.bodies, natives, self.protos, self.fn_protos,
                        self.helper_defs, self.fn_defs):
            if section:
                parts.append("\n".join(section))
        parts.append(entry)
        return "\n\n".join(parts) + "\n"

    def test_main(self, tests):
        rows = ",\n".join(f"{IND}{{{c_string(t.decl.name.encode())}, {t.cname}}}" for t in tests)
        return f"""static const struct {{ const char *name; void (*fn)(void); }} sl_tests[] = {{
{rows or IND + '{0, 0}'}
}};

int main(int argc, char **argv) {{
    sl_init(argc, argv);
    int n = {len(tests)}, failed = 0;
    const char *only = argc > 1 ? argv[1] : NULL;
    int ran = 0;
    for (int i = 0; i < n; i++) {{
        if (only && !strstr(sl_tests[i].name, only)) continue;
        ran++;
        fflush(stdout);
        fflush(stderr);
        pid_t pid = fork();
        if (pid == 0) {{
            sl_tests[i].fn();
            fflush(stdout);
            _exit(0);
        }}
        int status = 0;
        waitpid(pid, &status, 0);
        if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {{
            printf("test %s ... ok\\n", sl_tests[i].name);
        }} else {{
            printf("test %s ... FAILED\\n", sl_tests[i].name);
            failed++;
        }}
    }}
    printf("\\n%d passed, %d failed\\n", ran - failed, failed);
    return failed ? 1 : 0;
}}"""
