import { useCallback, useEffect, useMemo, useState } from "react";
import { api, poll, setDemoIdentity, type Json } from "./api";
import { AgentPanel } from "./AgentPanel";
import { completeLogin, getConfig, login, logout, tokenClaims, type AppConfig } from "./auth";
import PolicyGraph, { AREA_COLOR } from "./PolicyGraph";
import {
  AREA_LABEL, EXAMPLES, FINDING_STATE, LOGIC_LABEL, ROLES, fmt, money, outcomeLabel, outputLabel, paramLabel, pct, ruleName,
  signed, withUnit,
} from "./labels";

type Run = (label: string, fn: () => Promise<unknown>) => void;

export function EvidenceBadge({ level }: { level: string }) {
  if (level === "simulated") return <span className="badge b-sim" title="Calculado sobre dados sintéticos — não é impacto real">SIMULADO</span>;
  if (level === "study_validated") return <span className="badge b-valid">Validado por estudo</span>;
  return <span className="badge b-none">Ainda sem evidência</span>;
}
const SimTag = () => <span className="badge b-sim tiny" title="Número simulado sobre dados sintéticos">SIM</span>;
const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

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
      <div className="brand" style={{ color: "var(--ink)" }}>Policy <span>Playground</span></div>
      <p className="muted">Teste mudanças na política de crédito e veja o impacto antes de decidir. Ambiente de demonstração com dados 100% sintéticos.</p>
      {error && <div className="callout err">{error}</div>}
      <button className="primary" onClick={() => login(cfg)}>Entrar</button>
    </div>
  );
  return <Workspace cfg={cfg} role={role} setRole={setRole} />;
}

