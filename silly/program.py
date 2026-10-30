"""Whole-program state: module loading, name tables and generic instantiation."""

import os

from . import ast as A
from .errors import SillyError
from .parser import parse
from .traits import PrimDecl, TraitsMixin
from .types import (TaskTy, ALIASES, FLOAT_TYPES, INT_TYPES, VOID, ArrayTy, FnTy, ListTy, MapTy, NamedTy, is_hashable, Prim,
                    RefTy, TParam, TupleTy, has_list, is_copy, region_bearing)

STD_DIR = os.path.join(os.path.dirname(__file__), "std")


class ModuleInfo:
    def __init__(self, ast, name, path):
        self.ast = ast
        self.name = name
        self.path = path
        self.scope = {}     # name -> (kind, payload, ModuleInfo)
        self.cprefix = "m_" + "".join(c if c.isalnum() else "_" for c in name)
        self.native = False     # has an `extern "file.c"`


class StructInfo:
    def __init__(self, decl, args, ty, env, module):
        self.decl = decl
        self.args = args
        self.ty = ty
        self.env = env
        self.module = module
        self.fields = []
        self.field_index = {}
        self.methods = {m.name: m for m in decl.methods}
        self.is_enum = False
        self.props_done = False
        self.props_busy = False
        self.cname = ""


class EnumInfo(StructInfo):
    def __init__(self, *a):
        super().__init__(*a)
        self.is_enum = True
        self.variants = []      # list of (name, [(fname | None, Ty)])
        self.vindex = {}


class FnInst:
    def __init__(self, decl, owner, targs, env, module):
        self.decl = decl
        self.owner = owner          # StructInfo/EnumInfo for methods, else None
        self.targs = targs
        self.env = env
        self.module = module
        self.params = []            # list of (name, Ty) ; RefTy for by-reference
        self.self_ty = None         # RefTy for methods taking self
        self.ret = VOID
        self.body = None
        self.locals = []
        self.cname = ""
        self.transparent = False
        self.compact = False
        self.self_by_value = False
        self.param_vars = []
        self.is_extern = decl.is_extern
        self.extern_name = decl.name
        self.done = False

    @property
    def fn_ty(self):
        return FnTy([p for _, p in self.params], self.ret)

    def describe(self):
        n = self.decl.name
        if self.owner:
            n = f"{self.owner.ty}.{n}"
        if self.targs:
            n += "[" + ", ".join(map(str, self.targs)) + "]"
        return n


