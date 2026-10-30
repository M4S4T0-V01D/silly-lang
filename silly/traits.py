"""Traits: named sets of methods that types implement with `impl Trait for Type:`.

Dispatch is static. A generic function bounded by `[T: Show]` is monomorphised
like any other generic, so `x.show()` in its body is a direct call to the
implementing type's method. Bounds are checked where the generic is used, so
an unmet bound is reported at the call site, naming the type and the trait.

Impls may target structs and enums (every instantiation of a generic type at
once: `impl Show for Pair:` puts Pair's own type parameters in scope) and the
primitive types. Four structural traits are built in: Copy, Eq, Ord and Hash.
"""

from . import ast as A
from .errors import SillyError
from .types import ALIASES, FLOAT_TYPES, INT_TYPES, NamedTy, Prim, comparable, is_copy, is_hashable, ordered

BUILTIN_TRAITS = {
    "Copy": is_copy,
    "Eq": comparable,
    "Ord": ordered,
    "Hash": is_hashable,
}


class PrimDecl:
    """Stands in for a struct declaration as the owner of methods implemented for a primitive type."""

    def __init__(self, name):
        self.name = name
        self.tparams = []
        self.methods = []
        self.decorators = []
        self.bounds = {}


class PrimInfo:
    def __init__(self, ty, decl, module):
        self.ty = ty
        self.decl = decl
        self.env = {}
        self.args = ()
        self.module = module
        self.methods = {}
        self.is_enum = False
        self.cname = f"prim_{ty.name}"


class ImplInfo:
    def __init__(self, trait, decl, mod, methods):
        self.trait = trait
        self.decl = decl
        self.mod = mod
        self.methods = methods   # name -> FnDecl (the impl's own, or the trait's default)


def prim_name(name):
    p = ALIASES.get(name, name)
    return p if p in INT_TYPES or p in FLOAT_TYPES or p in ("bool", "char", "str") else None


