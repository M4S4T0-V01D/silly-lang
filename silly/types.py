"""Semantic types. Types are immutable and structurally comparable."""

INT_TYPES = {
    "i8": (8, True), "i16": (16, True), "i32": (32, True), "i64": (64, True),
    "u8": (8, False), "u16": (16, False), "u32": (32, False), "u64": (64, False),
}
FLOAT_TYPES = {"f32", "f64"}
ALIASES = {"int": "i64", "float": "f64", "byte": "u8", "usize": "u64", "uint": "u64"}
PRIM_NAMES = set(INT_TYPES) | FLOAT_TYPES | {"bool", "char", "str"}


class Ty:
    __slots__ = ()

    def __eq__(self, other):
        return type(self) is type(other) and self.key() == other.key()

    def __hash__(self):
        return hash((type(self).__name__, self.key()))

    def __repr__(self):
        return str(self)


class Prim(Ty):
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def key(self):
        return self.name

    def __str__(self):
        return "()" if self.name == "void" else self.name


class ListTy(Ty):
    __slots__ = ("elem",)

    def __init__(self, elem):
        self.elem = elem

    def key(self):
        return self.elem

    def __str__(self):
        return f"list[{self.elem}]"


class MapTy(Ty):
    """Insertion-ordered hash map; storage lives on the data stack like a list."""
    __slots__ = ("k", "v")

    def __init__(self, k, v):
        self.k = k
        self.v = v

    def key(self):
        return (self.k, self.v)

    def __str__(self):
        return f"map[{self.k}, {self.v}]"


def is_hashable(t):
    """Types usable as map keys: ints, char, bool, str and tuples of those."""
    if isinstance(t, Prim):
        return t.name in INT_TYPES or t.name in ("char", "bool", "str")
    if isinstance(t, TupleTy):
        return all(is_hashable(e) for e in t.elems)
    return False


class ArrayTy(Ty):
    __slots__ = ("elem", "size")

    def __init__(self, elem, size):
        self.elem = elem
        self.size = size

    def key(self):
        return (self.elem, self.size)

    def __str__(self):
        return f"[{self.elem}; {self.size}]"


class TupleTy(Ty):
    __slots__ = ("elems",)

    def __init__(self, elems):
        self.elems = tuple(elems)

    def key(self):
        return self.elems

    def __str__(self):
        return "(" + ", ".join(map(str, self.elems)) + ("," if len(self.elems) == 1 else "") + ")"


class FnTy(Ty):
    __slots__ = ("params", "ret")

    def __init__(self, params, ret):
        self.params = tuple(params)
        self.ret = ret

    def key(self):
        return (self.params, self.ret)

    def __str__(self):
        r = "" if self.ret == VOID else f" -> {self.ret}"
        return "fn(" + ", ".join(map(str, self.params)) + ")" + r


class TaskTy(Ty):
    """Handle to a running thread that will produce a value of type ret."""
    __slots__ = ("ret",)

    def __init__(self, ret):
        self.ret = ret

    def key(self):
        return self.ret

    def __str__(self):
        return f"Task[{self.ret}]"


class RefTy(Ty):
    """Only appears as a parameter type."""
    __slots__ = ("mut", "inner")

    def __init__(self, mut, inner):
        self.mut = mut
        self.inner = inner

    def key(self):
        return (self.mut, self.inner)

    def __str__(self):
        return ("&mut " if self.mut else "&") + str(self.inner)


class NamedTy(Ty):
    """Instance of a user struct or enum: decl identity plus type arguments."""
    __slots__ = ("decl", "args", "info")

    def __init__(self, decl, args, info=None):
        self.decl = decl
        self.args = tuple(args)
        self.info = info  # filled by the checker (StructInfo / EnumInfo)

    def key(self):
        return (id(self.decl), self.args)

    @property
    def is_enum(self):
        return type(self.decl).__name__ == "EnumDecl"

    def __str__(self):
        if self.args:
            return f"{self.decl.name}[{', '.join(map(str, self.args))}]"
        return self.decl.name


