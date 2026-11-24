"""Pacote de mudança para engenharia (R10.2, R11, R12 na forma do MVP; design §9.2).

Depois de uma decisão de aceite, gera um artefato revisável e NÃO SUBMETIDO, de forma
determinística (sem IA): o mesmo cenário, a mesma execução e a mesma decisão produzem
o mesmo pacote, byte a byte, exceto o carimbo de geração.

  1. patch  — JSON Patch (RFC 6902) sobre o Policy Spec, com antes e depois
  2. testes — um caso por proposta sintética, com o resultado esperado após a mudança
  3. prova  — aplica o patch numa cópia da política, recalcula TUDO do zero e confere os testes
  4. manifesto — hipótese, cenário, execução, decisão, achados e versões (rastreabilidade)
  5. prévia do PR — título e corpo como seriam abertos; destino a definir (OQ-9)
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import engine
from .model import load_policy

PACKAGE_VERSION = "change-package/1"


class ChangePackageError(ValueError):
    pass


def build_patch(model, overrides: dict[str, float]) -> list[dict]:
    spec = model.spec_snapshot()
    ops = []
    for pid, value in sorted(overrides.items()):
        idx = next((i for i, p in enumerate(spec["parameters"]) if p["id"] == pid), None)
        if idx is None:
            raise ChangePackageError(f"Parâmetro inexistente no Policy Spec: {pid}")
        p = spec["parameters"][idx]
        new = int(value) if float(value).is_integer() and isinstance(p["value"], int) else float(value)
        ops.append({"op": "test", "path": f"/parameters/{idx}/value", "value": p["value"]})
        ops.append({"op": "replace", "path": f"/parameters/{idx}/value", "value": new,
                    "_meta": {"parameterId": pid, "name": p["name"], "from": p["value"], "to": new,
                              "unit": p.get("unit", ""), "usedBy": list(p.get("used_by", []))}})
    return ops


def apply_patch(spec: dict, patch: list[dict]) -> dict:
    """Aplica só o subconjunto usado aqui (test/replace em /parameters/<i>/value)."""
    out = copy.deepcopy(spec)
    for op in patch:
        _, coll, idx, field = op["path"].split("/")
        target = out[coll][int(idx)]
        if op["op"] == "test" and target[field] != op["value"]:
            raise ChangePackageError(f"O Policy Spec mudou: {op['path']} não vale mais {op['value']}")
        if op["op"] == "replace":
            target[field] = op["value"]
    return out


def build_tests(model, rows: list[dict]) -> list[dict]:
    """Casos de regressão a partir das linhas da execução: o que deve sair após a mudança."""
    tests = []
    for r in rows:
        changed = {o: {"antes": r["baseline"].get(o), "depois": r["scenario"].get(o)}
                   for o in model.output_vars if r["baseline"].get(o) != r["scenario"].get(o)}
        tests.append({"recordId": r["recordId"], "kind": "muda" if changed else "nao_muda",
                      "expected": {o: r["scenario"].get(o) for o in model.output_vars},
                      "changes": changed,
                      "motivos": {"antes": r.get("baselineMotivos", []), "depois": r.get("scenarioMotivos", [])}})
    tests.sort(key=lambda t: (t["kind"] != "muda", t["recordId"]))
    return tests


def verify(model, patch: list[dict], tests: list[dict]) -> dict:
    """Prova independente: política com o patch aplicado, recálculo completo (sem reaproveitar baseline)."""
    patched = load_policy(apply_patch(model.spec_snapshot(), patch), model.extensions, model.dataset)
    params = patched.baseline_params()
    records = {r["record_id"]: r for r in model.dataset["records"]}
    results = []
    for t in tests:
        rec = records.get(t["recordId"])
        if rec is None:
            results.append({"recordId": t["recordId"], "passed": False, "reason": "proposta ausente no dataset"})
            continue
        payload = {k: v for k, v in rec.items() if k not in ("record_id", "cobertura")}
        env = engine.run_record(patched, payload, params)
        got = {o: env.get(o) for o in patched.output_vars}
        ok = got == t["expected"]
        results.append({"recordId": t["recordId"], "passed": ok, **({} if ok else {"got": got})})
    passed = sum(r["passed"] for r in results)
    return {"method": "patch aplicado + recálculo completo com o motor determinístico", "passed": passed,
            "total": len(results), "ok": passed == len(results), "results": results,
            "patchedPolicyVersion": f"{patched.meta['id']}@{patched.meta.get('source_commit', 'unknown')}+playground"}


def pytest_source(model, hid: str, patch: list[dict], tests: list[dict]) -> str:
    """Arquivo de teste que a engenharia pode rodar contra o motor do Playground."""
    vectors = json.dumps([{"recordId": t["recordId"], "expected": t["expected"]} for t in tests], ensure_ascii=False, indent=2)
    ops = json.dumps([{k: v for k, v in op.items() if k != "_meta"} for op in patch], ensure_ascii=False, indent=2)
    return f'''"""Testes de regressão gerados pelo Policy Playground para {hid} (NÃO SUBMETIDO).
