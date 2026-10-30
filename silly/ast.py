"""Syntax tree produced by the parser. Nodes are plain classes with a span."""


class Node:
    _fields = ()

    def __init__(self, *args, span=None):
        for name, value in zip(self._fields, args):
            setattr(self, name, value)
        self.span = span

    def __repr__(self):
        inner = ", ".join(f"{f}={getattr(self, f)!r}" for f in self._fields)
        return f"{type(self).__name__}({inner})"


def node(name, *fields):
    return type(name, (Node,), {"_fields": fields})


# ---- type expressions ----
TName = node("TName", "name", "args")          # int, list[T], mod.Type
TTuple = node("TTuple", "elems")
TArray = node("TArray", "elem", "size")        # [T; N]
TFn = node("TFn", "params", "ret")
TRef = node("TRef", "mut", "inner")            # only legal in parameter position

# ---- expressions ----
IntLit = node("IntLit", "value", "suffix")
FloatLit = node("FloatLit", "value", "suffix")
StrLit = node("StrLit", "value")
FStr = node("FStr", "parts")                   # list of str | (Expr, spec)
CharLit = node("CharLit", "value")
BoolLit = node("BoolLit", "value")
Name = node("Name", "name")
Field = node("Field", "base", "name")
Index = node("Index", "base", "indices")
Slice = node("Slice", "base", "lo", "hi")
Call = node("Call", "func", "args")            # args: list of Arg
Arg = node("Arg", "name", "value")
Unary = node("Unary", "op", "expr")
Ref = node("Ref", "mut", "expr")
Binary = node("Binary", "op", "left", "right")
Compare = node("Compare", "ops", "operands")
Ternary = node("Ternary", "cond", "then", "other")
Cast = node("Cast", "expr", "type")
ListLit = node("ListLit", "elems")
MapLit = node("MapLit", "pairs")              # list of (key, value)
ArrayRepeat = node("ArrayRepeat", "elem", "count")
TupleLit = node("TupleLit", "elems")
Try = node("Try", "expr")
Range = node("Range", "lo", "hi", "inclusive")
Is = node("Is", "expr", "pattern")
Lambda = node("Lambda", "params", "ret", "body", "is_expr")   # params: Param with type None when inferred
Checked = node("Checked", "ir")                # an already-checked expression (compiler-internal)

# ---- patterns ----
PWild = node("PWild")
PBind = node("PBind", "name", "mut")
PLit = node("PLit", "expr")
PRange = node("PRange", "lo", "hi", "inclusive")
PVariant = node("PVariant", "path", "subs")    # path: list of names; subs: list or None
PTuple = node("PTuple", "subs")
POr = node("POr", "alts")

# ---- statements ----
Let = node("Let", "mutable", "pattern", "type", "value")
Assign = node("Assign", "target", "op", "value")
ExprStmt = node("ExprStmt", "expr")
If = node("If", "branches", "orelse")          # branches: list of (cond, body)
While = node("While", "cond", "body")
Loop = node("Loop", "body")
For = node("For", "pattern", "iterable", "body")
Break = node("Break")
Continue = node("Continue")
Return = node("Return", "value")
Match = node("Match", "subject", "arms")
Arm = node("Arm", "pattern", "guard", "body")
Pass = node("Pass")
Assert = node("Assert", "cond", "msg")

# ---- declarations ----
Param = node("Param", "name", "type")
FnDecl = node("FnDecl", "name", "tparams", "params", "ret", "body", "decorators", "self_mode", "is_extern")
StructDecl = node("StructDecl", "name", "tparams", "fields", "methods", "decorators")
EnumDecl = node("EnumDecl", "name", "tparams", "variants", "methods", "decorators")
Variant = node("Variant", "name", "fields")    # fields: list of (name | None, TypeExpr)
TraitDecl = node("TraitDecl", "name", "supers", "methods", "decorators")   # supers: list of (name, span)
ImplDecl = node("ImplDecl", "trait", "type", "methods", "decorators")       # trait: (name, span)
ConstDecl = node("ConstDecl", "name", "type", "value")
Import = node("Import", "module", "names", "alias")
Native = node("Native", "file", "link")     # extern "file.c" [link "-lfoo"]
Module = node("Module", "name", "items", "file")
