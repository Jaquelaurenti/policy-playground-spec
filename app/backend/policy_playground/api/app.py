"""API HTTP (FastAPI). Em produção-demo roda na Lambda via Lambda Web Adapter; localmente com uvicorn.

Identidade:
- Na AWS, o API Gateway valida o JWT do Cognito; o Lambda Web Adapter repassa o
  requestContext no header `x-amzn-request-context`, de onde vêm `sub`/e-mail e `cognito:groups`.
- Localmente (PP_AUTH=local), usa os headers `X-Demo-User` e `X-Demo-Roles`.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..domain.model import PolicyInvalid, load_from_folder
from ..domain.record import InvalidTransition
from ..service import Actor, Config, Conflict, Forbidden, NotFound, Playground

HERE = Path(__file__).resolve()


def _repo_path(levels: int, *parts: str) -> Path:
    """Caminho relativo à raiz do repo quando roda do código-fonte; na imagem os caminhos vêm por env."""
    parents = HERE.parents
    return parents[levels].joinpath(*parts) if len(parents) > levels else Path("/nonexistent")


def build_playground() -> Playground:
    from ..adapters import memory
    fixtures = Path(os.environ.get("PP_FIXTURES") or _repo_path(4, ".kiro", "specs", "policy-playground", "fixtures"))
    model = load_from_folder(fixtures)
    cfg = Config(suggestion_cap=int(os.environ.get("PP_SUGGESTION_CAP", 5)),
                 max_suggestion_requests=int(os.environ.get("PP_MAX_SUGGESTION_REQUESTS", 3)))
    if os.environ.get("PP_STORE", "memory") == "dynamodb":
        from ..adapters import aws
        table = os.environ["PP_TABLE"]
        events, kv = aws.DynamoEventStore(table), aws.DynamoKV(table)
        audit = aws.S3Audit(os.environ["PP_AUDIT_BUCKET"]) if os.environ.get("PP_AUDIT_BUCKET") else memory.MemoryAudit()
    else:
        events, kv, audit = memory.MemoryEventStore(), memory.MemoryKV(), memory.MemoryAudit()
    model_id = os.environ.get("PP_MODEL_ID", "")
    if model_id:
        from ..adapters import aws
        ai = aws.BedrockModel(model_id)
    else:
        ai = memory.NoModel()
    pg = Playground(model, events, kv, audit, ai, dispatcher=None, config=cfg)
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        from ..adapters import aws
        pg.dispatcher = aws.LambdaSelfDispatcher()
    else:
        pg.dispatcher = memory.ThreadDispatcher(pg.run_job, synchronous=os.environ.get("PP_SYNC_JOBS") == "1")
    return pg


def create_app(pg: Playground | None = None) -> FastAPI:
    state = {}

    def playground() -> Playground:
        if "pg" not in state:
            state["pg"] = pg or build_playground()
        return state["pg"]

    # Servidor MCP do Playground (R17.6): as mesmas tools do agente, para qualquer cliente MCP (ex. Kiro).
    mcp_app, mcp_lifespan = None, None
    if os.environ.get("PP_MCP", "on") != "off":
        try:
            from ..agent.mcp_server import build_mcp_asgi
            mcp_app, mcp_lifespan = build_mcp_asgi(lambda: playground().model, lambda req: actor(req))
        except ImportError as e:                  # pacote mcp ausente ou incompatível: o app segue sem /mcp
            logging.getLogger("policy_playground").warning("Servidor MCP desligado: %s", e)
            mcp_app = None

    app = FastAPI(title="Policy Playground", version="1.0.0", lifespan=mcp_lifespan)

    def actor(request: Request) -> Actor:
        if os.environ.get("PP_AUTH", "local") == "cognito":
            ctx = request.headers.get("x-amzn-request-context")
            claims = {}
            if ctx:
                try:
                    claims = json.loads(ctx).get("authorizer", {}).get("jwt", {}).get("claims", {})
                except ValueError:
                    claims = {}
            if not claims:
                raise HTTPException(401, "Sessão inválida")
            groups = claims.get("cognito:groups", "")
            groups = groups.strip("[]").replace(",", " ").split() if isinstance(groups, str) else groups
            names = {"policy-specialist": "Policy Specialist", "risk-approver": "Risk Approver",
                     "data-analyst": "Data Analyst", "viewer": "Viewer"}
            return Actor(claims.get("email") or claims.get("username") or claims.get("sub", "?"),
                         {names.get(g, g) for g in groups})
        user = request.headers.get("x-demo-user", "especialista.demo")
        roles = request.headers.get("x-demo-roles", "Policy Specialist")
        return Actor(user, {r.strip() for r in roles.split(",") if r.strip()})

    @app.exception_handler(Forbidden)
    async def _forbidden(_, e):
        return JSONResponse({"detail": str(e)}, 403)

    @app.exception_handler(NotFound)
    async def _nf(_, e):
        return JSONResponse({"detail": str(e)}, 404)

    @app.exception_handler(Conflict)
    async def _conf(_, e):
        return JSONResponse({"detail": str(e)}, 409)

    @app.exception_handler(InvalidTransition)
    async def _inv(_, e):
        return JSONResponse({"detail": str(e)}, 409)

    @app.exception_handler(ValueError)
    async def _val(_, e):
        return JSONResponse({"detail": str(e)}, 422)

    @app.exception_handler(PolicyInvalid)
    async def _pol(_, e):
        return JSONResponse({"detail": "Policy Spec inválido: a exploração está bloqueada", "validation": e.report.as_dict()}, 422)

    @app.get("/api/health")
    def health():
        p = playground()
        return {"ok": True, "policyVersion": p.model.policy_version, "model": p.ai.name, "store": os.environ.get("PP_STORE", "memory"),
                "agent": {"enabled": p.ai.name != "none", "mcp": "/mcp/stream" if mcp_app is not None else None}}

    @app.get("/api/me")
    def me(request: Request):
        a = actor(request)
        return {"id": a.id, "roles": sorted(a.roles)}

    @app.get("/api/policy")
    def policy(request: Request):
        return playground().policy(actor(request))

    @app.post("/api/preview")
    def preview(request: Request, body: dict = Body(...)):
        return playground().preview(actor(request), body.get("overrides", {}))

    @app.get("/api/hypotheses")
    def hypotheses(request: Request):
        return playground().hypotheses(actor(request))

    @app.post("/api/hypotheses")
    def create(request: Request, body: dict = Body(...), idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{a.id}#create", lambda: p.create_hypothesis(a, body.get("intent", ""), body.get("overrides")))

    @app.get("/api/hypotheses/{hid}")
    def get_h(hid: str, request: Request):
        return playground().hypothesis(actor(request), hid)

    @app.get("/api/hypotheses/{hid}/audit")
    def audit(hid: str, request: Request):
        return playground().audit_trail(actor(request), hid)

    @app.post("/api/hypotheses/{hid}/scenarios")
    def confirm(hid: str, request: Request, body: dict = Body(...), idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{hid}#confirm", lambda: p.confirm(a, hid, body.get("overrides", {})))

    @app.post("/api/hypotheses/{hid}/executions")
    def execute(hid: str, request: Request, body: dict = Body(default={}), idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{hid}#exec", lambda: p.request_execution(a, hid, body.get("scenarioId")))

    @app.get("/api/executions/{eid}")
    def get_exec(eid: str, request: Request):
        return playground().execution(actor(request), eid)

    @app.post("/api/hypotheses/{hid}/suggestions")
    def suggest(hid: str, request: Request, idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{hid}#suggest", lambda: p.request_suggestions(a, hid))

    @app.post("/api/hypotheses/{hid}/investigations")
    def investigate(hid: str, request: Request, idem: str | None = Header(None, alias="Idempotency-Key")):
        """Aciona o Agente Investigador (R17) sobre o último cenário confirmado; responde 202 com o job."""
        a, p = actor(request), playground()
        return JSONResponse(p.idempotent(idem, f"{hid}#investigate", lambda: p.request_investigation(a, hid)), 202)

    @app.post("/api/hypotheses/{hid}/findings/{fid}/transitions")
    def transition(hid: str, fid: str, request: Request, body: dict = Body(...), idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{fid}#tr", lambda: p.transition(a, hid, fid, body.get("to", ""), body.get("reason")))

    @app.post("/api/hypotheses/{hid}/findings/{fid}/executions")
    def exec_finding(hid: str, fid: str, request: Request, idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{fid}#exec", lambda: p.execute_finding(a, hid, fid))

    @app.post("/api/hypotheses/{hid}/findings/{fid}/assessments")
    def assess(hid: str, fid: str, request: Request, body: dict = Body(...), idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{fid}#assess", lambda: p.assess(a, hid, fid, bool(body.get("relevant"))))

    @app.post("/api/hypotheses/{hid}/decisions")
    def decide(hid: str, request: Request, body: dict = Body(...), idem: str | None = Header(None, alias="Idempotency-Key")):
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{hid}#decide", lambda: p.decide(a, hid, body.get("outcome", ""), body.get("rationale", ""),
                                                                   body.get("evidenceRefs", [])))

    if mcp_app is not None:
        app.mount("/mcp", mcp_app)

    @app.post("/api/hypotheses/{hid}/change-package")
    def gen_package(hid: str, request: Request, idem: str | None = Header(None, alias="Idempotency-Key")):
        """Pacote de mudança para engenharia (NÃO SUBMETIDO), só após decisão de aceite."""
        a, p = actor(request), playground()
        return p.idempotent(idem, f"{hid}#package", lambda: p.generate_change_package(a, hid))

    @app.get("/api/hypotheses/{hid}/change-package/{pid}")
    def get_package(hid: str, pid: str, request: Request):
        return playground().change_package(actor(request), hid, pid)

    @app.post("/events")
    async def lambda_events(request: Request):
        """Jobs assíncronos: a Lambda se invoca com {"ppJob": {...}} e o Web Adapter entrega aqui."""
        payload = await request.json()
        job = payload.get("ppJob") if isinstance(payload, dict) else None
        if job:
            playground().run_job(job)
        return {"ok": True}

    static = Path(os.environ.get("PP_STATIC") or _repo_path(3, "frontend", "dist"))
    if static.exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = static / path
            return FileResponse(f if path and f.is_file() else static / "index.html")

    return app


app = create_app()
