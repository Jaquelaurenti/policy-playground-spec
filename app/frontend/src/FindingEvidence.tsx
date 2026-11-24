// Evidência de um achado (ajuste 1) e cenário próprio do achado (R9, ajustes 2 e 3).
import { useEffect, useState } from "react";
import { api, type Json } from "./api";
import { fmt, outcomeLabel, outputLabel, paramLabel } from "./labels";

/** Texto do cenário: "renda mínima 3.500" ou "recorte renda_mensal ∈ [2500, 3000) com renda mínima 3.000". */
export function scenarioText(policy: Json, sc: Json | null | undefined): string {
  if (!sc) return "";
  const ov = Object.entries(sc.overrides || {}).map(([pid, v]) => {
    const p = policy.parameters.find((x: Json) => x.id === pid);
    return `${p ? paramLabel(p) : pid} ${fmt(Number(v))}`;
  }).join(", ");
  return sc.slice ? `recorte ${sc.slice.label}, com ${ov}` : ov;
}

function delta(n: number) {
  return n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(Math.abs(n))}` : "0";
}

export function EvidencePanel({ policy, executionId, mainExec }: { policy: Json; executionId: string; mainExec?: Json }) {
  const [ex, setEx] = useState<Json | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.execution(executionId).then(setEx).catch((e) => setErr((e as Error).message)); }, [executionId]);
  if (err) return <div className="callout err" style={{ marginTop: 8 }}>{err}</div>;
  if (!ex) return <p className="muted"><span className="spinner" /> Carregando a evidência…</p>;

  const cmp = ex.comparison || {};
  const outs = cmp.outputs || {};
  const res = outs.resultado;
  const cats = res && res.type === "category" ? Object.keys({ ...res.baseline, ...res.scenario }) : [];
  const motivos = Object.entries(cmp.motivos || {}).filter(([, m]: [string, Json]) => m.baseline !== m.scenario);
  const mainRes = mainExec?.comparison?.outputs?.resultado;
  const sameAsMain = mainExec && !ex.slice && JSON.stringify(mainExec.overrides) === JSON.stringify(ex.overrides);
  const changedRows = (ex.rows || []).filter((r: Json) => r.baseline?.resultado !== r.scenario?.resultado);

  return (
    <div className="evidence">
      <div className="kv">
        <div>Cenário simulado</div><div>{scenarioText(policy, ex)}</div>
        <div>Execução</div><div className="mono">{ex.executionId} · {ex.mode} · {ex.source === "agent" ? "feita pelo agente" : "motor determinístico"}</div>
        <div>Propostas</div><div>{cmp.records ?? (ex.rows || []).length}{ex.slice ? " no recorte" : " (todas)"}</div>
      </div>
      {cats.length > 0 && <table style={{ marginTop: 8 }}>
        <thead><tr><th>{outputLabel("resultado")}</th><th>Hoje</th><th>Neste cenário</th><th>Diferença</th>
          {mainRes && !sameAsMain && !ex.slice && <th>No cenário confirmado</th>}</tr></thead>
        <tbody>{cats.map((c) => {
          const b = res.baseline[c] || 0, s = res.scenario[c] || 0;
          return <tr key={c}><td>{outcomeLabel(c)}</td><td>{b}</td><td><b>{s}</b></td><td>{delta(s - b)}</td>
            {mainRes && !sameAsMain && !ex.slice && <td>{mainRes.scenario[c] || 0}</td>}</tr>;
        })}</tbody>
      </table>}
      {motivos.length > 0 && <p className="muted" style={{ margin: "6px 0" }}>
        Motivos de recusa: {motivos.map(([code, m]: [string, Json]) => `${m.name} (${code}) ${m.baseline} → ${m.scenario}`).join(" · ")}
      </p>}
      {ex.slice && changedRows.length > 0 && <>
        <p style={{ margin: "8px 0 4px" }}><b>Quem muda dentro do recorte</b></p>
        <table><thead><tr><th>Proposta</th><th>Hoje</th><th>Neste cenário</th></tr></thead>
          <tbody>{changedRows.map((r: Json) => <tr key={r.recordId}><td className="mono">{r.recordId}</td>
            <td>{outcomeLabel(r.baseline.resultado)}</td><td><b>{outcomeLabel(r.scenario.resultado)}</b></td></tr>)}</tbody></table>
        <p className="muted" style={{ margin: "6px 0 0" }}>
          {(ex.rows || []).length - changedRows.length} proposta(s) do recorte não mudam de resultado.
        </p>
      </>}
      {sameAsMain && <p className="muted" style={{ margin: "6px 0 0" }}>Mesmo cenário do quadro "Impacto simulado": esta execução só foi vinculada ao achado.</p>}
    </div>
  );
}