class TParam(Ty):
    """Placeholder for a generic parameter while inferring type arguments."""
    __slots__ = ("name", "uid")

    def __init__(self, name, uid):
        self.name = name
        self.uid = uid

    def key(self):
        return (self.name, self.uid)

    def __str__(self):
        return self.name


VOID = Prim("void")
NEVER = Prim("never")
BOOL = Prim("bool")
CHAR = Prim("char")
STR = Prim("str")
I64 = Prim("i64")
I32 = Prim("i32")
U8 = Prim("u8")
U32 = Prim("u32")
U64 = Prim("u64")
F64 = Prim("f64")
F32 = Prim("f32")


def is_int(t):
    return isinstance(t, Prim) and t.name in INT_TYPES


def is_float(t):
    return isinstance(t, Prim) and t.name in FLOAT_TYPES


def is_numeric(t):
    return is_int(t) or is_float(t)


def is_signed(t):
    return INT_TYPES[t.name][1]


def int_bits(t):
    return INT_TYPES[t.name][0]


def int_range(t):
    bits, signed = INT_TYPES[t.name]
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def ordered(t):
    """Types with <, <= etc.: numbers, char, bool, str and tuples of those."""
    if is_numeric(t) or t in (CHAR, BOOL, STR):
        return True
    if isinstance(t, TupleTy):
        return all(ordered(x) for x in t.elems)
    return False


def comparable(t, seen=None):
    """Types with == and !=. `seen` holds the named types being checked, so
    recursive types (an enum holding a list of itself) terminate."""
    if isinstance(t, (Prim, FnTy)):
        return True
    if isinstance(t, (ListTy, ArrayTy)):
        return comparable(t.elem, seen)
    if isinstance(t, MapTy):
        return comparable(t.v, seen)
    if isinstance(t, TupleTy):
        return all(comparable(x, seen) for x in t.elems)
    if isinstance(t, NamedTy):
        seen = seen or []
        if t in seen:
            return True
        info = t.info
        comps = [x for _, x in info.fields] if not info.is_enum else [x for _, fs in info.variants for _, x in fs]
        return all(comparable(x, seen + [t]) for x in comps)
    return False


def is_copy(t):
    """Copy types are duplicated on assignment; everything else moves."""
    if isinstance(t, Prim) or isinstance(t, FnTy):
        return True
    if isinstance(t, (ListTy, MapTy, TaskTy)):
        return False
    if isinstance(t, ArrayTy):
        return is_copy(t.elem)
    if isinstance(t, TupleTy):
        return all(is_copy(e) for e in t.elems)
    if isinstance(t, NamedTy):
        return t.info.is_copy
    return True


def region_bearing(t):
    """True when values of t may point into the data stack (str or list inside)."""
    if isinstance(t, Prim):
        return t.name == "str"
    if isinstance(t, (ListTy, MapTy)):
        return True
    if isinstance(t, ArrayTy):
        return region_bearing(t.elem)
    if isinstance(t, TupleTy):
        return any(region_bearing(e) for e in t.elems)
    if isinstance(t, NamedTy):
        return t.info.region
    if isinstance(t, FnTy):
        return True     # a closure's environment lives on the data stack
    return False


def has_list(t):
    """True when t owns growable storage (needs deep copy on clone)."""
    if isinstance(t, (ListTy, MapTy)):
        return True
    if isinstance(t, ArrayTy):
        return has_list(t.elem)
    if isinstance(t, TupleTy):
        return any(has_list(e) for e in t.elems)
    if isinstance(t, NamedTy):
        return t.info.has_list
    return False