function Workspace({ cfg, role, setRole }: { cfg: AppConfig; role: string; setRole: (r: string) => void }) {
  const [policy, setPolicy] = useState<Json | null>(null);
  const [me, setMe] = useState<Json | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [list, setList] = useState<Json[]>([]);
  const [hid, setHid] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const [rec, setRec] = useState<Json | null>(null);
  const [focus, setFocus] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refreshList = useCallback(async () => {
    const l = await api.hypotheses();
    setList(l);
    return l as Json[];
  }, []);
  const refresh = useCallback(async (id = hid) => { if (id) setRec(await api.hypothesis(id)); }, [hid]);

  useEffect(() => {
    (async () => {
      try {
        setPolicy(await api.policy());
        setMe(await api.me());
        const l = await refreshList();
        setHid((cur) => cur ?? l[0]?.hypothesisId ?? null);
      } catch (e) { setErr(String((e as Error).message)); }
    })();
  }, [role, refreshList]);
  useEffect(() => { if (hid) refresh(hid); else setRec(null); }, [hid, refresh]);

  const run: Run = async (label, fn) => {
    setErr(null); setBusy(label);
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };

  const highlight = useMemo(() => {
    const sub = rec?.scenarios?.at(-1)?.affectedSubDag || rec?.hypothesis?.potentialImpact;
    if (!sub) return new Set<string>();
    return new Set<string>([...sub.changedParams, ...sub.executionSet, ...sub.path.flat()]);
  }, [rec]);

  if (!policy) return <div style={{ padding: 20 }}>{err ? <div className="callout err">{err}</div> : "Carregando a política…"}</div>;
  const canWrite = !!me?.roles?.includes("Policy Specialist");
  const canDecide = !!me?.roles?.some((r: string) => ["Policy Specialist", "Risk Approver"].includes(r));
  const roleInfo = ROLES.find((r) => r.value === role);
  const showComposer = composing || !hid;

  return (
    <>
      <div className="topbar">
        <div className="brand">Policy <span>Playground</span></div>
        <div className="meta">{policy.policy.name}</div>
        <div className="spacer" />
        {cfg.auth === "local" ? (
          <label className="role">
            <span>Você está como</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
            {roleInfo && <small>{roleInfo.can}</small>}
          </label>
        ) : <span className="meta">{me?.id} · {me?.roles?.map((r: string) => ROLES.find((x) => x.value === r)?.label ?? r).join(", ")}</span>}
        {cfg.auth === "cognito" && <button onClick={() => logout(cfg)}>Sair</button>}
      </div>
      <div className="banner">
        <span className="badge b-sim">SIMULADO</span>
        Os números vêm de um cálculo determinístico sobre <b>propostas fictícias</b>, não são impacto real. A IA só sugere o que olhar; quem decide é você.
      </div>
      {err && <div className="toast err" role="alert"><span>{err}</span><button className="ghost" onClick={() => setErr(null)} aria-label="Fechar">✕</button></div>}

      <div className="shell">
        <aside className="side">
          {canWrite && <button className="primary block" onClick={() => { setComposing(true); setHid(null); }}>+ Nova hipótese</button>}
          <h2>Suas hipóteses</h2>
          {list.length === 0 && <p className="muted">Nenhuma hipótese ainda.</p>}
          <div className="hlist">
            {list.map((h) => (
              <button key={h.hypothesisId} className={h.hypothesisId === hid && !composing ? "sel" : ""} onClick={() => { setComposing(false); setHid(h.hypothesisId); }}>
                <span className="htitle">{h.intent}</span>
                <span className="muted">{h.createdBy} · {when(h.createdAt)}</span>
              </button>
            ))}
          </div>
        </aside>

        <main className="stack">
          {showComposer ? (
            <Composer policy={policy} canWrite={canWrite} busy={busy} roleLabel={roleInfo?.label}
              onCreate={(intent) => run("Analisando a hipótese…", async () => {
                const r = await api.createHypothesis(intent);
                setComposing(false); setHid(r.hypothesis.hypothesisId); setRec(r); await refreshList();
              })} />
          ) : rec ? (
            <Investigation key={rec.hypothesis.hypothesisId} policy={policy} rec={rec} canWrite={canWrite} canDecide={canDecide}
              busy={busy} run={run} refresh={() => refresh(rec.hypothesis.hypothesisId)} setFocus={setFocus} />
          ) : <div className="panel muted">Carregando a hipótese…</div>}

          <details className="panel" open>
            <summary><h2>Mapa da política</h2><span className="muted">como as regras se conectam</span></summary>
            {!policy.validation.ok && <div className="callout err">A política carregada tem erros: {policy.validation.errors.join("; ")}</div>}
            <p className="muted" style={{ marginTop: 0 }}>
              {highlight.size ? "Em rosa, o caminho que a hipótese aberta pode afetar. " : ""}Clique numa caixa para ver o que ela faz.
            </p>
            <PolicyGraph policy={policy} highlight={highlight} focus={focus} onSelect={setSelected} />
            <div className="legend">
              <span><i style={{ background: "#7a4dd8" }} />Parâmetro ajustável</span>
              {Object.entries(AREA_COLOR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{AREA_LABEL[k] ?? k}</span>)}
              <span><i style={{ background: "#14161b" }} />Saída da política</span>
            </div>
            {selected && <RuleDetail policy={policy} id={selected} onClose={() => setSelected(null)} />}
          </details>
        </main>
      </div>
    </>
  );
}

function Composer({ policy, canWrite, busy, roleLabel, onCreate }: {
  policy: Json; canWrite: boolean; busy: string | null; roleLabel?: string; onCreate: (intent: string) => void }) {
  const [intent, setIntent] = useState("");
  const editable = policy.parameters.filter((p: Json) => p.editable);
  if (!canWrite) return (
    <div className="panel">
      <h3>Escolha uma hipótese na lista</h3>
      <p className="muted">Como {roleLabel ?? "este perfil"}, você pode consultar as hipóteses e os resultados, mas não criar novas. Para criar, troque o perfil para <b>Especialista de política</b> no topo da tela.</p>
    </div>
  );
  return (
    <div className="panel">
      <h3>O que você quer testar?</h3>
      <p className="muted" style={{ marginTop: 0 }}>Descreva a mudança com suas palavras. Você confere a proposta antes de qualquer simulação.</p>
      <textarea value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="Ex.: Subir a renda mínima para R$ 3.000" disabled={!!busy} autoFocus
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && intent.trim()) onCreate(intent); }} />
      <div className="chips">
        <span className="muted">Exemplos:</span>
        {EXAMPLES.map((x) => <button key={x} className="chip" disabled={!!busy} onClick={() => setIntent(x)}>{x}</button>)}
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" disabled={!!busy || !intent.trim()} onClick={() => onCreate(intent)}>{busy ?? "Continuar"}</button>
        <span className="muted">Hoje dá para ajustar: {editable.map((p: Json) => paramLabel(p)).join(" e ")}.</span>
      </div>
      <ol className="howto">
        <li><b>Descreva</b> a mudança que quer testar.</li>
        <li><b>Confira</b> o valor proposto e simule sobre as propostas fictícias.</li>
        <li><b>Analise</b> o impacto, peça sugestões do que mais olhar e <b>registre sua decisão</b>.</li>
      </ol>
    </div>
  );
}

