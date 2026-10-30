"""Typed intermediate representation produced by the checker and consumed by codegen.

Every expression node carries `.ty`. Nodes are deliberately loose bags of
attributes keyed by `kind`; codegen dispatches on the kind string.
"""


class E:
    def __init__(self, kind, ty, span=None, **kw):
        self.kind = kind
        self.ty = ty
        self.span = span
        self.__dict__.update(kw)

    def __repr__(self):
        extra = {k: v for k, v in self.__dict__.items() if k not in ("kind", "ty", "span")}
        return f"E.{self.kind}<{self.ty}>{extra}"


class S:
    def __init__(self, kind, span=None, **kw):
        self.kind = kind
        self.span = span
        self.__dict__.update(kw)

    def __repr__(self):
        extra = {k: v for k, v in self.__dict__.items() if k not in ("kind", "span")}
        return f"S.{self.kind}{extra}"


class Var:
    _counter = 0

    def __init__(self, name, ty, mutable=False, is_ref=False, borrowed=False, loop_depth=0):
        Var._counter += 1
        self.id = Var._counter
        self.name = name
        self.cname = f"v_{name}_{self.id}" if name != "self" else f"self_{self.id}"
        self.ty = ty
        self.mutable = mutable
        self.is_ref = is_ref        # parameter passed as a pointer (&T / &mut T / self)
        self.borrowed = borrowed    # shallow view of storage owned elsewhere: no moves, no writes
        self.loop_depth = loop_depth

    def __repr__(self):
        return f"Var({self.name}:{self.ty})"


# Place expressions: kinds that denote storage locations.
PLACE_KINDS = {"local", "field", "index", "tuple_field", "map_index"}


def is_place(e):
    return e.kind in PLACE_KINDS


def root_var(e):
    while e.kind in ("field", "index", "tuple_field", "map_index"):
        e = e.base
    return e.var if e.kind == "local" else None


def place_path(e):
    """Field path from the root, or None if an index is involved."""
    path = []
    while e.kind in ("field", "tuple_field"):
        path.append(e.name if e.kind == "field" else str(e.index))
        e = e.base
    if e.kind != "local":
        return None
    return list(reversed(path))
