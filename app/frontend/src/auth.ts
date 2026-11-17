// Login. Local: identidade de demo escolhida na tela. AWS: Cognito Hosted UI com Authorization Code + PKCE.
// A configuração vem de /config.json, gerado pelo deploy; sem ele, assume modo local.

export type AppConfig = { auth: "local" | "cognito"; cognitoDomain?: string; clientId?: string; redirectUri?: string };

let cached: AppConfig | null = null;

export async function getConfig(): Promise<AppConfig> {
  if (cached) return cached;
  try {
    const r = await fetch("/config.json", { cache: "no-store" });
    cached = r.ok ? await r.json() : { auth: "local" };
  } catch {
    cached = { auth: "local" };
  }
  return cached!;
}

const b64url = (buf: ArrayBuffer | Uint8Array) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export async function login(cfg: AppConfig): Promise<void> {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));
  sessionStorage.setItem("pp.pkce", JSON.stringify({ verifier, state }));
  const p = new URLSearchParams({ client_id: cfg.clientId!, response_type: "code", scope: "openid email profile",
    redirect_uri: cfg.redirectUri!, code_challenge: challenge, code_challenge_method: "S256", state });
  window.location.assign(`https://${cfg.cognitoDomain}/oauth2/authorize?${p}`);
}

/** Na volta do Hosted UI: troca o código pelo id_token. */
export async function completeLogin(cfg: AppConfig): Promise<void> {
  const q = new URLSearchParams(window.location.search);
  const code = q.get("code");
  const saved = JSON.parse(sessionStorage.getItem("pp.pkce") || "null");
  if (!code || !saved) return;
  history.replaceState(null, "", window.location.pathname);
  sessionStorage.removeItem("pp.pkce");
  if (q.get("state") !== saved.state) throw new Error("Estado de login inválido");
  const body = new URLSearchParams({ grant_type: "authorization_code", client_id: cfg.clientId!, code,
    redirect_uri: cfg.redirectUri!, code_verifier: saved.verifier });
  const r = await fetch(`https://${cfg.cognitoDomain}/oauth2/token`, { method: "POST", body,
    headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  if (!r.ok) throw new Error("Falha ao concluir o login");
  const tok = await r.json();
  sessionStorage.setItem("pp.idToken", tok.id_token);
}

export function tokenClaims(): Record<string, unknown> | null {
  const t = sessionStorage.getItem("pp.idToken");
  if (!t) return null;
  try {
    const claims = JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (claims.exp * 1000 < Date.now()) {
      sessionStorage.removeItem("pp.idToken");
      return null;
    }
    return claims;
  } catch {
    return null;
  }
}

export function logout(cfg: AppConfig): void {
  sessionStorage.removeItem("pp.idToken");
  const p = new URLSearchParams({ client_id: cfg.clientId!, logout_uri: cfg.redirectUri! });
  window.location.assign(`https://${cfg.cognitoDomain}/logout?${p}`);
}