Dados sintéticos; selo SIMULADO. Gerado de forma determinística a partir da execução aceita."""
import json
from pathlib import Path

import pytest

from policy_playground.domain import engine
from policy_playground.domain.change_package import apply_patch
from policy_playground.domain.model import load_from_folder, load_policy

FIXTURES = Path(__file__).resolve().parents[4] / ".kiro" / "specs" / "policy-playground" / "fixtures"
PATCH = json.loads(r"""{ops}""")
CASES = json.loads(r"""{vectors}""")


@pytest.fixture(scope="module")
def patched():
    base = load_from_folder(FIXTURES)
    return load_policy(apply_patch(base.spec_snapshot(), PATCH), base.extensions, base.dataset)


@pytest.mark.parametrize("case", CASES, ids=[c["recordId"] for c in CASES])
def test_resultado_apos_mudanca(patched, case):
    rec = next(r for r in patched.dataset["records"] if r["record_id"] == case["recordId"])
    payload = {{k: v for k, v in rec.items() if k not in ("record_id", "cobertura")}}
    env = engine.run_record(patched, payload, patched.baseline_params())
    assert {{o: env.get(o) for o in patched.output_vars}} == case["expected"]
'''


def _fmt(v, unit=""):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v} {unit}".strip()


def pr_preview(model, manifest: dict, patch: list[dict], tests: list[dict], verification: dict) -> dict:
    changes = [op["_meta"] for op in patch if op["op"] == "replace"]
    title = "Policy Playground: " + "; ".join(f"{c['name']} {_fmt(c['from'])} → {_fmt(c['to'])}" for c in changes)
    muda = [t for t in tests if t["kind"] == "muda"]
    cmp = manifest["evidence"]["deltas"]
    lines = [
        "> **NÃO SUBMETIDO.** Pacote demonstrativo gerado pelo Policy Playground sobre dados 100% sintéticos (selo SIMULADO).",
        "> Abrir este PR na plataforma de políticas de crédito depende de acesso aos repositórios (OQ-9).", "",
        "## Mudança", *[f"- `{c['parameterId']}` **{c['name']}**: {_fmt(c['from'], c['unit'])} → {_fmt(c['to'], c['unit'])} "
                         f"(usado por {', '.join(c['usedBy'])})" for c in changes], "",
        "## Evidência (execução determinística)",
        f"- Execução `{manifest['evidence']['executionId']}` · runner `{manifest['versions']['runner']}` · "
        f"dataset `{manifest['versions']['dataset']}`",
    ]
    for out, cats in cmp.items():
        if out == "motivos" or not isinstance(cats, dict):
            continue
        if "de" in cats:
            lines.append(f"- {out}: {_fmt(cats['de'])} → {_fmt(cats['para'])} (delta {_fmt(cats['delta'])})")
        else:
            lines += [f"- {out} · {c}: {v['de']} → {v['para']} (delta {v['delta']:+d})" for c, v in cats.items() if v["delta"]]
    lines += [f"- motivo {code} ({m['nome']}): {m['de']} → {m['para']} (delta {m['delta']:+d})"
              for code, m in cmp.get("motivos", {}).items() if m["delta"]]
    lines += ["", "## Testes de regressão",
              f"- {verification['passed']}/{verification['total']} passaram ({verification['method']})",
              f"- Propostas que mudam de resultado: {', '.join(t['recordId'] for t in muda) or 'nenhuma'}", "",
              "## Decisão humana",
              f"- {manifest['decision']['outcome']} por {manifest['decision']['decidedBy']} em {manifest['decision']['decidedAt']}",
              f"- Justificativa: {manifest['decision']['rationale']}",
              f"- Hipótese `{manifest['hypothesisId']}` · cenário `{manifest['scenario']['scenarioId']}` · "
              f"decisão `{manifest['decision']['decisionId']}`", "",
              "Este PR é um pedido de revisão: não faz merge nem deploy (R12.2)."]
    return {"title": title, "body": "\n".join(lines), "target": "a definir (OQ-9)", "status": "nao_submetido"}


def package_id(content: dict) -> str:
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    return "CP-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