const STEPS = ["Descrever", "Conferir e simular", "Ver impacto", "Investigar mais", "Decidir"];
const HINT: Record<number, string> = {
  2: "Confira o parâmetro e o novo valor abaixo. Se estiver certo, clique em Simular cenário.",
  3: "Veja o impacto abaixo. Depois, peça sugestões do que mais analisar ou registre sua decisão no fim da página.",
  4: "Analise as sugestões e, quando tiver segurança, registre a decisão no fim da página.",
  5: "Decisão registrada. Você pode ajustar o cenário, simular de novo e registrar uma nova decisão.",
};

function Investigation({ policy, rec, canWrite, canDecide, busy, run, refresh, setFocus }: {
  policy: Json; rec: Json; canWrite: boolean; canDecide: boolean; busy: string | null; run: Run;
  refresh: () => Promise<void>; setFocus: (s: Set<string>) => void }) {
  const h = rec.hypothesis;
  const hid = h.hypothesisId;
  const proposal = h.structuring;
  const editable = policy.parameters.filter((p: Json) => p.editable);
  const lastScenario = rec.scenarios.at(-1);
  const initialParam = proposal.parameterId || Object.keys(h.proposedOverrides)[0] || (lastScenario && Object.keys(lastScenario.overrides)[0]) || editable[0]?.id;
  const [paramId, setParamId] = useState<string>(initialParam);
  const param = policy.parameters.find((p: Json) => p.id === paramId);
  const [value, setValue] = useState<number>(lastScenario?.overrides[paramId] ?? h.proposedOverrides[paramId] ?? param?.value ?? 0);
  const [execution, setExecution] = useState<Json | null>(null);

  const lastExec = rec.executions.filter((e: Json) => !e.findingId && e.source !== "agent").at(-1);   // execuções do agente aparecem no painel dele
  useEffect(() => { if (lastExec?.jobState === "done") api.execution(lastExec.executionId).then(setExecution); }, [lastExec?.executionId, lastExec?.jobState]);

  const step = rec.decisions.length ? 5 : rec.findings.length ? 4 : lastExec?.jobState === "done" ? 3 : 2;
  const inRange = param && value >= param.domain.min && value <= param.domain.max;
  const changed = param && value !== param.value;

  const simulate = () => run("Simulando…", async () => {
    const same = lastScenario && Object.keys(lastScenario.overrides).length === 1 && lastScenario.overrides[param.id] === value;
    if (!same) { await api.confirm(hid, { [param.id]: value }); }
    const r = await api.execute(hid);
    await refresh();
    const done = await poll(() => api.execution(r.executionId), (x: Json) => x.jobState === "done");
    setExecution(done); await refresh();
  });

  const impact = h.potentialImpact;
  return (
    <div className="panel">
      <div className="steps">{STEPS.map((s, i) => <span key={s} className={`step ${i + 1 === step ? "on" : i + 1 < step ? "done" : ""}`}>{i + 1 < step ? "✓" : i + 1}. {s}</span>)}</div>
      <h3 className="title">{h.intent}</h3>
      {HINT[step] && <div className="hint">{HINT[step]}</div>}

      <div className="card">
        <b>O que muda</b>
        {!proposal.understood && <div className="callout warn" style={{ margin: "8px 0" }}>Não consegui identificar o parâmetro no texto. Escolha abaixo o que você quer ajustar.</div>}
        {proposal.understood && proposal.message && <div className="callout warn" style={{ margin: "8px 0" }}>Entendi o parâmetro, mas não o novo valor. Ajuste o valor abaixo.</div>}
        {(!proposal.understood && canWrite) && (
          <select value={paramId} onChange={(e) => { const p = policy.parameters.find((x: Json) => x.id === e.target.value); setParamId(e.target.value); setValue(p?.value ?? 0); }} style={{ marginTop: 6 }}>
            {editable.map((p: Json) => <option key={p.id} value={p.id}>{paramLabel(p)} (hoje {withUnit(p.value, p.unit)})</option>)}
          </select>
        )}
        {param && <div className="change">
          <span className="clabel">{paramLabel(param)}</span>
          {changed ? <>
            <span className="from">{withUnit(param.value, param.unit)}</span>
            <span className="arrow">→</span>
            <span className="to">{withUnit(value, param.unit)}</span>
          </> : <span className="muted">hoje {withUnit(param.value, param.unit)} · escolha o novo valor</span>}
        </div>}
        {param?.editable && canWrite && <div className="slider">
          <span className="muted">{withUnit(param.domain.min, param.unit)}</span>
          <input type="range" min={param.domain.min} max={param.domain.max} step={param.domain.step} value={value} onChange={(e) => setValue(+e.target.value)} aria-label={`Novo valor de ${paramLabel(param)}`} />
          <span className="muted">{withUnit(param.domain.max, param.unit)}</span>
          <input type="number" min={param.domain.min} max={param.domain.max} step={param.domain.step} value={value} onChange={(e) => setValue(+e.target.value)} aria-label="Valor exato" />
        </div>}
        {param && !inRange && <div className="callout err" style={{ marginTop: 8 }}>Use um valor entre {withUnit(param.domain.min, param.unit)} e {withUnit(param.domain.max, param.unit)}.</div>}
        {impact && <p className="muted" style={{ marginBottom: 0 }}>
          Pode afetar as regras <b>{impact.executionSet.map((id: string) => ruleName(policy, id)).join(" → ")}</b>, o <b>{impact.affectedOutputs.map(outputLabel).join(", ").toLowerCase()}</b>
          {impact.affectedMotivos.length > 0 && <> e o motivo de recusa <b>{impact.affectedMotivos.map((m: Json) => m.name).join(", ")}</b></>}.
          {" "}Isso é o caminho na política, ainda não é resultado.
        </p>}
        {canWrite ? <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" disabled={!!busy || !param || !inRange || !changed} onClick={simulate}>{busy === "Simulando…" ? "Simulando…" : lastExec ? "Simular de novo" : "Simular cenário"}</button>
          <span className="muted">{!changed ? "Escolha um valor diferente do atual para simular." : "Nada é simulado sem o seu clique."}</span>
        </div> : <p className="muted">Seu perfil só consulta: a simulação é feita pelo Especialista de política.</p>}
      </div>

      {lastExec && lastExec.jobState !== "done" && <div className="callout" style={{ marginTop: 12 }}><span className="spinner" /> Calculando o impacto…</div>}
      {execution && <ResultSummary policy={policy} ex={execution} />}

      {lastExec && <AgentPanel rec={rec} canWrite={canWrite} refresh={refresh} />}
      {lastExec && <Findings policy={policy} rec={rec} canWrite={canWrite} busy={busy} run={run} refresh={refresh} setFocus={setFocus} />}
      {lastExec && <Decisions rec={rec} canDecide={canDecide} busy={busy} run={run} refresh={refresh} />}

      <details className="more">
        <summary>Histórico e detalhes técnicos</summary>
        <div className="kv" style={{ marginTop: 8 }}>
          <div>Hipótese</div><div className="mono">{hid}</div>
          <div>Versão da política</div><div className="mono">{h.policyVersion}</div>
          <div>Base de dados</div><div className="mono">{h.datasetVersion}</div>
          {lastScenario && <><div>Cenário confirmado</div><div>{lastScenario.scenarioId} por {lastScenario.confirmedBy}</div></>}
        </div>
        <Audit hid={hid} events={rec.events} metrics={rec.metrics} />
      </details>
    </div>
  );
}

