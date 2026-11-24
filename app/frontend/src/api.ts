// Cliente da API. Toda mudança de estado manda Idempotency-Key (tech.md).
import { getConfig } from "./auth";

export type Json = any; // eslint-disable-line @typescript-eslint/no-explicit-any

let demoIdentity = { user: "especialista.demo", roles: "Policy Specialist" };
export function setDemoIdentity(user: string, roles: string) {
  demoIdentity = { user, roles };
}

async function headers(): Promise<Record<string, string>> {
  const cfg = await getConfig();
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (cfg.auth === "cognito") {
    const token = sessionStorage.getItem("pp.idToken");
    if (token) h.Authorization = `Bearer ${token}`;
  } else {
    h["X-Demo-User"] = demoIdentity.user;
    h["X-Demo-Roles"] = demoIdentity.roles;
  }
  return h;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call(method: string, path: string, body?: unknown): Promise<Json> {
  const h = await headers();
  if (method !== "GET") h["Idempotency-Key"] = crypto.randomUUID();
  const r = await fetch(path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.detail || `Erro ${r.status}`);
  return data;
}

export const api = {
  health: () => call("GET", "/api/health"),
  me: () => call("GET", "/api/me"),
  policy: () => call("GET", "/api/policy"),
  preview: (overrides: Record<string, number>) => call("POST", "/api/preview", { overrides }),
  hypotheses: () => call("GET", "/api/hypotheses"),
  createHypothesis: (intent: string, overrides?: Record<string, number>) => call("POST", "/api/hypotheses", { intent, overrides }),
  hypothesis: (id: string) => call("GET", `/api/hypotheses/${id}`),
  audit: (id: string) => call("GET", `/api/hypotheses/${id}/audit`),
  confirm: (id: string, overrides: Record<string, number>) => call("POST", `/api/hypotheses/${id}/scenarios`, { overrides }),
  execute: (id: string) => call("POST", `/api/hypotheses/${id}/executions`, {}),
  execution: (eid: string) => call("GET", `/api/executions/${eid}`),
  suggest: (id: string) => call("POST", `/api/hypotheses/${id}/suggestions`),
  investigate: (id: string) => call("POST", `/api/hypotheses/${id}/investigations`),
  generateChangePackage: (id: string) => call("POST", `/api/hypotheses/${id}/change-package`),
  changePackage: (id: string, pid: string) => call("GET", `/api/hypotheses/${id}/change-package/${pid}`),
  transition: (id: string, fid: string, to: string, reason?: string) =>
    call("POST", `/api/hypotheses/${id}/findings/${fid}/transitions`, { to, reason }),
  executeFinding: (id: string, fid: string) => call("POST", `/api/hypotheses/${id}/findings/${fid}/executions`),
  assess: (id: string, fid: string, relevant: boolean) => call("POST", `/api/hypotheses/${id}/findings/${fid}/assessments`, { relevant }),
  decide: (id: string, outcome: string, rationale: string, evidenceRefs: string[]) =>
    call("POST", `/api/hypotheses/${id}/decisions`, { outcome, rationale, evidenceRefs }),
};

/** Consulta até o job terminar (decisão D-DQ4: polling, sem WebSocket). */
export async function poll<T>(fn: () => Promise<T>, done: (v: T) => boolean, everyMs = 800, maxTries = 40): Promise<T> {
  for (let i = 0; i < maxTries; i++) {
    const v = await fn();
    if (done(v)) return v;
    await new Promise((r) => setTimeout(r, everyMs));
  }
  throw new Error("O job demorou mais que o esperado. Atualize a hipótese em instantes.");
}