class TraitsMixin:
    def init_traits(self):
        self.pending_impls = []
        self.impls = {}          # type key -> {id(trait): ImplInfo}
        self.impl_methods = {}   # type key -> {method name: [(FnDecl, ImplInfo)]}
        self.prim_decls = {}
        self.prim_infos = {}

    def declare_trait(self, item, mod):
        seen = set()
        for m in item.methods:
            if m.name in seen:
                raise SillyError(f"trait '{item.name}' declares '{m.name}' twice", m.span)
            seen.add(m.name)
            m.trait_method = True
            self.decl_mod[id(m)] = mod

    # ---- type keys ----
    @staticmethod
    def type_key(ty):
        if isinstance(ty, NamedTy):
            return id(ty.decl)
        if isinstance(ty, Prim):
            return ("prim", ty.name)
        return None

    def prim_decl(self, name):
        if name not in self.prim_decls:
            d = PrimDecl(name)
            d.prim_info = None
            self.prim_decls[name] = d
        return self.prim_decls[name]

    def prim_info(self, ty):
        if ty.name not in self.prim_infos:
            d = self.prim_decl(ty.name)
            d.prim_info = PrimInfo(ty, d, self.prelude)
            self.prim_infos[ty.name] = d.prim_info
        return self.prim_infos[ty.name]

    def lookup_trait(self, name, mod, span):
        """A trait declaration, or the name of a built-in structural trait."""
        if "." not in name and name in BUILTIN_TRAITS and name not in mod.scope:
            return name
        entry = self.lookup_path(name, mod, span)
        if entry[0] != "trait":
            raise SillyError(f"'{name}' is not a trait", span)
        return entry[1]

    # ---- impls ----
    def register_impls(self):
        for item, mod in self.pending_impls:
            self.register_impl(item, mod)
        for key, table in self.impls.items():
            for impl in table.values():
                for sname, ssp in impl.trait.supers:
                    sup = self.lookup_trait(sname, self.decl_module(impl.trait), ssp)
                    if isinstance(sup, str):
                        continue    # structural supertraits are checked with the bounds
                    if id(sup) not in table:
                        tname = self.impl_type_name(impl.decl)
                        raise SillyError(f"'{impl.trait.name}' requires '{sup.name}', which {tname} does not implement",
                                         impl.decl.span, hint=f"add `impl {sup.name} for {tname}:`")

    @staticmethod
    def impl_type_name(item):
        return item.type.name if isinstance(item.type, A.TName) else "this type"

    def impl_target(self, item, mod):
        """(type key, owner declaration) for the type an impl is for."""
        t = item.type
        if not isinstance(t, A.TName):
            raise SillyError("impls are allowed for structs, enums and primitive types", t.span)
        p = prim_name(t.name) if "." not in t.name else None
        if p is not None:
            return ("prim", p), self.prim_decl(p)
        entry = self.lookup_path(t.name, mod, t.span)
        if entry[0] not in ("struct", "enum"):
            raise SillyError(f"impls are allowed for structs, enums and primitive types; '{t.name}' is a {entry[0]}",
                             t.span)
        decl = entry[1]
        if t.args and [getattr(a, "name", None) for a in t.args] != decl.tparams:
            raise SillyError(f"an impl covers every instantiation of '{decl.name}'", t.span,
                             hint=f"write `impl {item.trait[0]} for {decl.name}:`; its type parameters are in scope")
        return id(decl), decl

    def register_impl(self, item, mod):
        tname, tsp = item.trait
        trait = self.lookup_trait(tname, mod, tsp)
        if isinstance(trait, str):
            raise SillyError(f"'{tname}' is a built-in trait; types get it from their structure, not from an impl",
                             tsp)
        key, odecl = self.impl_target(item, mod)
        table = self.impls.setdefault(key, {})
        if id(trait) in table:
            raise SillyError(f"'{odecl.name}' already implements '{trait.name}'", item.span)
        wanted = {m.name: m for m in trait.methods}
        given = {}
        for m in item.methods:
            if m.name in given:
                raise SillyError(f"method '{m.name}' is defined twice in this impl", m.span)
            if m.name not in wanted:
                raise SillyError(f"'{m.name}' is not a method of trait '{trait.name}'", m.span,
                                 hint="methods: " + ", ".join(wanted) if wanted else None)
            self.same_signature(wanted[m.name], m, odecl, trait, mod)
            given[m.name] = m
            m.trait_method = True
            self.decl_mod[id(m)] = mod
        missing = [n for n, m in wanted.items() if m.body is None and n not in given]
        if missing:
            raise SillyError(f"the impl of '{trait.name}' for '{odecl.name}' is missing: {', '.join(missing)}",
                             item.span)
        methods = {n: given.get(n, m) for n, m in wanted.items()}
        impl = ImplInfo(trait, item, mod, methods)
        table[id(trait)] = impl
        inherent = {m.name for m in odecl.methods}
        by_name = self.impl_methods.setdefault(key, {})
        for n, m in methods.items():
            if n not in inherent:
                by_name.setdefault(n, []).append((m, impl))

    def same_signature(self, want, got, odecl, trait, mod):
        where = f"'{got.name}' in the impl of '{trait.name}'"
        if want.self_mode != got.self_mode:
            mode = {None: "no self", "ref": "self", "mut": "mut self"}
            raise SillyError(f"{where} takes {mode[got.self_mode]}, but the trait says {mode[want.self_mode]}",
                             got.span)
        if len(want.params) != len(got.params) or len(want.tparams) != len(got.tparams):
            raise SillyError(f"{where} has a different number of parameters than the trait declares", got.span)
        if {d[0] for d in want.decorators} & {"consuming"} != {d[0] for d in got.decorators} & {"consuming"}:
            raise SillyError(f"{where} must match the trait's @consuming", got.span)
        oenv = {tp: self.fresh_tparam(tp) for tp in odecl.tparams}
        if isinstance(odecl, PrimDecl):
            self_ty = Prim(odecl.name)
        else:
            self_ty = self.named_ty(odecl, [oenv[tp] for tp in odecl.tparams], mod)
        mtps = [self.fresh_tparam(tp) for tp in want.tparams]
        tenv = {"Self": self_ty, **dict(zip(want.tparams, mtps))}
        ienv = {**oenv, "Self": self_ty, **dict(zip(got.tparams, mtps))}
        tmod = self.decl_module(want)
        pairs = [(w.type, g.type, g.span) for w, g in zip(want.params, got.params)]
        pairs.append((want.ret, got.ret, got.span))
        for wt, gt, sp in pairs:
            a = self.resolve_type(wt, tenv, tmod, allow_ref=True) if wt is not None else None
            b = self.resolve_type(gt, ienv, mod, allow_ref=True) if gt is not None else None
            if a != b:
                raise SillyError(f"{where} has type {b or '()'} here, but the trait declares {a or '()'}", sp)

    def find_impl_method(self, ty, name, span):
        """(FnDecl, ImplInfo) for a trait method `name` implemented by ty, or None."""
        key = self.type_key(ty)
        return None if key is None else self.find_by_key(key, name, str(ty), span)

    def find_by_key(self, key, name, label, span):
        cands = self.impl_methods.get(key, {}).get(name, [])
        if len(cands) > 1:
            traits = [impl.trait.name for _, impl in cands]
            raise SillyError(f"'{name}' is ambiguous: {label} gets it from {', '.join(traits)}", span,
                             hint=f"call it through the trait: {traits[0]}.{name}(x, ...)")
        return cands[0] if cands else None

    def check_bounds(self, decl, args, mod, span, what):
        for name, arg in zip(decl.tparams, args):
            for bname, bsp in getattr(decl, "bounds", {}).get(name, []):
                trait = self.lookup_trait(bname, self.decl_mod.get(id(decl), mod), bsp)
                if not self.implements(arg, trait):
                    raise SillyError(f"{arg} does not implement {bname}", span,
                                     hint=f"{what} requires `{name}: {bname}`")

    def implements(self, ty, trait):
        if isinstance(trait, str):
            return BUILTIN_TRAITS[trait](ty)
        key = self.type_key(ty)
        return key is not None and id(trait) in self.impls.get(key, {})