class Program(TraitsMixin):
    def __init__(self, main_path, extra_paths=(), packages=None):
        self.sources = {}
        self.packages = packages or {}   # package name -> its src/ directory
        self.modules = {}
        self.named = {}          # (id(decl), args) -> NamedTy
        self.type_order = []     # NamedTy in creation order
        self.fn_insts = {}
        self.fn_order = []
        self.worklist = []
        self.consts = {}
        self.tparam_uid = 0
        self.decl_mod = {}
        self.natives = {}        # path of an `extern "file.c"` -> (C source, linker flags)
        self.init_traits()
        self.search = [os.path.dirname(os.path.abspath(main_path))] + list(extra_paths) + [STD_DIR]
        self.prelude = self.load_module("prelude", os.path.join(STD_DIR, "prelude.silly"), is_prelude=True)
        self.main = self.load_module("main", main_path)

    # ---- loading ----
    def load_module(self, name, path, is_prelude=False):
        key = os.path.abspath(path)
        if key in self.modules:
            return self.modules[key]
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            raise SillyError(f"cannot read {path}: {e.strerror}")
        rel = os.path.relpath(path) if not path.startswith(STD_DIR) else "<std>/" + os.path.relpath(path, STD_DIR)
        self.sources[rel] = text
        ast = parse(text, rel, name)
        mod = ModuleInfo(ast, name, key)
        self.modules[key] = mod
        if not is_prelude:
            for k, v in self.prelude.scope.items():
                if not k.startswith("_"):
                    mod.scope[k] = v
        self.declare(mod)
        return mod

    def find_module(self, dotted, span):
        rel = dotted.replace(".", os.sep) + ".silly"
        head, _, rest = dotted.partition(".")
        if dotted.startswith("std."):
            cands = [os.path.join(STD_DIR, dotted[4:].replace(".", os.sep) + ".silly")]
        elif head in self.packages:
            # `import pkg` is the package's src/lib.silly; `import pkg.a.b` is src/a/b.silly.
            cands = [os.path.join(self.packages[head], (rest or "lib").replace(".", os.sep) + ".silly")]
        else:
            cands = [os.path.join(d, rel) for d in self.search]
        for c in cands:
            if os.path.exists(c):
                return self.load_module(dotted, c)
        raise SillyError(f"module '{dotted}' not found", span,
                         hint="searched: " + ", ".join(os.path.relpath(c) for c in cands))

    def declare(self, mod):
        scope = mod.scope
        local = set()

        def define(name, entry, span):
            if name in local:
                raise SillyError(f"'{name}' is defined twice in this module", span)
            local.add(name)
            scope[name] = entry

        for item in mod.ast.items:
            self.decl_mod[id(item)] = mod
            if isinstance(item, A.FnDecl):
                define(item.name, ("fn", item, mod), item.span)
            elif isinstance(item, A.StructDecl):
                define(item.name, ("struct", item, mod), item.span)
            elif isinstance(item, A.EnumDecl):
                define(item.name, ("enum", item, mod), item.span)
                if any(d[0] == "export_variants" for d in item.decorators):
                    for i, v in enumerate(item.variants):
                        define(v.name, ("variant", (item, i), mod), v.span)
            elif isinstance(item, A.ConstDecl):
                define(item.name, ("const", item, mod), item.span)
            elif isinstance(item, A.TraitDecl):
                define(item.name, ("trait", item, mod), item.span)
                self.declare_trait(item, mod)
            elif isinstance(item, A.ImplDecl):
                self.pending_impls.append((item, mod))
        for item in mod.ast.items:
            if isinstance(item, A.Native):
                mod.native = True
                path =os.path.join(os.path.dirname(mod.path), item.file)
                if path not in self.natives:
                    try:
                        with open(path, encoding="utf-8") as f:
                            self.natives[path] = (f.read(), item.link.split())
                    except OSError as e:
                        raise SillyError(f"cannot read native source {item.file}: {e.strerror}", item.span)
            elif isinstance(item, A.Import):
                sub = self.find_module(item.module, item.span)
                if item.names is None:
                    alias = item.alias or item.module.split(".")[-1]
                    define(alias, ("module", sub, mod), item.span)
                else:
                    for n in item.names:
                        if n not in sub.scope:
                            raise SillyError(f"module '{item.module}' has no item '{n}'", item.span)
                        define(n, sub.scope[n], item.span)

    # ---- type resolution ----
    def fresh_tparam(self, name):
        self.tparam_uid += 1
        return TParam(name, self.tparam_uid)

    def resolve_type(self, t, env, mod, allow_ref=False):
        if isinstance(t, A.TRef):
            if not allow_ref:
                raise SillyError("reference types are only allowed for parameters", t.span)
            inner = self.resolve_type(t.inner, env, mod)
            if isinstance(inner, RefTy):
                raise SillyError("references to references are not allowed", t.span)
            return RefTy(t.mut, inner)
        if isinstance(t, A.TTuple):
            if not t.elems:
                return VOID
            return TupleTy([self.resolve_type(e, env, mod) for e in t.elems])
        if isinstance(t, A.TArray):
            size = self.const_int(t.size, mod)
            if size <= 0:
                raise SillyError("array size must be positive", t.span)
            return ArrayTy(self.resolve_type(t.elem, env, mod), size)
        if isinstance(t, A.TFn):
            ret = self.resolve_type(t.ret, env, mod) if t.ret else VOID
            return FnTy([self.resolve_type(p, env, mod) for p in t.params], ret)
        name = t.name
        args = [self.resolve_type(a, env, mod) for a in t.args]
        if "." not in name:
            if name in env:
                if args:
                    raise SillyError(f"type parameter '{name}' takes no arguments", t.span)
                return env[name]
            prim = ALIASES.get(name, name)
            if prim in INT_TYPES or prim in FLOAT_TYPES or prim in ("bool", "char", "str"):
                if args:
                    raise SillyError(f"'{name}' takes no type arguments", t.span)
                return Prim(prim)
            if name == "list":
                if len(args) != 1:
                    raise SillyError("list takes exactly one type argument: list[T]", t.span)
                return ListTy(args[0])
            if name == "map":
                if len(args) != 2:
                    raise SillyError("map takes two type arguments: map[K, V]", t.span)
                if not is_hashable(args[0]) and not _has_tparam(args[0]):
                    raise SillyError(f"'{args[0]}' cannot be a map key", t.span,
                                     hint="map keys must be integers, char, bool, str or tuples of those")
                return MapTy(args[0], args[1])
            if name == "Task" and "Task" not in mod.scope:
                if len(args) != 1:
                    raise SillyError("Task takes exactly one type argument: Task[T]", t.span)
                return TaskTy(args[0])
        entry = self.lookup_path(name, mod, t.span)
        if entry[0] not in ("struct", "enum"):
            raise SillyError(f"'{name}' is a trait, not a type" if entry[0] == "trait" else f"'{name}' is not a type",
                             t.span, hint="take a type parameter bounded by it: fn f[T: Name](x: T)"
                             if entry[0] == "trait" else None)
        decl = entry[1]
        if len(args) != len(decl.tparams):
            raise SillyError(f"'{name}' expects {len(decl.tparams)} type argument(s), got {len(args)}", t.span)
        return self.named_ty(decl, args, entry[2], t.span)

    def lookup_path(self, name, mod, span):
        parts = name.split(".")
        entry = mod.scope.get(parts[0])
        if entry is None:
            raise SillyError(f"unknown name '{parts[0]}'", span)
        for p in parts[1:]:
            if entry[0] != "module":
                raise SillyError(f"'{p}' cannot be looked up in a {entry[0]}", span)
            sub = entry[1]
            entry = sub.scope.get(p)
            if entry is None or entry[2] is not sub:
                raise SillyError(f"module '{sub.name}' has no item '{p}'", span)
        return entry

    def const_int(self, e, mod):
        if isinstance(e, A.IntLit):
            return e.value
        if isinstance(e, A.Name):
            entry = mod.scope.get(e.name)
            if entry and entry[0] == "const":
                return self.const_int(entry[1].value, entry[2])
        if isinstance(e, A.Binary) and e.op in ("+", "-", "*", "//", "/", "<<"):
            a, b = self.const_int(e.left, mod), self.const_int(e.right, mod)
            return {"+": a + b, "-": a - b, "*": a * b, "//": a // max(b, 1), "/": a // max(b, 1), "<<": a << b}[e.op]
        raise SillyError("expected a compile-time integer constant", e.span)

    def named_ty(self, decl, args, mod, span=None):
        args = tuple(args)
        if any(isinstance(a, TParam) or _has_tparam(a) for a in args):
            return NamedTy(decl, args, None)
        key = (id(decl), args)
        if key in self.named:
            return self.named[key]
        self.check_bounds(decl, args, mod, span or decl.span, f"type '{decl.name}'")
        ty = NamedTy(decl, args)
        env = dict(zip(decl.tparams, args))
        info = (EnumInfo if isinstance(decl, A.EnumDecl) else StructInfo)(decl, args, ty, env, mod)
        info.cname = f"{mod.cprefix}_{decl.name}"
        ty.info = info
        self.named[key] = ty
        self.type_order.append(ty)
        if isinstance(decl, A.StructDecl):
            seen = set()
            for fname, fty, fsp in decl.fields:
                if fname in seen:
                    raise SillyError(f"duplicate field '{fname}'", fsp)
                seen.add(fname)
                info.field_index[fname] = len(info.fields)
                info.fields.append((fname, self.resolve_type(fty, env, mod)))
        else:
            for v in decl.variants:
                if v.name in info.vindex:
                    raise SillyError(f"duplicate variant '{v.name}'", v.span)
                info.vindex[v.name] = len(info.variants)
                info.variants.append((v.name, [(fn, self.resolve_type(ft, env, mod)) for fn, ft in v.fields]))
        self.compute_props(info, span or decl.span)
        return ty

    def compute_props(self, info, span):
        if info.props_done:
            return
        if info.props_busy:
            raise SillyError(f"type '{info.ty}' contains itself by value and would have infinite size", span,
                             hint="store recursive children in a list[...] instead")
        info.props_busy = True
        comps = [t for _, t in info.fields] if not info.is_enum else [t for _, fs in info.variants for _, t in fs]

        def visit(t):
            if isinstance(t, NamedTy):
                self.compute_props(t.info, span)
            elif isinstance(t, TupleTy):
                for e in t.elems:
                    visit(e)
            elif isinstance(t, ArrayTy):
                visit(t.elem)

        for c in comps:
            visit(c)
        info.is_copy = all(is_copy(c) for c in comps)
        info.region = any(region_bearing(c) for c in comps)
        info.has_list = any(has_list(c) for c in comps)
        info.props_busy = False
        info.props_done = True

    def subst(self, t, binds):
        """Replace TParams using a binding dict, instantiating named types."""
        if isinstance(t, TParam):
            return binds.get(t, t)
        if isinstance(t, ListTy):
            return ListTy(self.subst(t.elem, binds))
        if isinstance(t, MapTy):
            return MapTy(self.subst(t.k, binds), self.subst(t.v, binds))
        if isinstance(t, ArrayTy):
            return ArrayTy(self.subst(t.elem, binds), t.size)
        if isinstance(t, TupleTy):
            return TupleTy([self.subst(e, binds) for e in t.elems])
        if isinstance(t, FnTy):
            return FnTy([self.subst(e, binds) for e in t.params], self.subst(t.ret, binds))
        if isinstance(t, RefTy):
            return RefTy(t.mut, self.subst(t.inner, binds))
        if isinstance(t, TaskTy):
            return TaskTy(self.subst(t.ret, binds))
        if isinstance(t, NamedTy):
            args = [self.subst(a, binds) for a in t.args]
            mod = self.decl_module(t.decl)
            return self.named_ty(t.decl, args, mod)
        return t

    def decl_module(self, decl):
        return self.decl_mod[id(decl)]

    # ---- functions ----
    def fn_inst(self, decl, owner, targs, mod, span=None):
        key = (id(decl), owner.ty if owner else None, tuple(targs))
        if key in self.fn_insts:
            return self.fn_insts[key]
        env = dict(owner.env) if owner else {}
        if owner:
            env["Self"] = owner.ty
        env.update(zip(decl.tparams, targs))
        inst = FnInst(decl, owner, tuple(targs), env, mod)
        base = f"{mod.cprefix}_{owner.decl.name}_{decl.name}" if owner else f"{mod.cprefix}_{decl.name}"
        if owner and owner.args or targs or getattr(decl, "trait_method", False):
            base += f"_{len(self.fn_order)}"
        inst.cname = base
        self.fn_insts[key] = inst
        self.fn_order.append(inst)
        decos = {d[0] for d in decl.decorators}
        if owner and decl.self_mode:
            if "consuming" in decos:
                # @consuming methods take self by value: the receiver is moved into the call.
                inst.self_ty = owner.ty
                inst.self_by_value = True
            else:
                inst.self_ty = RefTy(decl.self_mode == "mut", owner.ty)
        for p in decl.params:
            pt = self.resolve_type(p.type, env, mod, allow_ref=True)
            if isinstance(pt, RefTy) and isinstance(pt.inner, FnTy):
                raise SillyError("references to functions are not allowed", p.span)
            inst.params.append((p.name, pt))
        inst.ret = self.resolve_type(decl.ret, env, mod) if decl.ret else VOID
        unknown = decos - {"test", "compact", "inline", "cold", "extern_name", "export_variants", "consuming", "views"}
        if unknown:
            raise SillyError(f"unknown decorator '@{sorted(unknown)[0]}'", decl.span)
        for d in decl.decorators:
            if d[0] == "extern_name":
                if not d[1] or not isinstance(d[1][0], A.StrLit):
                    raise SillyError("@extern_name needs a string argument", d[2])
                inst.extern_name = d[1][0].value
        if decl.is_extern:
            # C sees str as sl_str, &T as T *, and lists as sl_list (see docs/spec.md, "Native code").
            def plain_list(t):
                return isinstance(t, ListTy) and isinstance(t.elem, Prim) and t.elem.name != "str"
            for n, pt in inst.params:
                if not (isinstance(pt, Prim) or
                        isinstance(pt, RefTy) and (isinstance(pt.inner, Prim) or plain_list(pt.inner))):
                    raise SillyError("extern functions may only take primitive values, str, and references "
                                     "to primitives or to lists of them", decl.span)
            if inst.ret != VOID and not (isinstance(inst.ret, Prim) or plain_list(inst.ret)):
                raise SillyError("extern functions may only return primitive values, str, or lists of "
                                 "numeric/bool/char values", decl.span)
            inst.done = True
        mut_region = any(isinstance(pt, RefTy) and pt.mut and region_bearing(pt.inner) for _, pt in inst.params)
        if isinstance(inst.self_ty, RefTy) and inst.self_ty.mut and region_bearing(owner.ty):
            mut_region = True
        inst.compact = "compact" in decos
        if inst.compact and mut_region:
            raise SillyError("@compact functions cannot take `&mut` parameters that own data-stack storage", decl.span)
        # A transparent function hands its whole data-stack frame to the caller
        # instead of releasing it on return (see docs/memory-model.md).
        inst.transparent = mut_region or (region_bearing(inst.ret) and not inst.compact)
        if not decl.is_extern:
            self.worklist.append(inst)
        return inst


def _has_tparam(t):
    from .types import contains_tparam
    return contains_tparam(t)

