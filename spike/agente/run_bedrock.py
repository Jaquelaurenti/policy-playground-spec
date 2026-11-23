"""SPIKE — roda o Agente Investigador contra o Bedrock de verdade (CloudShell ou máquina com credenciais).

Uso, na raiz do repo:
  pip install -r app/backend/requirements.txt
  python spike/agente/run_bedrock.py --model us.amazon.nova-lite-v1:0 \
      --intent "aumentar a renda mínima para 3000" --set P001=3000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app" / "backend"), str(Path(__file__).resolve().parent)]

import boto3  # noqa: E402

from loop import investigate  # noqa: E402
from policy_playground.domain.model import load_from_folder  # noqa: E402
from policy_playground.service import Actor  # noqa: E402
from tool_registry import ToolRegistry  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="us.amazon.nova-lite-v1:0")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--intent", required=True)
    ap.add_argument("--set", action="append", required=True, help="P001=3000 (repita para mais de um)")
    ap.add_argument("--max-steps", type=int, default=10)
    a = ap.parse_args()
    overrides = {k: float(v) for k, v in (s.split("=", 1) for s in a.set)}
    model = load_from_folder(ROOT / ".kiro" / "specs" / "policy-playground" / "fixtures")
    reg = ToolRegistry(model, Actor("cloudshell", {"Policy Specialist"}))
    out = investigate(boto3.client("bedrock-runtime", region_name=a.region), a.model, reg,
                      a.intent, overrides, max_steps=a.max_steps)
    print(f"\n== status={out['status']}, {out['steps']} passos, {out['tokens']} tokens\n")
    for i, c in enumerate(out["calls"], 1):
        if c["tool"] == "_plan":
            print(f"{i:>2}. 💭 {c['input']['text'][:110]}")
            continue
        print(f"{i:>2}. {c['tool']:<22} {c['status']:<8} {json.dumps(c['input'], ensure_ascii=False)[:90]}"
              + (f"\n     ↳ {c['error']}" if c.get("error") else ""))
    print("\n== Achados")
    for f in out["findings"]:
        print(f"- [{', '.join(f['executionIds'])}] {f['title']}\n  {f['text']}")
    print("\n== Recomendação do agente\n" + out["summary"])


if __name__ == "__main__":
    main()
