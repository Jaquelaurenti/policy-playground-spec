"""Geradores determinísticos de candidatos G1/G2 e ranking com feedback (design §10.3).

Produzem fatos estruturais da política (limiares e linhas de matriz), nunca
estimativas de impacto: todo candidato nasce evidenceLevel=none.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import expr
from .engine import affected_subdag
from .model import PolicyModel

W_STRUCT, W_FB = 0.6, 0.4


@dataclass(frozen=True)
class Interval:
    lo: float = -math.inf
    lo_inc: bool = False
    hi: float = math.inf
    hi_inc: bool = False

    def intersect(self, o: "Interval") -> "Interval":
        lo, lo_inc = max((self.lo, not self.lo_inc), (o.lo, not o.lo_inc))
        hi, hi_inc = min((self.hi, self.hi_inc), (o.hi, o.hi_inc))
        return Interval(lo, not lo_inc, hi, hi_inc)

    @property
    def empty(self) -> bool:
        return self.lo > self.hi or (self.lo == self.hi and not (self.lo_inc and self.hi_inc))

    def __str__(self) -> str:
        if self.empty:
            return "∅"
        lo = "-∞" if self.lo == -math.inf else f"{self.lo:g}"
        hi = "∞" if self.hi == math.inf else f"{self.hi:g}"
        return f"{'[' if self.lo_inc else '('}{lo}, {hi}{']' if self.hi_inc else ')'}"


def _cmp_interval(op: str, value: float) -> list[Interval]:
    return {">=": [Interval(value, True)], ">": [Interval(value, False)], "<=": [Interval(hi=value, hi_inc=True)],
            "<": [Interval(hi=value, hi_inc=False)], "=": [Interval(value, True, value, True)]}.get(op, [Interval()])


def _complement(i: Interval) -> list[Interval]:
    out = []
    if i.lo != -math.inf:
        out.append(Interval(hi=i.lo, hi_inc=not i.lo_inc))
    if i.hi != math.inf:
        out.append(Interval(i.hi, not i.hi_inc))
    return out


def _single_var_cmp(ast, params: dict) -> tuple[str, Interval] | None:
    """Reconhece `var OP (literal|param)` sobre uma variável numérica."""
    if not isinstance(ast, expr.Cmp) or not isinstance(ast.left, expr.Ref):
        return None
    r = ast.right
    if isinstance(r, expr.Lit) and isinstance(r.value, float):
        val = r.value
    elif isinstance(r, expr.Ref) and r.name in params:
        val = float(params[r.name])
    else:
        return None
    ivs = _cmp_interval(ast.op, val)
    return (ast.left.name, ivs[0]) if len(ivs) == 1 else None


def branch_intervals(model: PolicyModel, rule_id: str, params: dict) -> tuple[str, list[tuple[str, list[Interval]]]] | None:
    """Intervalo de cada ramo com semântica de primeiro-que-casa (ramo i = cond_i ∧ ¬cond_<i)."""
    rule = model.rules[rule_id]
    if rule.logic["type"] != "case_when":
        return None
    var, prior, out = None, [Interval()], []
    for ast, then in rule.conditions:
        sc = _single_var_cmp(ast, params)
        if not sc or (var and sc[0] != var):
            return None
        var = sc[0]
        out.append((then, [p.intersect(sc[1]) for p in prior if not p.intersect(sc[1]).empty]))
        prior = [p.intersect(c) for p in prior for c in _complement(sc[1]) if not p.intersect(c).empty]
    out.append((rule.logic.get("else"), prior))
    return var, out


def g1_shared_input(model: PolicyModel, overrides: dict) -> list[dict]:
    sub = affected_subdag(model, list(overrides))
    changed = set(sub.seed) | set(sub.forward)
    param_names = {p.name for p in model.parameters.values()}
    c_inputs = {v for r in changed for v in model.rules[r].inputs} - param_names
    out = []
    for rid in model.order:
        if rid in changed:
            continue
        shared = sorted(set(model.rules[rid].inputs) & c_inputs)
        if not shared:
            continue
        downstream = [c for o in model.rules[rid].outputs for c in model.consumed_by.get(o, [])]
        out.append({"generator": "G1", "source": "deterministic_analysis", "evidenceLevel": "none",
                    "ruleRefs": [rid] + downstream,
                    "title": f"{rid} ({model.rules[rid].name}) lê {', '.join(shared)}, a mesma variável do caminho alterado",
                    "text": (f"A mudança não recalcula {rid}, mas {rid} usa {', '.join(shared)} como as regras alteradas "
                             f"({', '.join(sorted(changed))}). Vale olhar o efeito combinado"
                             + (f"; {rid} alimenta {', '.join(downstream)}." if downstream else ".")),
                    "structuralBasis": {"sharedInputs": shared, "changedPath": sorted(changed)}})
    return out


def g2_reachability(model: PolicyModel, overrides: dict) -> list[dict]:
    """Ramos de outras regras que ficam (in)alcançáveis para propostas aprovadas."""
    base_p = model.baseline_params()
    scen_p = dict(base_p)
    for pid, v in overrides.items():
        scen_p[model.parameters[pid].name] = float(v)
    sub = affected_subdag(model, list(overrides))
    out = []
    for seed in sub.seed:
        approve_b = branch_intervals(model, seed, base_p)
        approve_s = branch_intervals(model, seed, scen_p)
        if not approve_b or not approve_s:
            continue
        var = approve_b[0]
        # a restrição de aprovação é o ramo explícito (o que não cai no else)
        cons_b = approve_b[1][0][1]
        cons_s = approve_s[1][0][1]
        for rid in model.order:
            if rid == seed:
                continue
            bi = branch_intervals(model, rid, base_p)
            if not bi or bi[0] != var:
                continue
            for label, ivs in bi[1]:
                reach_b = [i.intersect(c) for i in ivs for c in cons_b if not i.intersect(c).empty]
                reach_s = [i.intersect(c) for i in ivs for c in cons_s if not i.intersect(c).empty]
                if bool(reach_b) == bool(reach_s):
                    continue
                users = [r.id for r in model.rules.values() if r.logic["type"] == "matrix_lookup"
                         and r.logic["row_key"] in model.rules[rid].outputs and label in r.logic["matrix"]]
                row_txt = ""
                if users:
                    cols = ", ".join(f"{k}={v:g}" for k, v in model.rules[users[0]].logic["matrix"][label].items())
                    row_txt = f"; a linha {label} da matriz de {users[0]} ({cols}) deixa de ser usada para aprovados" if reach_b else \
                              f"; a linha {label} da matriz de {users[0]} ({cols}) passa a ser usada para aprovados"
                verb = "nenhuma proposta aprovada cai" if reach_b else "propostas aprovadas passam a cair"
                pname = ", ".join(f"{model.parameters[p].name} {model.parameters[p].value:g} → {v:g}" for p, v in overrides.items())
                out.append({"generator": "G2", "source": "deterministic_analysis", "evidenceLevel": "none",
                            "ruleRefs": [seed, rid] + users,
                            "title": f"Com {pname}, {verb} na faixa {label} de {rid}",
                            "text": f"Com {pname}, {verb} na faixa {label} de {rid}{row_txt}. "
                                    f"É um fato estrutural da política, não uma estimativa de impacto.",
                            "structuralBasis": {"variable": var, "branch": label,
                                                "branchInterval": [str(i) for i in ivs],
                                                "approvalBaseline": [str(i) for i in cons_b],
                                                "approvalScenario": [str(i) for i in cons_s],
                                                "reachableBaseline": [str(i) for i in reach_b],
                                                "reachableScenario": [str(i) for i in reach_s]}})
    return out


def relevance(assessments: list[dict], kind: str) -> float:
    rel = sum(1 for a in assessments if a["kind"] == kind and a["relevant"])
    tot = sum(1 for a in assessments if a["kind"] == kind)
    return (rel + 1) / (tot + 2)


def rank(candidates: list[dict], assessments: list[dict], cap: int) -> list[dict]:
    for c in candidates:
        kind = c.get("generator") or "ai_suggestion"
        c["score"] = round(W_STRUCT * (c["source"] == "deterministic_analysis") + W_FB * relevance(assessments, kind), 4)
    return sorted(candidates, key=lambda c: -c["score"])[:cap]
