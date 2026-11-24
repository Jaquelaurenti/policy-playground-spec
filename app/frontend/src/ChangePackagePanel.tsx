// Pacote para engenharia (R10.2, R11, R12 na forma do MVP): depois do aceite, gera um artefato
// determinístico e NÃO SUBMETIDO com o diff do Policy Spec, os testes de regressão já conferidos
// pelo motor, o manifesto de rastreabilidade e a prévia do PR.
import { useEffect, useState } from "react";
import { api, type Json } from "./api";

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ChangePackagePanel({ rec, canWrite, refresh }: { rec: Json; canWrite: boolean; refresh: () => Promise<void> }) {
  const hid = rec.hypothesis.hypothesisId;
  const latest = rec.decisions.length ? rec.decisions[rec.decisions.length - 1] : null;
  const summary = (rec.changePackages || []).find((p: Json) => latest && p.decisionId === latest.decisionId);
  const [pkg, setPkg] = useState<Json | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showPr, setShowPr] = useState(false);

  useEffect(() => {
    setPkg(null);
    if (summary) api.changePackage(hid, summary.packageId).then(setPkg).catch(() => setPkg(null));
  }, [hid, summary?.packageId]);

  if (!latest || latest.outcome !== "accept") return null;

  const generate = async () => {
    setErr(null); setBusy(true);
    try { setPkg(await api.generateChangePackage(hid)); await refresh(); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  const changes = pkg ? pkg.patch.filter((op: Json) => op.op === "replace").map((op: Json) => op._meta) : [];
  const muda = pkg ? pkg.tests.filter((t: Json) => t.kind === "muda") : [];

  return (
    <section className="section">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Pacote para engenharia</h3>
        {canWrite && !pkg && <button className="primary" disabled={busy} onClick={generate}>{busy ? "Gerando…" : "Gerar pacote"}</button>}
      </div>
      {!pkg && <p className="muted">
        A hipótese foi aceita. O pacote reúne a mudança no Policy Spec, os testes de regressão conferidos pelo motor
        e a prévia do pull request. Ele não é enviado a lugar nenhum.
      </p>}
      {err && <div className="callout err" style={{ marginTop: 8 }}>{err}</div>}
      {pkg && <div className="card">
        <div className="row">
          <span className="badge b-state">Não submetido</span>
          <span className="badge b-sim">SIMULADO</span>
          <span className={`badge ${pkg.verification.ok ? "b-ok" : "b-err"}`}>
            {pkg.verification.passed}/{pkg.verification.total} testes passaram
          </span>
          <span className="spacer" />
          <span className="muted mono">{pkg.packageId}</span>
        </div>

        <p style={{ margin: "10px 0 4px" }}><b>Mudança no Policy Spec</b></p>
        {changes.map((c: Json) => <div key={c.parameterId} className="change">
          <span className="clabel">{c.name} <span className="muted mono">{c.parameterId}</span></span>
          <span className="from">{c.from} {c.unit}</span><span className="arrow">→</span><span className="to">{c.to} {c.unit}</span>
        </div>)}

        <p style={{ margin: "12px 0 4px" }}><b>Testes de regressão</b> <span className="muted">· {pkg.verification.method}</span></p>
        <table>
          <thead><tr><th>Proposta</th><th>O que muda</th><th>Conferido</th></tr></thead>
          <tbody>
            {muda.map((t: Json) => {
              const r = pkg.verification.results.find((x: Json) => x.recordId === t.recordId);
              return <tr key={t.recordId}><td className="mono">{t.recordId}</td>
                <td>{Object.entries(t.changes).map(([o, v]: [string, Json]) => `${o}: ${v.antes} → ${v.depois}`).join(" · ")}</td>
                <td>{r?.passed ? "✓" : "✗"}</td></tr>;
            })}
            <tr><td colSpan={2} className="muted">{pkg.tests.length - muda.length} propostas sem mudança (não regressão)</td>
              <td>{pkg.verification.results.filter((r: Json) => !muda.some((t: Json) => t.recordId === r.recordId)).every((r: Json) => r.passed) ? "✓" : "✗"}</td></tr>
          </tbody>
        </table>

        <p style={{ margin: "12px 0 4px" }}><b>Rastreabilidade</b></p>
        <div className="kv">
          <div>Decisão</div><div>{pkg.manifest.decision.decidedBy} · <span className="mono">{pkg.manifest.decision.decisionId}</span></div>
          <div>Evidência</div><div className="mono">{pkg.manifest.evidence.executionId} · {pkg.manifest.versions.runner}</div>
          <div>Achados aceitos</div><div>{pkg.manifest.findingsAccepted.length}</div>
          <div>Política após a mudança</div><div className="mono">{pkg.manifest.versions.patchedPolicy}</div>
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={() => setShowPr(!showPr)}>{showPr ? "Ocultar prévia do PR" : "Ver prévia do PR"}</button>
          <button className="ghost" onClick={() => download(`pacote-${hid}.json`, JSON.stringify(pkg, null, 2), "application/json")}>Baixar pacote (.json)</button>
          <button className="ghost" onClick={() => download(pkg.testFile.path.split("/").pop(), pkg.testFile.content, "text/x-python")}>Baixar testes (.py)</button>
        </div>
        {showPr && <div className="card" style={{ marginTop: 10 }}>
          <b>{pkg.pullRequest.title}</b>
          <div className="muted">Destino: {pkg.pullRequest.target}</div>
          <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "8px 0 0" }}>{pkg.pullRequest.body}</pre>
        </div>}
      </div>}
    </section>
  );
}
