import { useCallback, useEffect, useMemo, useState } from "react";
import { api, poll, setDemoIdentity, type Json } from "./api";
import { completeLogin, getConfig, login, logout, tokenClaims, type AppConfig } from "./auth";
import PolicyGraph from "./PolicyGraph";

const fmt = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const DEMO_ROLES = ["Policy Specialist", "Risk Approver", "Data Analyst", "Viewer"];
const STATE_PT: Record<string, string> = { suggested: "sugerido", under_investigation: "em investigação", executed: "executado", accepted: "aceito", rejected: "rejeitado" };

export function EvidenceBadge({ level }: { level: string }) {
  if (level === "simulated") return <span className="badge b-sim" title="Dados sintéticos — não é impacto real">SIMULADO</span>;
  if (level === "study_validated") return <span className="badge b-valid">Validado por estudo</span>;
  return <span className="badge b-none">Hipótese sem comprovação</span>;
}

export default function App() {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [authed, setAuthed] = useState(false);
  const [role, setRole] = useState("Policy Specialist");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const c = await getConfig();
      setCfg(c);
      if (c.auth === "cognito") {
        try { await completeLogin(c); } catch (e) { setError(String(e)); }
        setAuthed(!!tokenClaims());
      } else setAuthed(true);
    })();
  }, []);

  useEffect(() => { setDemoIdentity(role === "Policy Specialist" ? "especialista.demo" : role.toLowerCase().replace(/ /g, ".") + ".demo", role); }, [role]);

  if (!cfg) return null;
  if (!authed) return (
    <div className="login panel">
      <div className="brand" style={{ color: "#14161b" }}>Policy <span>Playground</span></div>
      <p className="muted">Ambiente de demonstração com dados 100% sintéticos.</p>
      {error && <div className="callout err">{error}</div>}
      <button className="primary" onClick={() => login(cfg)}>Entrar</button>
    </div>
  );
  return <Workspace cfg={cfg} role={role} setRole={setRole} />;
}