function ResultSummary({ policy, ex }: { policy: Json; ex: Json }) {
  if (ex.status !== "ok") return <div className="callout err" style={{ marginTop: 12 }}>Não foi possível calcular este cenário: {ex.reason}. Nenhum número parcial é mostrado.</div>;
  const c = ex.comparison;
  const res = c.outputs.resultado;
  const keys = Object.keys(res.baseline);
  const approved = keys.find((k) => k.includes("APROVA"));
  const motivos = Object.entries(c.motivos as Record<string, Json>).map(([code, m]) => ({ code, ...m, delta: m.scenario - m.baseline }));
  const top = [...motivos].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0];
  const limitDelta = c.approvedLimitSum.scenario - c.approvedLimitSum.baseline;
  const aDelta = approved ? res.scenario[approved] - res.baseline[approved] : 0;

  const sentence = [
    `${res.changedRecords.length} de ${c.records} propostas mudariam de resultado`,
    approved && aDelta !== 0 ? `${Math.abs(aDelta)} ${aDelta < 0 ? "aprovações a menos" : "aprovações a mais"}` : null,
    limitDelta !== 0 ? `o limite total aprovado ${limitDelta < 0 ? "cairia" : "subiria"} ${money(Math.abs(limitDelta))}` : null,
  ].filter(Boolean).join(", ") + ".";

  return (
    <div className="result">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Impacto simulado</h3>
        <span className="row"><EvidenceBadge level={ex.evidenceLevel} />{ex.reused && <span className="badge b-state" title="O mesmo cenário já tinha sido calculado">resultado reaproveitado</span>}</span>
      </div>
      <p className="lead">{sentence}</p>
      <div className="stats">
        {keys.map((k) => {
          const d = res.scenario[k] - res.baseline[k];
          const good = k === approved ? d > 0 : d < 0;
          const p = pct(res.baseline[k], res.scenario[k]);
          return <div className="stat" key={k}>
            <span className="slabel">{outcomeLabel(k)} <SimTag /></span>
            <span className="sval">{res.baseline[k]} → <b>{res.scenario[k]}</b></span>
            <span className={d === 0 ? "muted" : good ? "delta-up" : "delta-down"}>{d === 0 ? "sem mudança" : `${signed(d)}${p != null ? ` (${signed(p)}%)` : ""}`}</span>
          </div>;
        })}
        <div className="stat">
          <span className="slabel">Limite total dos aprovados <SimTag /></span>
          <span className="sval">{money(c.approvedLimitSum.baseline)} → <b>{money(c.approvedLimitSum.scenario)}</b></span>
          <span className={limitDelta === 0 ? "muted" : limitDelta > 0 ? "delta-up" : "delta-down"}>{limitDelta === 0 ? "sem mudança" : `${limitDelta > 0 ? "+" : "−"}${money(Math.abs(limitDelta))}`}</span>
        </div>
        {top && top.delta !== 0 && <div className="stat">
          <span className="slabel">Motivo de recusa que mais mudou <SimTag /></span>
          <span className="sval"><b>{top.name}</b></span>
          <span className={top.delta > 0 ? "delta-down" : "delta-up"}>{top.baseline} → {top.scenario} propostas</span>
        </div>}
      </div>

      <details className="more">
        <summary>Ver números completos e propostas afetadas</summary>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Motivo de recusa</th><th>Hoje</th><th>Com a mudança</th></tr></thead>
          <tbody>{motivos.map((m) => <tr key={m.code}><td>{m.name}</td><td>{m.baseline} <SimTag /></td><td>{m.scenario} <SimTag /></td></tr>)}</tbody>
        </table>
        {res.changedRecords.length > 0 && <>
          <p style={{ marginBottom: 4 }}><b>Propostas que mudaram de resultado</b></p>
          <table><thead><tr><th>Proposta</th><th>Hoje</th><th>Com a mudança</th><th>Faixa</th></tr></thead>
            <tbody>{ex.rows.filter((r: Json) => res.changedRecords.includes(r.recordId)).map((r: Json) =>
              <tr key={r.recordId}><td className="mono">{r.recordId}</td><td>{outcomeLabel(r.baseline.resultado)}</td><td><b>{outcomeLabel(r.scenario.resultado)}</b></td><td className="muted">{r.cobertura}</td></tr>)}</tbody></table>
        </>}
        <p className="muted">Recalculou só {ex.subDag.executionSet.map((id: string) => ruleName(policy, id)).join(", ")} e reaproveitou o resto. Execução {ex.executionId} · {ex.runnerVersion}.</p>
      </details>
    </div>
  );
}

