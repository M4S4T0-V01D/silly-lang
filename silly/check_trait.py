"""Calls to trait methods: `x.show()` through an impl, `Show.show(x)`, and `T.zero()` on a type parameter."""

from .builtins import CHAR_METHODS, FLOAT_METHODS, INT_METHODS, STR_METHODS
from .traits import prim_name
from .types import BOOL, CHAR, STR, NamedTy, Prim, is_float, is_int


def builtin_methods(t):
    if t == STR:
        return STR_METHODS
    if t == CHAR:
        return CHAR_METHODS
    if is_float(t):
        return FLOAT_METHODS
    if is_int(t):
        return INT_METHODS
    if t == BOOL:
        return ["clone"]
    return None


class TraitMixin:
    def owner_of(self, t):
        """(owner declaration, owner type arguments) for calling a method of type t."""
        if isinstance(t, NamedTy):
            return t.decl, list(t.args)
        return self.prog.prim_decl(t.name), []

    def impl_method_call(self, recv, name, e, exp):
        """x.name(...) through a trait impl, or None if no trait gives recv's type that method."""
        t = recv.ty
        if isinstance(t, Prim) and name in (builtin_methods(t) or ()):
            return None
        found = self.prog.find_impl_method(t, name, e.span) if isinstance(t, (NamedTy, Prim)) else None
        if found is None:
            return None
        odecl, oargs = self.owner_of(t)
        return self.call_decl(found[0], odecl, oargs, None, recv, e.args, exp, e.span)

    def trait_call(self, trait, md, e, exp):
        """Trait.method(x, ...): the first argument is the receiver."""
        if md.self_mode is None and not self.has_deco(md, "consuming"):
            self.err(f"'{trait.name}.{md.name}' takes no self; call it on the type: T.{md.name}(...)", e.span)
        if not e.args or e.args[0].name is not None:
            self.err(f"'{trait.name}.{md.name}' needs the receiver as its first argument", e.span)
        recv = self.expr(e.args[0].value, None)
        t = recv.ty
        key = self.prog.type_key(t)
        impl = self.prog.impls.get(key, {}).get(id(trait)) if key is not None else None
        if impl is None:
            self.err(f"{t} does not implement {trait.name}", e.args[0].span)
        odecl, oargs = self.owner_of(t)
        return self.call_decl(impl.methods[md.name], odecl, oargs, None, recv, e.args[1:], exp, e.span)

    def type_entry(self, name):
        """A static entry for a type parameter, `Self` or a primitive type name used as `T.method`."""
        t = self.env.get(name)
        if t is None and prim_name(name):
            t = Prim(prim_name(name))
        if isinstance(t, NamedTy):
            return ("enum" if t.is_enum else "struct", t.decl, self.prog.decl_module(t.decl), list(t.args))
        if isinstance(t, Prim):
            return ("prim", t, self.mod)
        return None

    def type_method_entry(self, decl, name, span):
        """A static entry for an impl method of a struct/enum declaration or a primitive type."""
        if isinstance(decl, Prim):
            key, label, decl = ("prim", decl.name), str(decl), self.prog.prim_decl(decl.name)
        else:
            key, label = id(decl), decl.name
        found = self.prog.find_by_key(key, name, label, span)
        return None if found is None else ("method", (decl, found[0]))
