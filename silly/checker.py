"""Drives type checking over the whole program until every reachable instance is checked."""

from . import ast as A
from .check_fn import FnChecker
from .errors import SillyError
from .types import I64, VOID, Prim


def instantiate_roots(prog):
    """Every non-generic function and method is checked, even if unused."""
    for mod in list(prog.modules.values()):
        for item in mod.ast.items:
            if isinstance(item, A.FnDecl) and not item.tparams:
                prog.fn_inst(item, None, [], mod, item.span)
            elif isinstance(item, (A.StructDecl, A.EnumDecl)) and not item.tparams:
                info = prog.named_ty(item, [], mod, item.span).info
                for m in item.methods:
                    if not m.tparams:
                        prog.fn_inst(m, info, [], mod, m.span)
    # Impl methods (including inherited defaults) of non-generic types are checked too.
    for key, table in prog.impls.items():
        for impl in table.values():
            if isinstance(key, tuple):
                info = prog.prim_info(Prim(key[1]))
            else:
                odecl = prog.impl_target(impl.decl, impl.mod)[1]
                if odecl.tparams:
                    continue
                info = prog.named_ty(odecl, [], prog.decl_module(odecl), impl.decl.span).info
            for m in impl.methods.values():
                if not m.tparams:
                    prog.fn_inst(m, info, [], prog.decl_module(m), m.span)


def drain(prog):
    while prog.worklist:
        inst = prog.worklist.pop(0)
        if inst.done:
            continue
        try:
            FnChecker(prog, inst).check()
        except SillyError as e:
            if inst.targs or (inst.owner and inst.owner.args):
                e.notes.append(f"in the instantiation {inst.describe()}")
            raise


def check_program(prog, want_main=True):
    prog.register_impls()
    instantiate_roots(prog)
    main = None
    ent = prog.main.scope.get("main")
    if ent is not None and ent[0] == "fn" and ent[2] is prog.main:
        decl = ent[1]
        main = prog.fn_inst(decl, None, [], prog.main, decl.span)
        if decl.params or decl.tparams or main.ret not in (VOID, I64):
            raise SillyError("main() takes no parameters and returns nothing or an int", decl.span,
                             hint="use args() to read command-line arguments")
    elif want_main:
        raise SillyError("no `fn main()` found in the main module", None)
    tests = []
    for item in prog.main.ast.items:
        if isinstance(item, A.FnDecl) and any(d[0] == "test" for d in item.decorators):
            inst = prog.fn_inst(item, None, [], prog.main, item.span)
            if item.params or item.tparams or inst.ret != VOID:
                raise SillyError("@test functions take no parameters and return nothing", item.span)
            tests.append(inst)
    drain(prog)
    return main, tests