def has_task(t, seen=None):
    """True when t holds a Task handle anywhere (such values cannot be cloned or printed)."""
    if isinstance(t, TaskTy):
        return True
    if isinstance(t, (ListTy, ArrayTy)):
        return has_task(t.elem, seen)
    if isinstance(t, MapTy):
        return has_task(t.v, seen)
    if isinstance(t, TupleTy):
        return any(has_task(e, seen) for e in t.elems)
    if isinstance(t, NamedTy) and t.info is not None:
        seen = seen or set()
        if t in seen:
            return False
        seen.add(t)
        info = t.info
        comps = [x for _, x in info.fields] if not info.is_enum else [x for _, fs in info.variants for _, x in fs]
        return any(has_task(c, seen) for c in comps)
    return False


def mangle(t):
    if isinstance(t, Prim):
        return t.name
    if isinstance(t, ListTy):
        return f"L{mangle(t.elem)}_"
    if isinstance(t, MapTy):
        return f"H{mangle(t.k)}{mangle(t.v)}_"
    if isinstance(t, ArrayTy):
        return f"A{t.size}{mangle(t.elem)}_"
    if isinstance(t, TupleTy):
        return "T" + "".join(mangle(e) for e in t.elems) + "_"
    if isinstance(t, FnTy):
        return "F" + "".join(mangle(e) for e in t.params) + "R" + mangle(t.ret) + "_"
    if isinstance(t, NamedTy):
        base = t.info.cname if t.info else t.decl.name
        return base + ("G" + "".join(mangle(a) for a in t.args) + "_" if t.args else "")
    if isinstance(t, RefTy):
        return ("M" if t.mut else "R") + mangle(t.inner)
    if isinstance(t, TaskTy):
        return f"K{mangle(t.ret)}_"
    raise TypeError(t)


def contains_tparam(t):
    if isinstance(t, TParam):
        return True
    if isinstance(t, (ListTy, ArrayTy)):
        return contains_tparam(t.elem)
    if isinstance(t, MapTy):
        return contains_tparam(t.k) or contains_tparam(t.v)
    if isinstance(t, TupleTy):
        return any(contains_tparam(e) for e in t.elems)
    if isinstance(t, FnTy):
        return any(contains_tparam(e) for e in t.params) or contains_tparam(t.ret)
    if isinstance(t, NamedTy):
        return any(contains_tparam(a) for a in t.args)
    if isinstance(t, (RefTy, TaskTy)):
        return contains_tparam(t.inner if isinstance(t, RefTy) else t.ret)
    return False


def unify(pattern, actual, binds):
    """Match a type that may contain TParams against a concrete type."""
    if isinstance(pattern, TParam):
        if pattern in binds:
            return binds[pattern] == actual
        binds[pattern] = actual
        return True
    if type(pattern) is not type(actual):
        return False
    if isinstance(pattern, Prim):
        return pattern == actual
    if isinstance(pattern, ListTy):
        return unify(pattern.elem, actual.elem, binds)
    if isinstance(pattern, MapTy):
        return unify(pattern.k, actual.k, binds) and unify(pattern.v, actual.v, binds)
    if isinstance(pattern, ArrayTy):
        return pattern.size == actual.size and unify(pattern.elem, actual.elem, binds)
    if isinstance(pattern, TupleTy):
        return len(pattern.elems) == len(actual.elems) and all(
            unify(p, a, binds) for p, a in zip(pattern.elems, actual.elems))
    if isinstance(pattern, FnTy):
        return len(pattern.params) == len(actual.params) and all(
            unify(p, a, binds) for p, a in zip(pattern.params, actual.params)) and unify(pattern.ret, actual.ret, binds)
    if isinstance(pattern, NamedTy):
        return pattern.decl is actual.decl and all(unify(p, a, binds) for p, a in zip(pattern.args, actual.args))
    if isinstance(pattern, RefTy):
        return pattern.mut == actual.mut and unify(pattern.inner, actual.inner, binds)
    if isinstance(pattern, TaskTy):
        return unify(pattern.ret, actual.ret, binds)
    return False
