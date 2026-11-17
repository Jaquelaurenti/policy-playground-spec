"""Gramática fechada das condições de `case_when` (design §7.2).

Aceita apenas `{var|param|literal} {= != >= <= > <} {var|param|literal}`
unidos por AND/OR (AND tem precedência) e parênteses. Qualquer coisa fora
disso é erro de validação, nunca execução "por aproximação".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

COMPARATORS = {"=", "!=", ">=", "<=", ">", "<"}
_TOKEN = re.compile(
    r"\s*(?:(?P<num>-?\d+(?:\.\d+)?)|(?P<str>'[^']*')|(?P<op>>=|<=|!=|=|>|<)"
    r"|(?P<par>[()])|(?P<word>[A-Za-z_][A-Za-z0-9_]*))"
)


class ExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Lit:
    value: Union[float, str]


Operand = Union[Ref, Lit]


@dataclass(frozen=True)
class Cmp:
    left: Operand
    op: str
    right: Operand


@dataclass(frozen=True)
class BoolOp:
    op: str  # AND | OR
    items: tuple


Node = Union[Cmp, BoolOp]


def tokenize(text: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExpressionError(f"Trecho fora da gramática suportada perto de: {text[pos:pos + 20]!r}")
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "word" and val.upper() in ("AND", "OR"):
            kind, val = "bool", val.upper()
        out.append((kind, val))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self) -> Node:
        node = self.or_()
        if self.i != len(self.t):
            raise ExpressionError(f"Sobrou texto não interpretável: {self.t[self.i:]}")
        return node

    def or_(self):
        items = [self.and_()]
        while self.peek() == ("bool", "OR"):
            self.take()
            items.append(self.and_())
        return items[0] if len(items) == 1 else BoolOp("OR", tuple(items))

    def and_(self):
        items = [self.atom()]
        while self.peek() == ("bool", "AND"):
            self.take()
            items.append(self.atom())
        return items[0] if len(items) == 1 else BoolOp("AND", tuple(items))

    def atom(self):
        if self.peek() == ("par", "("):
            self.take()
            node = self.or_()
            if self.take() != ("par", ")"):
                raise ExpressionError("Parêntese não fechado")
            return node
        left = self.operand()
        kind, op = self.take()
        if kind != "op" or op not in COMPARATORS:
            raise ExpressionError(f"Esperava um comparador ({', '.join(sorted(COMPARATORS))}), veio {op!r}")
        return Cmp(left, op, self.operand())

    def operand(self) -> Operand:
        kind, val = self.take()
        if kind == "num":
            return Lit(float(val))
        if kind == "str":
            return Lit(val[1:-1])
        if kind == "word":
            return Ref(val)
        raise ExpressionError(f"Esperava variável, parâmetro ou literal, veio {val!r}")


def parse(text: str) -> Node:
    return _Parser(tokenize(text)).parse()


def refs(node: Node) -> set[str]:
    if isinstance(node, Cmp):
        return {o.name for o in (node.left, node.right) if isinstance(o, Ref)}
    return set().union(*(refs(i) for i in node.items))


class MissingValue(Exception):
    """Uma referência não tem valor: a regra não pode ser calculada."""


def evaluate(node: Node, env: dict) -> bool:
    if isinstance(node, BoolOp):
        vals = (evaluate(i, env) for i in node.items)
        return all(vals) if node.op == "AND" else any(vals)
    a, b = _val(node.left, env), _val(node.right, env)
    if isinstance(a, (int, float)) != isinstance(b, (int, float)):
        if node.op in ("=", "!="):
            return (str(a) == str(b)) == (node.op == "=")
        raise MissingValue(f"Comparação entre tipos diferentes: {a!r} {node.op} {b!r}")
    return {"=": a == b, "!=": a != b, ">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[node.op]


def _val(o: Operand, env: dict):
    if isinstance(o, Lit):
        return o.value
    if o.name not in env or env[o.name] is None:
        raise MissingValue(o.name)
    return env[o.name]