function Findings({ policy, rec, canWrite, busy, run, refresh, setFocus }: { policy: Json; rec: Json; canWrite: boolean; busy: string | null;
  run: Run; refresh: () => Promise<void>; setFocus: (s: Set<string>) => void }) {
  const hid = rec.hypothesis.hypothesisId;
  const pending = rec.suggestionJobs.some((j: Json) => j.state !== "done");
  const ask = () => run("Buscando sugestões…", async () => {
    const j = await api.suggest(hid);
    await poll(() => api.hypothesis(hid), (r: Json) => r.suggestionJobs.some((x: Json) => x.jobId === j.jobId && x.state === "done"));
    await refresh();
  });
  const lastJob = rec.suggestionJobs.at(-1);
  const act = (label: string, fn: () => Promise<unknown>) => run(label, async () => { await fn(); await refresh(); });
  const execFinding = (fid: string) => run("Simulando…", async () => {
    const r = await api.executeFinding(hid, fid);
    await poll(() => api.execution(r.executionId), (x: Json) => x.jobState === "done");
    await refresh();
  });
  return (
    <section className="section">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>O que mais analisar</h3>
        {canWrite && <button disabled={!!busy || pending} onClick={ask}>{busy === "Buscando sugestões…" || pending ? "Buscando sugestões…" : rec.findings.length ? "Buscar mais sugestões" : "Sugerir pontos de atenção"}</button>}
      </div>
      {!lastJob && <p className="muted">Peça sugestões para descobrir efeitos que talvez você não tenha previsto.</p>}
      {lastJob && lastJob.state === "done" && <p className="muted">
        {rec.findings.length === 0 ? "Nenhum ponto de atenção encontrado para este cenário. " : ""}
        {lastJob.modelStatus === "ok" ? "Sugestões da análise da política e do modelo de IA." : "Sugestões geradas pela análise da estrutura da política (IA desligada neste ambiente)."}
      </p>}
      {rec.findings.map((f: Json) => (
        <div className="card" key={f.findingId} onMouseEnter={() => setFocus(new Set(f.ruleRefs))} onMouseLeave={() => setFocus(new Set())}>
          <div className="row">
            {f.source === "agent" ? <span className="badge b-ai">Achado do agente</span> : f.source === "ai_suggestion" ? <span className="badge b-ai">Sugestão da IA</span> : <span className="badge b-det">Análise da política</span>}
            <span className="badge b-state">{FINDING_STATE[f.investigationState]}</span>
            <EvidenceBadge level={f.evidenceLevel} />
          </div>
          <p style={{ margin: "8px 0 4px" }}><b>{f.title}</b></p>
          <p style={{ margin: 0, fontSize: 14 }}>{f.text}</p>
          <p className="muted" style={{ margin: "6px 0" }}>Regras envolvidas: {f.ruleRefs.map((id: string) => ruleName(policy, id)).join(", ")}</p>
          {canWrite && <div className="row">
            {f.investigationState === "suggested" && <button disabled={!!busy} onClick={() => act("Atualizando…", () => api.transition(hid, f.findingId, "under_investigation"))}>Analisar</button>}
            {f.investigationState === "under_investigation" && <button disabled={!!busy} className="primary" onClick={() => execFinding(f.findingId)}>Simular este ponto</button>}
            {f.investigationState === "executed" && <button disabled={!!busy} className="primary" onClick={() => act("Atualizando…", () => api.transition(hid, f.findingId, "accepted", "Aceito após ver a evidência"))}>Aceitar</button>}
            {["executed", "accepted"].includes(f.investigationState) && <button disabled={!!busy} className="ghost" onClick={() => act("Atualizando…", () => api.transition(hid, f.findingId, "under_investigation", "Reabrir"))}>Reabrir</button>}
            {["suggested", "under_investigation", "executed"].includes(f.investigationState) && <button disabled={!!busy} className="ghost" onClick={() => act("Atualizando…", () => api.transition(hid, f.findingId, "rejected", "Descartado"))}>Descartar</button>}
            <span className="spacer" />
            {f.assessment === undefined ? <>
              <span className="muted">Foi útil?</span>
              <button disabled={!!busy} className="ghost" title="Útil" onClick={() => act("Atualizando…", () => api.assess(hid, f.findingId, true))}>👍</button>
              <button disabled={!!busy} className="ghost" title="Não útil" onClick={() => act("Atualizando…", () => api.assess(hid, f.findingId, false))}>👎</button></>
              : <span className="muted">Você marcou como {f.assessment ? "útil" : "não útil"}</span>}
          </div>}
        </div>
      ))}
    </section>
  );
}

