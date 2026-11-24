// Agente Investigador (R17): aciona a investigação e mostra, ao vivo, o plano, as ferramentas usadas,
// as recusas recuperadas e a recomendação. Os achados aparecem na lista "O que mais analisar".
import { useState } from "react";
import { api, type Json } from "./api";

const TOOL_LABEL: Record<string, string> = {
  get_policy: "Leu a política",
  preview_subdag: "Previu as dependências",
  trace_output: "Rastreou o que decide uma saída",
  run_scenario: "Simulou um cenário",
  compare: "Comparou execuções",
  get_candidates: "Consultou a análise da política (G1/G2)",
  read_audit: "Leu a trilha da investigação",
  submit_recommendation: "Enviou a recomendação",
  register_finding: "Registrou um achado",
};

const OUTCOME: Record<string, { cls: string; text: string }> = {
  done: { cls: "b-ok", text: "Concluída" },
  limited: { cls: "b-state", text: "Parou no limite" },
  model_unavailable: { cls: "b-err", text: "Modelo indisponível" },
  error: { cls: "b-err", text: "Erro" },
};

const clean = (t: string) => t.replace(/<thinking>|<\/thinking>/g, "").trim();

function describe(step: Json): string {
  const i = step.input || {};
  if (step.tool === "run_scenario" && i.overrides) {
    return Object.entries(i.overrides).map(([k, v]) => `${k} = ${v}`).join(", ");
  }
  if (step.tool === "compare") return i.against_execution_id ? `${i.execution_id} × ${i.against_execution_id}` : `${i.execution_id} × hoje`;
  if (step.tool === "register_finding") return i.title || "";
  return "";
}

export function AgentPanel({ rec, canWrite, refresh }: { rec: Json; canWrite: boolean; refresh: () => Promise<void> }) {
  const hid = rec.hypothesis.hypothesisId;
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const invs: Json[] = rec.investigations || [];
  const last = invs.length ? invs[invs.length - 1] : undefined;
  const running = last && last.state !== "done";

  const start = async () => {
    setErr(null);
    setStarting(true);
    try {
      const j = await api.investigate(hid);
      // polling (D-DQ4) com atualização da timeline a cada volta; o agente leva de segundos a ~1 min
      for (let i = 0; i < 120; i++) {
        await refresh();
        const r = await api.hypothesis(hid);
        const inv = (r.investigations || []).find((x: Json) => x.jobId === j.jobId);
        if (inv && inv.state === "done") break;
        await new Promise((res) => setTimeout(res, 1500));
      }
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  return (
    <section className="section">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Investigação do agente</h3>
        {canWrite && <button className="primary" disabled={starting || running} onClick={start}>
          {starting || running ? "Agente investigando…" : invs.length ? "Investigar de novo" : "Investigar com o agente"}
        </button>}
      </div>
      {!last && <p className="muted">
        O agente planeja, chama as ferramentas do motor, testa variações por conta própria e registra achados com evidência.
        Ele não decide: a decisão continua sua.
      </p>}
      {err && <div className="callout err" style={{ marginTop: 8 }}>{err}</div>}
      {last && <div className="card">
        <div className="row">
          {last.state !== "done" ? <span className="badge b-state"><span className="spinner" /> Investigando</span>
            : <span className={`badge ${OUTCOME[last.outcome]?.cls ?? "b-state"}`}>{OUTCOME[last.outcome]?.text ?? last.outcome}</span>}
          <span className="badge b-sim">SIMULADO</span>
          <span className="spacer" />
          {last.transport === "mcp" && <span className="badge b-det" title="O agente descobriu as ferramentas pelo tools/list e chamou cada uma pelo tools/call do servidor MCP do Playground">via MCP · {last.toolsDiscovered} ferramentas</span>}
          {last.state === "done" && <span className="muted">{last.steps} passos · {last.tokens?.toLocaleString("pt-BR")} tokens · modelo {last.model}</span>}
        </div>
        <ol className="agent-timeline">
          {(last.timeline || []).map((s: Json, k: number) => s.tool === "_plan"
            ? (clean(s.input?.text || "") && <li key={k} className="thought">{clean(s.input.text)}</li>)
            : <li key={k} className={s.status === "error" ? "tool error" : "tool"}>
              <b>{TOOL_LABEL[s.tool] ?? s.tool}</b>{describe(s) && <span className="muted"> · {describe(s)}</span>}
              {s.status === "error" && <div className="muted">Recusado: {s.error}</div>}
            </li>)}
        </ol>
        {last.outcome === "done" && last.recommendation && <div className="callout" style={{ marginTop: 8 }}>
          <b>Recomendação do agente</b><div>{last.recommendation}</div>
          <div className="muted">Os números vêm só das execuções do motor. A decisão é sua.</div>
        </div>}
        {last.outcome === "limited" && <div className="callout warn" style={{ marginTop: 8 }}>
          O agente parou no limite de passos ou de tokens (FinOps). Os achados registrados até aqui continuam válidos.
        </div>}
        {last.outcome === "model_unavailable" && <div className="callout warn" style={{ marginTop: 8 }}>
          O modelo de IA não está disponível neste ambiente: o agente não rodou. Seguem os pontos da análise da política (G1/G2).
        </div>}
        {last.outcome === "error" && <div className="callout err" style={{ marginTop: 8 }}>A investigação falhou: {last.reason}</div>}
      </div>}
    </section>
  );
}
