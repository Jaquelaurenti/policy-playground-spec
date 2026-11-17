// Textos de negócio para o usuário final. Os IDs técnicos continuam na API e na auditoria;
// aqui só traduzimos o que aparece na tela.
import type { Json } from "./api";

export const fmt = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
export const signed = (n: number) => (n > 0 ? "+" : n < 0 ? "−" : "") + fmt(Math.abs(n));
export const pct = (from: number, to: number) => (from === 0 ? null : Math.round(((to - from) / from) * 100));

const PARAM_LABEL: Record<string, string> = {
  renda_minima: "Renda mínima",
  comprometimento_max_pct: "Comprometimento máximo da renda",
};

const humanize = (s: string) => {
  const t = s.replace(/_/g, " ").toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

export const paramLabel = (p: Json) => PARAM_LABEL[p?.name] ?? humanize(p?.name ?? "");

/** Valor com unidade no formato que o usuário lê: R$ 2.500, 35%. */
export const money = (v: number) => `R$ ${fmt(v)}`;
export function withUnit(v: number, unit?: string) {
  if (unit === "BRL") return money(v);
  if (unit === "%") return `${fmt(v)}%`;
  return unit ? `${fmt(v)} ${unit}` : fmt(v);
}

const OUTCOME_LABEL: Record<string, string> = {
  APROVACAO_SIMULADA: "Aprovadas",
  REPROVACAO_SIMULADA: "Reprovadas",
};
export const outcomeLabel = (k: string) => OUTCOME_LABEL[k] ?? humanize(k.replace(/_SIMULADA$/, ""));

const OUTPUT_LABEL: Record<string, string> = { resultado: "Resultado", limite_sugerido: "Limite sugerido" };
export const outputLabel = (k: string) => OUTPUT_LABEL[k] ?? humanize(k);

export const AREA_LABEL: Record<string, string> = {
  Extraction: "Coleta de dados",
  "Hard filters": "Filtros eliminatórios",
  ETL: "Preparação",
  "Final base": "Decisão final",
};

export const LOGIC_LABEL: Record<string, string> = {
  case_when: "Regra condicional (se… então…)",
  json_extract: "Leitura de um dado da proposta",
  matrix_lookup: "Consulta a uma tabela de oferta",
};

export const ruleName = (policy: Json, id: string) =>
  policy.rules.find((r: Json) => r.id === id)?.name ?? (policy.parameters.find((p: Json) => p.id === id) ? paramLabel(policy.parameters.find((p: Json) => p.id === id)) : id);

export const ROLES: { value: string; label: string; can: string }[] = [
  { value: "Policy Specialist", label: "Especialista de política", can: "cria hipóteses, simula e decide" },
  { value: "Risk Approver", label: "Aprovador de risco", can: "consulta e registra decisões" },
  { value: "Data Analyst", label: "Analista de dados", can: "somente consulta" },
  { value: "Viewer", label: "Leitor", can: "somente consulta" },
];

export const FINDING_STATE: Record<string, string> = {
  suggested: "Nova sugestão",
  under_investigation: "Em análise",
  executed: "Simulada",
  accepted: "Aceita",
  rejected: "Descartada",
};

export const EXAMPLES = [
  "Subir a renda mínima de R$ 2.500 para R$ 3.000",
  "Baixar a renda mínima para R$ 2.000",
  "Reduzir o comprometimento máximo da renda para 30%",
];