function Decisions({ rec, canDecide, busy, run, refresh }: { rec: Json; canDecide: boolean; busy: string | null; run: Run; refresh: () => Promise<void> }) {
  const [rationale, setRationale] = useState("");
  const hid = rec.hypothesis.hypothesisId;
  const evidence = rec.executions.filter((e: Json) => e.jobState === "done").map((e: Json) => e.executionId);
  const decide = (o: string) => run("Registrando…", async () => { await api.decide(hid, o, rationale, evidence); setRationale(""); await refresh(); });
  const label: Record<string, string> = { accept: "Aceitar hipótese", reject: "Rejeitar", defer: "Adiar" };
  const short: Record<string, string> = { accept: "Aceita", reject: "Rejeitada", defer: "Adiada" };
  return (
    <section className="section">
      <h3>Sua decisão</h3>
      {canDecide ? <>
        <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Explique o porquê da decisão. A justificativa é obrigatória e fica no histórico." />
        <div className="row" style={{ marginTop: 8 }}>
          {Object.keys(label).map((o) => <button key={o} className={o === "accept" ? "primary" : ""} disabled={!!busy || !rationale.trim()} onClick={() => decide(o)}>{label[o]}</button>)}
          <span className="muted">{rationale.trim() ? "Aceitar aqui não muda a política em produção." : "Escreva a justificativa para liberar os botões."}</span>
        </div></> : <p className="muted">Seu perfil só consulta. A decisão é do Especialista de política ou do Aprovador de risco.</p>}
      {[...rec.decisions].reverse().map((d: Json, i: number) => (
        <div className="card" key={d.decisionId} style={{ opacity: i === 0 ? 1 : 0.6, marginTop: 8 }}>
          <span className={`badge ${d.outcome === "accept" ? "b-ok" : d.outcome === "reject" ? "b-err" : "b-state"}`}>{short[d.outcome]}</span>{" "}
          {i === 0 && <span className="badge b-state">vigente</span>}
          <p style={{ margin: "6px 0 2px" }}>{d.rationale}</p>
          <span className="muted">{d.decidedBy} · {when(d.decidedAt)}{d.evidenceRefs.length ? ` · com base em ${d.evidenceRefs.length} simulação(ões)` : ""}</span>
        </div>
      ))}
    </section>
  );
}

