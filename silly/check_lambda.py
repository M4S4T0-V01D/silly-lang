"""Lambdas: anonymous functions that capture variables of the enclosing function by value.

A lambda is checked by a child FnChecker whose name lookup falls back to the
enclosing checker. The first use of an outer variable creates a *capture*:
a read-only local of the lambda, loaded from its environment when it runs.
Copy values are copied in; anything else is moved in, so the enclosing
function cannot use it afterwards. Inside the lambda a non-Copy capture is a
borrowed view (it can be read but not moved or modified), which is what makes
copies of one closure safe to share an environment.
"""

from . import ast as A
from .ir import E, S, Var
from .program import FnInst
from .types import NEVER, VOID, FnTy, contains_tparam, is_copy, region_bearing


class LambdaDecl:
    """Stands in for an FnDecl so that a lambda is an FnInst like any other function."""

    def __init__(self, params, ret, body, span):
        self.name = "<lambda>"
        self.tparams = []
        self.params = params
        self.ret = ret
        self.body = body
        self.decorators = []
        self.self_mode = None
        self.is_extern = False
        self.span = span


class LambdaMixin:
    parent = None       # the enclosing FnChecker, for a lambda body
    captures = None     # capture Vars in order of first use

    def capture(self, name):
        pv = self.parent.lookup_var(name)
        if pv is None:
            return None
        v = Var(name, pv.ty, borrowed=not is_copy(pv.ty))
        v.captured = True
        v.use_span = None
        self.inst.locals.append(v)
        self.scopes[0][name] = v
        self.captures.append(v)
        return v

    def ex_Checked(self, e, exp):
        return e.ir

    def ex_Lambda(self, e, exp):
        views, self.lambda_views = getattr(self, "lambda_views", None), None
        want = exp if isinstance(exp, FnTy) and len(exp.params) == len(e.params) else None
        names, ptys = [], []
        for i, p in enumerate(e.params):
            if p.name in names:
                self.err(f"duplicate parameter '{p.name}'", p.span)
            if p.type is not None:
                pty = self.ty(p.type)
            elif want is not None and not contains_tparam(want.params[i]):
                pty = want.params[i]
            else:
                self.err(f"cannot infer the type of lambda parameter '{p.name}'", p.span,
                         hint=f"annotate it: `fn({p.name}: Type) => ...`")
            if pty in (VOID, NEVER):
                self.err(f"lambda parameter '{p.name}' cannot have type {pty}", p.span)
            names.append(p.name)
            ptys.append(pty)
        if e.ret is not None:
            ret = self.ty(e.ret)
        elif want is not None and not contains_tparam(want.ret):
            ret = want.ret
        else:
            ret = None if e.is_expr else VOID   # an expression body's type is the result

        self.prog.n_lambdas = getattr(self.prog, "n_lambdas", 0) + 1
        inst = FnInst(LambdaDecl(e.params, e.ret, e.body, e.span), None, [], self.env, self.mod)
        inst.cname = f"lam_{self.prog.n_lambdas}"
        inst.params = list(zip(names, ptys))
        inst.is_lambda = True
        child = type(self)(self.prog, inst)
        child.parent = self
        child.captures = []
        child.lambda_body(e, ret, views)
        inst.captures = child.captures
        inst.transparent = region_bearing(inst.ret)
        inst.done = True

        caps = []
        for v in child.captures:
            span = v.use_span or e.span
            pv = self.lookup_var(v.name)
            if not is_copy(v.ty) and (pv.borrowed or pv.is_ref):
                self.err(f"the lambda captures '{v.name}' by value, but here it is only borrowed", span,
                         hint=f"capture a copy: `let {v.name}2 = {v.name}.clone()` before the lambda")
            caps.append(self.value(A.Name(v.name, span=span), None))
        return E("lambda", FnTy(ptys, inst.ret), e.span, inst=inst, caps=caps)

    def lambda_body(self, e, ret, views=None):
        inst = self.inst
        views = views or [False] * len(e.params)
        inst.param_vars = [self.new_var(name, pty, p.span, borrowed=view and not is_copy(pty))
                           for (name, pty), p, view in zip(inst.params, e.params, views)]
        if not e.is_expr:
            inst.ret = ret
            inst.body = self.block(e.body)
            if not self.diverges and ret not in (VOID, NEVER):
                self.err(f"the lambda can reach its end without returning a {ret}", e.span)
            return
        if ret is None:
            v = self.value(e.body, None)
            ret = VOID if v.ty == NEVER else v.ty
        elif ret == VOID:
            v = self.expr(e.body, None)
        else:
            inst.ret = ret
            v = self.value(e.body, ret)
            self.expect_type(v, ret, e.body.span)
        inst.ret = ret
        inst.body = [S("expr", e.span, e=v)] if ret == VOID else [S("return", e.span, value=v)]