function Workspace({ cfg, role, setRole }: { cfg: AppConfig; role: string; setRole: (r: string) => void }) {
  const [policy, setPolicy] = useState<Json | null>(null);
  const [me, setMe] = useState<Json | null>(null);
  const [selected, setSelected] = useState<string | null>("R005");
  const [list, setList] = useState<Json[]>([]);
  const [hid, setHid] = useState<string | null>(null);
  const [rec, setRec] = useState<Json | null>(null);
  const [preview, setPreview] = useState<Json | null>(null);
  const [focus, setFocus] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshList = useCallback(async () => setList(await api.hypotheses()), []);
  const refresh = useCallback(async (id = hid) => { if (id) setRec(await api.hypothesis(id)); }, [hid]);

  useEffect(() => {
    (async () => {
      try {
        setPolicy(await api.policy());
        setMe(await api.me());
        await refreshList();
      } catch (e) { setErr(String((e as Error).message)); }
    })();
  }, [role, refreshList]);
  useEffect(() => { refresh(hid); }, [hid, refresh]);

  const run = async (fn: () => Promise<unknown>) => {
    setErr(null); setBusy(true);
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const highlight = useMemo(() => {
    const sub = rec?.scenarios?.at(-1)?.affectedSubDag || rec?.hypothesis?.potentialImpact || preview?.subDag;
    if (!sub) return new Set<string>();
    return new Set<string>([...sub.changedParams, ...sub.executionSet, ...sub.path.flat()]);
  }, [rec, preview]);

  if (!policy) return <div style={{ padding: 20 }}>{err ? <div className="callout err">{err}</div> : "Carregando a política…"}</div>;
  const canWrite = me?.roles?.includes("Policy Specialist");

  return (
    <>
      <div className="topbar">
        <div className="brand">Policy <span>Playground</span></div>
        <div className="meta">{policy.policy.name}<br /><span className="mono">{policy.policyVersion} · dataset {policy.datasetVersion}</span></div>
        <div className="spacer" />
        {cfg.auth === "local" ? (
          <select value={role} onChange={(e) => setRole(e.target.value)} title="Perfil de demonstração">
            {DEMO_ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        ) : <span className="meta">{me?.id} · {me?.roles?.join(", ")}</span>}
        {cfg.auth === "cognito" && <button onClick={() => logout(cfg)}>Sair</button>}
      </div>
      <div className="banner">
        Todo número desta tela vem do executor determinístico sobre <b>dados sintéticos</b> e leva o selo <b>SIMULADO</b>: não é impacto real.
        A IA só sugere investigações, nunca produz números.
      </div>
      {err && <div style={{ padding: "10px 20px 0" }}><div className="callout err">{err}</div></div>}
      <div className="layout">
        <div className="stack">
          <div className="panel">
            <h2>Política e dependências</h2>
            {!policy.validation.ok && <div className="callout err">Policy Spec inválido: {policy.validation.errors.join("; ")}</div>}
            <PolicyGraph policy={policy} highlight={highlight} focus={focus} onSelect={setSelected} />
            <p className="muted">Clique numa regra para ver a lógica. Em destaque: o caminho afetado pela hipótese atual (descoberto pelo DAG, não pela IA).</p>
          </div>
          {selected && <RuleDetail policy={policy} id={selected} />}
        </div>
        <div className="stack">
          <div className="panel">
            <h2>Hipóteses</h2>
            <NewHypothesis policy={policy} disabled={!canWrite || busy} onPreview={setPreview}
              onCreate={(intent, ov) => run(async () => {
                const r = await api.createHypothesis(intent, ov);
                setHid(r.hypothesis.hypothesisId); setRec(r); await refreshList();
              })} />
            {list.length > 0 && <div className="hlist" style={{ marginTop: 12 }}>
              {list.map((h) => <button key={h.hypothesisId} className={h.hypothesisId === hid ? "sel" : ""} onClick={() => setHid(h.hypothesisId)}>
                <b className="mono">{h.hypothesisId}</b> · {h.intent}<br /><span className="muted">{h.createdBy} · {new Date(h.createdAt).toLocaleString("pt-BR")}</span>
              </button>)}
            </div>}
          </div>
          {rec && <Investigation policy={policy} rec={rec} canWrite={!!canWrite} canDecide={!!me?.roles?.some((r: string) => ["Policy Specialist", "Risk Approver"].includes(r))}
            busy={busy} run={run} refresh={() => refresh(rec.hypothesis.hypothesisId)} setFocus={setFocus} />}
        </div>
      </div>
    </>
  );
}

function RuleDetail({ policy, id }: { policy: Json; id: string }) {
  const p = policy.parameters.find((x: Json) => x.id === id);
  if (p) return (
    <div className="panel"><h3>{p.id} · {p.name}</h3>
      <div className="kv"><div>Valor (baseline)</div><div>{fmt(p.value)} {p.unit}</div><div>Usado por</div><div>{p.usedBy.join(", ")}</div>
        <div>Editável</div><div>{p.editable ? `sim, de ${fmt(p.domain.min)} a ${fmt(p.domain.max)} em passos de ${fmt(p.domain.step)}` : "não (somente leitura)"}</div>
        <div>Descrição</div><div>{p.description}</div></div></div>
  );
  const r = policy.rules.find((x: Json) => x.id === id);
  if (!r) return null;
  const motivo = policy.motivos.find((m: Json) => m.rule_id === id);
  return (
    <div className="panel">
      <h3>{r.id} · {r.name} <span className="badge b-state">{r.area || "sem área"}</span></h3>
      <div className="kv">
        <div>Tipo</div><div>{r.type} · <span className="mono">{r.logic.type}</span></div>
        <div>Entradas</div><div className="mono">{r.inputs.join(", ") || "payload"}</div>
        <div>Saídas</div><div className="mono">{r.outputs.join(", ")}</div>
        <div>Depende de</div><div className="mono">{r.dependsOn.join(", ") || "—"}</div>
        {r.parameters.length > 0 && <><div>Parâmetros</div><div className="mono">{r.parameters.join(", ")}</div></>}
        {motivo && <><div>Motivo de Decisão</div><div>{motivo.code} · {motivo.name}</div></>}
      </div>
      <div style={{ marginTop: 10 }}>
        {r.logic.type === "case_when" && <table><thead><tr><th>Quando</th><th>Então</th></tr></thead><tbody>
          {r.logic.branches.map((b: Json, i: number) => <tr key={i}><td className="mono">{b.when}</td><td>{b.then}</td></tr>)}
          <tr><td className="muted">senão</td><td>{r.logic.else}</td></tr></tbody></table>}
        {r.logic.type === "json_extract" && <div className="mono">{r.logic.path} → {r.logic.cast}</div>}
        {r.logic.type === "matrix_lookup" && <table><thead><tr><th>{r.logic.row_key} \ {r.logic.col_key}</th>{r.logic.col_labels.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{Object.entries(r.logic.matrix).map(([row, cols]: [string, Json]) => <tr key={row}><td>{row}</td>{r.logic.col_labels.map((c: string) => <td key={c}>{fmt(cols[c])}</td>)}</tr>)}</tbody></table>}
      </div>
      {r.readOnlyThresholds.length > 0 && <p className="muted">Limiares escritos como literal na regra (somente leitura no MVP): {r.readOnlyThresholds.join("; ")}</p>}
    </div>
  );
}

function NewHypothesis({ policy, disabled, onCreate, onPreview }: { policy: Json; disabled: boolean;
  onCreate: (intent: string, ov?: Record<string, number>) => void; onPreview: (p: Json | null) => void }) {
  const [intent, setIntent] = useState("Testar renda mínima de R$ 2.500 para R$ 3.000");
  return (
    <div>
      <textarea value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="Descreva a hipótese em linguagem natural" disabled={disabled} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="primary" disabled={disabled || !intent.trim()} onClick={() => { onPreview(null); onCreate(intent); }}>Estruturar hipótese</button>
        <span className="muted">{disabled ? "Seu perfil só pode consultar." : `Parâmetros editáveis: ${policy.parameters.filter((p: Json) => p.editable).map((p: Json) => p.id).join(", ")}`}</span>
      </div>
    </div>
  );
}

function Investigation({ policy, rec, canWrite, canDecide, busy, run, refresh, setFocus }: {
  policy: Json; rec: Json; canWrite: boolean; canDecide: boolean; busy: boolean; run: (fn: () => Promise<unknown>) => void;
  refresh: () => Promise<void>; setFocus: (s: Set<string>) => void }) {
  const h = rec.hypothesis;
  const hid = h.hypothesisId;
  const proposal = h.structuring;
  const param = policy.parameters.find((p: Json) => p.id === (proposal.parameterId || Object.keys(h.proposedOverrides)[0]));
  const [value, setValue] = useState<number>(h.proposedOverrides[param?.id] ?? param?.value ?? 0);
  const [execution, setExecution] = useState<Json | null>(null);
  useEffect(() => { setValue(h.proposedOverrides[param?.id] ?? param?.value ?? 0); setExecution(null); }, [hid]); // eslint-disable-line

  const lastExec = rec.executions.filter((e: Json) => !e.findingId).at(-1);
  useEffect(() => { if (lastExec?.jobState === "done") api.execution(lastExec.executionId).then(setExecution); }, [lastExec?.executionId, lastExec?.jobState]);

  const step = rec.decisions.length ? 5 : rec.findings.length ? 4 : lastExec ? 3 : rec.scenarios.length ? 2 : 1;
  const steps = ["Estruturar", "Confirmar cenário", "Executar", "Investigar", "Decidir"];

  const execute = () => run(async () => {
    const r = await api.execute(hid);
    await refresh();
    const done = await poll(() => api.execution(r.executionId), (x: Json) => x.jobState === "done");
    setExecution(done); await refresh();
  });

  return (
    <div className="panel">
      <div className="steps">{steps.map((s, i) => <span key={s} className={`step ${i + 1 === step ? "on" : i + 1 < step ? "done" : ""}`}>{i + 1}. {s}</span>)}</div>
      <h3>{h.intent}</h3>
      <p className="muted mono">{hid} · {h.policyVersion} · {h.datasetVersion}</p>

      {!proposal.understood && <div className="callout warn">{proposal.message}</div>}
      {param && <div className="card">
        <b>Proposta estruturada</b> <span className="muted">(nada roda sem a sua confirmação)</span>
        <p style={{ margin: "6px 0" }}>{param.id} <span className="mono">{param.name}</span>: {fmt(param.value)} → <b>{fmt(value)}</b> {param.unit} · usado por {param.usedBy.join(", ")}</p>
        {h.potentialImpact && <div className="callout">Pode afetar: <b>{h.potentialImpact.executionSet.join(" → ")}</b>, saída <b>{h.potentialImpact.affectedOutputs.join(", ")}</b>
          {h.potentialImpact.affectedMotivos.length > 0 && <> e o motivo {h.potentialImpact.affectedMotivos.map((m: Json) => `${m.code} (${m.name})`).join(", ")}</>}.
          É o caminho de dependências, <b>não um resultado calculado</b>.</div>}
        {param.editable && canWrite && <div className="slider" style={{ marginTop: 10 }}>
          <input type="range" min={param.domain.min} max={param.domain.max} step={param.domain.step} value={value} onChange={(e) => setValue(+e.target.value)} />
          <input type="number" min={param.domain.min} max={param.domain.max} step={param.domain.step} value={value} onChange={(e) => setValue(+e.target.value)} />
        </div>}
        {canWrite && <div className="row" style={{ marginTop: 10 }}>
          <button className="primary" disabled={busy} onClick={() => run(async () => { await api.confirm(hid, { [param.id]: value }); await refresh(); })}>Confirmar cenário</button>
          <button disabled={busy || !rec.scenarios.length} onClick={execute}>Executar (SimulatedRunner)</button>
        </div>}
        {rec.scenarios.length > 0 && <p className="muted">Cenário confirmado {rec.scenarios.at(-1).scenarioId}: {Object.entries(rec.scenarios.at(-1).overrides).map(([k, v]) => `${k}=${fmt(v as number)}`).join(", ")} por {rec.scenarios.at(-1).confirmedBy}</p>}
      </div>}

      {lastExec && lastExec.jobState !== "done" && <div className="callout" style={{ marginTop: 10 }}>Execução {lastExec.executionId}: {lastExec.jobState}…</div>}
      {execution && <Results policy={policy} ex={execution} />}

      {rec.scenarios.length > 0 && <Findings rec={rec} canWrite={canWrite} busy={busy} run={run} refresh={refresh} setFocus={setFocus} />}
      {lastExec && <Decisions rec={rec} canDecide={canDecide} busy={busy} run={run} refresh={refresh} />}
      <Audit hid={hid} events={rec.events} metrics={rec.metrics} />
    </div>
  );
}

function Results({ policy, ex }: { policy: Json; ex: Json }) {
  if (ex.status !== "ok") return <div className="callout err" style={{ marginTop: 12 }}>Não foi possível calcular: {ex.reason}. Nenhum número parcial é mostrado.</div>;
  const c = ex.comparison;
  const res = c.outputs.resultado;
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b>Baseline × cenário · {c.records} propostas sintéticas</b>
        <span className="row"><EvidenceBadge level={ex.evidenceLevel} />{ex.reused && <span className="badge b-state" title="Mesma chave de idempotência">resultado reaproveitado</span>}</span>
      </div>
      <p className="muted">Execução {ex.executionId} · tentativa {ex.attempt} · {ex.runnerVersion} · executou só {ex.subDag.executionSet.join(", ")} e reaproveitou o baseline no resto.</p>
      <table>
        <thead><tr><th>Saída</th><th>Baseline</th><th>Cenário</th><th>Δ</th></tr></thead>
        <tbody>
          {Object.keys(res.baseline).map((k) => <tr key={k}><td>{policy.outputVars[0]} = {k}</td><td>{res.baseline[k]} <SimTag /></td><td>{res.scenario[k]} <SimTag /></td>
            <td className={res.scenario[k] - res.baseline[k] > 0 ? "delta-up" : res.scenario[k] < res.baseline[k] ? "delta-down" : ""}>{signed(res.scenario[k] - res.baseline[k])}</td></tr>)}
          <tr><td>Soma do limite sugerido dos aprovados</td><td>R$ {fmt(c.approvedLimitSum.baseline)} <SimTag /></td><td>R$ {fmt(c.approvedLimitSum.scenario)} <SimTag /></td>
            <td className={c.approvedLimitSum.scenario < c.approvedLimitSum.baseline ? "delta-down" : "delta-up"}>R$ {signed(c.approvedLimitSum.scenario - c.approvedLimitSum.baseline)}</td></tr>
        </tbody>
      </table>
      <table style={{ marginTop: 10 }}>
        <thead><tr><th>Motivo de Decisão</th><th>Baseline</th><th>Cenário</th></tr></thead>
        <tbody>{Object.entries(c.motivos).map(([code, m]: [string, Json]) => <tr key={code}><td>{code} · {m.name} ({m.ruleId})</td><td>{m.baseline} <SimTag /></td><td>{m.scenario} <SimTag /></td></tr>)}</tbody>
      </table>
      {res.changedRecords.length > 0 && <><p style={{ marginBottom: 4 }}><b>Propostas que mudaram de resultado</b></p>
        <table><tbody>{ex.rows.filter((r: Json) => res.changedRecords.includes(r.recordId)).map((r: Json) =>
          <tr key={r.recordId}><td className="mono">{r.recordId}</td><td>{r.baseline.resultado} → <b>{r.scenario.resultado}</b></td><td className="muted">{r.cobertura}</td></tr>)}</tbody></table></>}
      <p className="muted">{ex.validation.notes}.</p>
    </div>
  );
}

const SimTag = () => <span className="badge b-sim" style={{ fontSize: 9.5, padding: "1px 5px" }}>SIM</span>;
const signed = (n: number) => (n > 0 ? "+" : "") + fmt(n);

function Findings({ rec, canWrite, busy, run, refresh, setFocus }: { rec: Json; canWrite: boolean; busy: boolean;
  run: (fn: () => Promise<unknown>) => void; refresh: () => Promise<void>; setFocus: (s: Set<string>) => void }) {
  const hid = rec.hypothesis.hypothesisId;
  const pending = rec.suggestionJobs.some((j: Json) => j.state !== "done");
  const ask = () => run(async () => {
    const j = await api.suggest(hid);
    await poll(() => api.hypothesis(hid), (r: Json) => r.suggestionJobs.some((x: Json) => x.jobId === j.jobId && x.state === "done"));
    await refresh();
  });
  const lastJob = rec.suggestionJobs.at(-1);
  const act = (fn: () => Promise<unknown>) => run(async () => { await fn(); await refresh(); });
  const execFinding = (fid: string) => run(async () => {
    const r = await api.executeFinding(hid, fid);
    await poll(() => api.execution(r.executionId), (x: Json) => x.jobState === "done");
    await refresh();
  });
  return (
    <div style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Investigações sugeridas</h3>
        {canWrite && <button disabled={busy || pending} onClick={ask}>O que mais devo olhar?</button>}
      </div>
      {lastJob && <p className="muted">
        {lastJob.state !== "done" ? "Gerando sugestões…" : lastJob.modelStatus === "ok" ? `Geradores determinísticos + modelo · ${lastJob.tokens} tokens` :
          "Modelo indisponível neste ambiente: só os geradores determinísticos (G1/G2) rodaram."}
      </p>}
      {rec.findings.map((f: Json) => (
        <div className="card" key={f.findingId} onMouseEnter={() => setFocus(new Set(f.ruleRefs))} onMouseLeave={() => setFocus(new Set())}>
          <div className="row">
            {f.source === "ai_suggestion" ? <span className="badge b-ai">Sugestão da IA</span> : <span className="badge b-det">Análise estrutural {f.generator}</span>}
            <span className="badge b-state">{STATE_PT[f.investigationState]}</span>
            <EvidenceBadge level={f.evidenceLevel} />
            <span className="muted mono">score {f.score}</span>
          </div>
          <p style={{ margin: "8px 0 4px" }}><b>{f.title}</b></p>
          <p style={{ margin: 0, fontSize: 13.5 }}>{f.text}</p>
          <p className="muted mono" style={{ margin: "6px 0" }}>regras: {f.ruleRefs.join(", ")}{f.currentExecutionId && ` · evidência: ${f.currentExecutionId}`}</p>
          {canWrite && <div className="row">
            {f.investigationState === "suggested" && <button disabled={busy} onClick={() => act(() => api.transition(hid, f.findingId, "under_investigation"))}>Investigar</button>}
            {f.investigationState === "under_investigation" && <button disabled={busy} className="primary" onClick={() => execFinding(f.findingId)}>Executar cenário</button>}
            {f.investigationState === "executed" && <button disabled={busy} onClick={() => act(() => api.transition(hid, f.findingId, "accepted", "Aceito após ver a evidência"))}>Aceitar</button>}
            {["executed", "accepted"].includes(f.investigationState) && <button disabled={busy} className="ghost" onClick={() => act(() => api.transition(hid, f.findingId, "under_investigation", "Reabrir"))}>Reabrir</button>}
            {["suggested", "under_investigation", "executed"].includes(f.investigationState) && <button disabled={busy} className="ghost" onClick={() => act(() => api.transition(hid, f.findingId, "rejected", "Descartado"))}>Rejeitar</button>}
            {f.assessment === undefined ? <>
              <button disabled={busy} className="ghost" onClick={() => act(() => api.assess(hid, f.findingId, true))}>👍 Relevante</button>
              <button disabled={busy} className="ghost" onClick={() => act(() => api.assess(hid, f.findingId, false))}>👎 Irrelevante</button></>
              : <span className="muted">Avaliado como {f.assessment ? "relevante" : "irrelevante"}</span>}
          </div>}
        </div>
      ))}
    </div>
  );
}

function Decisions({ rec, canDecide, busy, run, refresh }: { rec: Json; canDecide: boolean; busy: boolean;
  run: (fn: () => Promise<unknown>) => void; refresh: () => Promise<void> }) {
  const [rationale, setRationale] = useState("");
  const hid = rec.hypothesis.hypothesisId;
  const evidence = rec.executions.filter((e: Json) => e.jobState === "done").map((e: Json) => e.executionId);
  const decide = (o: string) => run(async () => { await api.decide(hid, o, rationale, evidence); setRationale(""); await refresh(); });
  const label: Record<string, string> = { accept: "Aceitar", reject: "Rejeitar", defer: "Adiar" };
  return (
    <div style={{ marginTop: 16 }}>
      <h3>Decisão sobre a hipótese</h3>
      {canDecide && <>
        <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Justificativa (obrigatória)" />
        <div className="row" style={{ marginTop: 8 }}>
          {Object.keys(label).map((o) => <button key={o} className={o === "accept" ? "primary" : ""} disabled={busy || !rationale.trim()} onClick={() => decide(o)}>{label[o]}</button>)}
          <span className="muted">Aceitar não aprova mudança em produção.</span>
        </div></>}
      {[...rec.decisions].reverse().map((d: Json, i: number) => (
        <div className="card" key={d.decisionId} style={{ opacity: i === 0 ? 1 : 0.6, marginTop: 8 }}>
          <span className={`badge ${d.outcome === "accept" ? "b-ok" : d.outcome === "reject" ? "b-err" : "b-state"}`}>{label[d.outcome]}</span>{" "}
          <b>{d.rationale}</b><br /><span className="muted">{d.decidedBy} · {new Date(d.decidedAt).toLocaleString("pt-BR")} · evidências {d.evidenceRefs.join(", ") || "—"}{d.supersedes && ` · substitui ${d.supersedes}`}{i === 0 ? " · vigente" : ""}</span>
        </div>
      ))}
    </div>
  );
}

function Audit({ hid, events, metrics }: { hid: string; events: number; metrics: Json }) {
  const [trail, setTrail] = useState<Json[] | null>(null);
  return (
    <div style={{ marginTop: 16 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Trilha de auditoria ({events} eventos, só acréscimo)</h3>
        <button className="ghost" onClick={async () => setTrail(trail ? null : await api.audit(hid))}>{trail ? "Ocultar" : "Ver eventos"}</button>
      </div>
      <p className="muted">Hipótese → primeira evidência: {metrics.hypothesisToEvidenceSeconds != null ? `${metrics.hypothesisToEvidenceSeconds}s` : "—"} ·
        findings relevantes: {metrics.relevantFindingShare != null ? `${Math.round(metrics.relevantFindingShare * 100)}%` : "—"} · tokens de modelo: {metrics.modelTokens ?? 0}</p>
      {trail && <table><thead><tr><th>#</th><th>Evento</th><th>Quem</th><th>Quando</th></tr></thead>
        <tbody>{trail.map((e) => <tr key={e.seq}><td>{e.seq}</td><td className="mono">{e.type}</td><td>{e.actor}</td><td>{new Date(e.at).toLocaleString("pt-BR")}</td></tr>)}</tbody></table>}
    </div>
  );
}