function Audit({ hid, events, metrics }: { hid: string; events: number; metrics: Json }) {
  const [trail, setTrail] = useState<Json[] | null>(null);
  return (
    <div style={{ marginTop: 12 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b>Trilha de auditoria ({events} eventos)</b>
        <button className="ghost" onClick={async () => setTrail(trail ? null : await api.audit(hid))}>{trail ? "Ocultar" : "Ver eventos"}</button>
      </div>
      <p className="muted">
        Tempo até a primeira evidência: {metrics.hypothesisToEvidenceSeconds != null ? `${fmt(metrics.hypothesisToEvidenceSeconds)}s` : "—"} ·
        sugestões úteis: {metrics.relevantFindingShare != null ? `${Math.round(metrics.relevantFindingShare * 100)}%` : "—"} · tokens de IA: {metrics.modelTokens ?? 0}
      </p>
      {trail && <table><thead><tr><th>#</th><th>Evento</th><th>Quem</th><th>Quando</th></tr></thead>
        <tbody>{trail.map((e) => <tr key={e.seq}><td>{e.seq}</td><td className="mono">{e.type}</td><td>{e.actor}</td><td>{when(e.at)}</td></tr>)}</tbody></table>}
    </div>
  );
}

function RuleDetail({ policy, id, onClose }: { policy: Json; id: string; onClose: () => void }) {
  const close = <button className="ghost" onClick={onClose} aria-label="Fechar detalhe">✕</button>;
  const p = policy.parameters.find((x: Json) => x.id === id);
  if (p) return (
    <div className="card detail">
      <div className="row" style={{ justifyContent: "space-between" }}><h3 style={{ margin: 0 }}>{paramLabel(p)}</h3>{close}</div>
      <div className="kv" style={{ marginTop: 8 }}>
        <div>Valor hoje</div><div><b>{withUnit(p.value, p.unit)}</b></div>
        <div>Usado por</div><div>{p.usedBy.map((r: string) => ruleName(policy, r)).join(", ")}</div>
        <div>Pode ajustar?</div><div>{p.editable ? `Sim, de ${withUnit(p.domain.min, p.unit)} a ${withUnit(p.domain.max, p.unit)}` : "Não, somente leitura"}</div>
        <div>Descrição</div><div>{p.description}</div>
      </div>
    </div>
  );
  const r = policy.rules.find((x: Json) => x.id === id);
  if (!r) return null;
  const motivo = policy.motivos.find((m: Json) => m.rule_id === id);
  return (
    <div className="card detail">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{r.name} <span className="badge b-state">{AREA_LABEL[r.area] ?? r.area ?? "sem área"}</span></h3>{close}
      </div>
      <div className="kv" style={{ marginTop: 8 }}>
        <div>O que faz</div><div>{LOGIC_LABEL[r.logic.type] ?? r.logic.type}</div>
        {r.dependsOn.length > 0 && <><div>Depende de</div><div>{r.dependsOn.map((d: string) => ruleName(policy, d)).join(", ")}</div></>}
        {r.parameters.length > 0 && <><div>Parâmetros</div><div>{r.parameters.map((x: string) => ruleName(policy, x)).join(", ")}</div></>}
        {motivo && <><div>Motivo de recusa</div><div>{motivo.name} (código {motivo.code})</div></>}
        <div>Lê</div><div className="mono">{r.inputs.join(", ") || "dados da proposta"}</div>
        <div>Produz</div><div className="mono">{r.outputs.join(", ")}</div>
      </div>
      <div style={{ marginTop: 10 }}>
        {r.logic.type === "case_when" && <table><thead><tr><th>Quando</th><th>Então</th></tr></thead><tbody>
          {r.logic.branches.map((b: Json, i: number) => <tr key={i}><td className="mono">{b.when}</td><td>{b.then}</td></tr>)}
          <tr><td className="muted">nos demais casos</td><td>{r.logic.else}</td></tr></tbody></table>}
        {r.logic.type === "json_extract" && <p className="muted">Lê o campo <span className="mono">{r.logic.path}</span> da proposta.</p>}
        {r.logic.type === "matrix_lookup" && <table><thead><tr><th>{r.logic.row_key} \ {r.logic.col_key}</th>{r.logic.col_labels.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{Object.entries(r.logic.matrix).map(([row, cols]: [string, Json]) => <tr key={row}><td>{row}</td>{r.logic.col_labels.map((c: string) => <td key={c}>{fmt(cols[c])}</td>)}</tr>)}</tbody></table>}
      </div>
      {r.readOnlyThresholds.length > 0 && <p className="muted">Limites fixos nesta regra (não ajustáveis nesta versão): {r.readOnlyThresholds.join("; ")}</p>}
    </div>
  );
}
