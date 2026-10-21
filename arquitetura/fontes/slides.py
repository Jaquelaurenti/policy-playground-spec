"""Gera os quadros (1920x1080) do vídeo: uma imagem por frase de cada cena, com a legenda da frase."""
import sys, re, json, html, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from script import SCENES
from playwright.async_api import async_playwright

S = Path("/tmp/claude-0/-home-claude/4c9ae48c-10e9-5678-8681-628a8f13dac5/scratchpad")
ARCH = (S / "arch/architecture.html").read_text()
SVG = re.search(r"<svg.*</svg>", ARCH, re.S).group(0)
INNER = re.sub(r"^<svg[^>]*>", "", SVG)[:-6].replace('href="icons/', 'href="' + (S / "arch/icons").as_uri() + '/')
OUT = S / "video/frames"; OUT.mkdir(parents=True, exist_ok=True)
ACC = "#B3155A"
HL = {"user":(60,200,270,150),"entra":(60,440,270,150),"cf":(440,215,240,150),"s3spa":(440,700,240,140),"apigw":(440,460,240,170),
 "alb":(900,255,280,140),"endpoints":(1250,255,270,150),"apia":(786,520,152,220),"wka":(952,520,152,220),"apib":(1176,520,152,220),"wkb":(1342,520,152,220),
 "bedrock":(1610,260,300,175),"sqs":(1610,560,300,150),"lambda":(1680,735,230,150),"appconfig":(1960,260,310,150),"s3data":(1960,450,310,150),"c1":(1960,640,310,205),
 "ddb":(765,985,310,190),"pipes":(1105,985,250,190),"firehose":(1385,985,250,190),"audit":(1665,985,250,190),"athena":(1945,985,250,190)}
E = html.escape

def sentences(t):
    parts = re.split(r"(?<=[.!?:])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])", t.strip())
    out = []
    for p in parts:
        if out and len(out[-1]) < 45: out[-1] += " " + p
        else: out.append(p)
    return out

CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}} html,body{{width:1920px;height:1080px;overflow:hidden;background:#fff;font-family:Inter,'DejaVu Sans',sans-serif;color:#14161B}}
.band{{position:absolute;left:0;right:0;bottom:0;height:236px;background:#fff;border-top:1px solid #E3E6EB;padding:26px 72px 0;display:flex;flex-direction:column;gap:14px}}
.row{{display:flex;align-items:center;gap:18px}}
.chip{{background:{ACC};color:#fff;font-weight:700;font-size:24px;padding:6px 16px;border-radius:999px;white-space:nowrap}}
.ttl{{font-size:38px;font-weight:800;letter-spacing:-.01em}}
.cap{{font-size:30px;line-height:1.35;color:#2A2E36;max-width:1776px}}
.brand{{position:absolute;top:26px;right:40px;font-weight:800;color:{ACC};font-size:26px;background:rgba(255,255,255,.92);padding:6px 14px;border-radius:10px}}
.stage{{position:absolute;left:0;top:0;width:1920px;height:844px;overflow:hidden;background:#fff}}
.full{{height:1080px}}
"""

def arch_stage(hl, full):
    W, H = 2400, 1350
    h_px = 1080 if full else 844
    ar = 1920 / h_px
    if not hl:
        rx1, ry1, rx2, ry2 = 30, 118, 2370, 1312
        vh = ry2 - ry1; vw = vh * ar
        if vw < rx2 - rx1: vw = rx2 - rx1; vh = vw / ar
        x0 = (rx1 + rx2 - vw) / 2; y0 = (ry1 + ry2 - vh) / 2
    else:
        bx = [HL[k] for k in hl]
        x1 = min(b[0] for b in bx) - 150; y1 = min(b[1] for b in bx) - 130
        x2 = max(b[0]+b[2] for b in bx) + 150; y2 = max(b[1]+b[3] for b in bx) + 130
        vw, vh = x2 - x1, y2 - y1
        if vw / vh < ar: vw = vh * ar
        else: vh = vw / ar
        if vw < 1150: vw = 1150; vh = vw / ar
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        x0 = min(max(cx - vw/2, -40), W + 40 - vw); y0 = min(max(cy - vh/2, -40), H + 40 - vh)
    holes = "".join(f'<rect x="{b[0]-12}" y="{b[1]-12}" width="{b[2]+24}" height="{b[3]+24}" rx="16" fill="black"/>' for b in [HL[k] for k in hl])
    rings = "".join(f'<rect x="{b[0]-12}" y="{b[1]-12}" width="{b[2]+24}" height="{b[3]+24}" rx="16" fill="none" stroke="{ACC}" stroke-width="6"/>' for b in [HL[k] for k in hl])
    overlay = (f'<defs><mask id="spot"><rect x="-500" y="-500" width="3400" height="2400" fill="white"/>{holes}</mask></defs>'
               f'<rect x="-500" y="-500" width="3400" height="2400" fill="rgba(20,22,27,0.42)" mask="url(#spot)"/>{rings}') if hl else ""
    return (f'<div class="stage{" full" if full else ""}"><svg xmlns="http://www.w3.org/2000/svg" width="1920" height="{h_px}" viewBox="{x0:.0f} {y0:.0f} {vw:.0f} {vh:.0f}" '
            f'style="font-family:Inter,sans-serif">{INNER}{overlay}</svg></div>')

def title_stage(sc):
    return f"""<div class="stage" style="background:linear-gradient(180deg,#fff 0,#F6F2F4 100%)">
      <div style="position:absolute;left:120px;top:150px;width:12px;height:420px;background:{ACC};border-radius:6px"></div>
      <div style="position:absolute;left:170px;top:150px">
        <div style="font-size:34px;font-weight:600;color:#5A606D">{E(sc['kicker'])}</div>
        <div style="font-size:128px;font-weight:800;letter-spacing:-.03em;line-height:1.05;margin-top:16px">{E(sc['title'])}</div>
        <div style="font-size:52px;font-weight:800;color:{ACC};margin-top:36px">CredIA Girls</div>
        <div style="font-size:30px;color:#5A606D;margin-top:8px">AWS Builders League</div>
        <div style="font-size:30px;color:#2A2E36;margin-top:48px">AI proposes · deterministic execution proves · humans decide</div>
      </div></div>"""

def principle_stage():
    card = lambda n, t, d: f"""<div style="flex:1;border:2px solid #E3E6EB;border-radius:18px;padding:34px;background:#fff">
        <div style="font-size:26px;font-weight:700;color:{ACC}">{n}</div><div style="font-size:44px;font-weight:800;margin-top:10px;line-height:1.1">{t}</div>
        <div style="font-size:28px;color:#4A505C;margin-top:18px;line-height:1.35">{d}</div></div>"""
    return f"""<div class="stage" style="padding:110px 120px 0">
      <div style="font-size:30px;color:#5A606D;font-weight:600">Hoje: 3 dias e 3 handoffs para testar uma hipótese de política</div>
      <div style="font-size:56px;font-weight:800;margin-top:12px;letter-spacing:-.02em">Renda mínima de R$ 2.500 para R$ 3.000: o que acontece?</div>
      <div style="display:flex;gap:28px;margin-top:56px">
        {card("1","IA propõe","Interpreta a intenção e estrutura a hipótese. Nunca calcula impacto.")}
        {card("2","Execução determinística comprova","Avaliador fechado sobre o DAG da política. É a única fonte dos números.")}
        {card("3","Pessoas decidem","Accept, Reject ou Defer, com justificativa e trilha imutável.")}
      </div></div>"""

def stats_stage(sc):
    tiles = "".join(f"""<div style="flex:1;background:#F6F2F4;border-radius:18px;padding:34px 36px">
        <div style="font-size:84px;font-weight:800;color:{ACC};letter-spacing:-.02em;line-height:1">{E(v)}</div>
        <div style="font-size:30px;color:#2A2E36;margin-top:16px;line-height:1.3">{E(l)}</div></div>""" for v, l in sc["stats"])
    bul = "".join(f'<div style="display:flex;gap:16px;align-items:center"><span style="width:14px;height:14px;border-radius:7px;background:{ACC}"></span><span>{E(b)}</span></div>' for b in sc["bullets"])
    return f"""<div class="stage" style="padding:120px 120px 0">
      <div style="font-size:64px;font-weight:800;letter-spacing:-.02em">{E(sc['title'])}</div>
      <div style="display:flex;gap:28px;margin-top:48px">{tiles}</div>
      <div style="display:flex;gap:56px;margin-top:52px;font-size:32px;font-weight:600;color:#2A2E36">{bul}</div></div>"""

def shot_stage(sc):
    if sc["shot"] == "desk":
        img = (S / "video/shots/desk.png").as_uri()
        return f'<div class="stage" style="background:#F4F5F8"><img src="{img}" style="position:absolute;left:0;top:0;width:1920px"></div>'
    tile = lambda v, l, c: f"""<div style="flex:1;background:#fff;border:2px solid #E3E6EB;border-radius:18px;padding:30px 32px">
        <div style="font-size:76px;font-weight:800;color:{c};line-height:1">{v}</div><div style="font-size:28px;color:#2A2E36;margin-top:14px;line-height:1.3">{l}</div></div>"""
    return f"""<div class="stage" style="background:#F4F5F8;padding:110px 110px 0">
      <div style="font-size:64px;font-weight:800;letter-spacing:-.02em">A arquitetura para de pé</div>
      <div style="display:flex;gap:24px;margin-top:44px">
        {tile("9/9","cenários aprovados no teste de mesa","#1B7A4B")}
        {tile("63/64","verificações contra o SDD","#1B7A4B")}
        {tile("15 s","P95 no pico normal, 50 especialistas","#1B7A4B")}
        {tile("175 s","P95 na rajada de 50, com cota de 200 mil tokens/min","#9A5B00")}
      </div>
      <div style="font-size:30px;color:#2A2E36;margin-top:40px;line-height:1.4">Na rajada, nada se perde: a fila absorve e o token bucket respeita a cota.<br>Mitigação: modo de sessão em grupo e aumento de cota para o dia da demo.</div></div>"""

def page(stage, sc, sent, full=False):
    band = "" if full else f"""<div class="band"><div class="row"><span class="chip">{E(sc.get('chip', sc['title']))}</span><span class="ttl">{E(sc['title'] if sc.get('chip') else '')}</span></div>
      <div class="cap">{E(sent)}</div></div>"""
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{stage}{band}<div class='brand'>CredIA Girls</div></body></html>"

async def main():
    meta = json.load(open(S / "video/audio/meta.json"))
    durs = {m["id"]: m["dur"] for m in meta}
    plan = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width":1920,"height":1080})
        for sc in SCENES:
            sents = sentences(sc["text"]); total = sum(len(x) for x in sents); dur = durs[sc["id"]] + 0.4
            if sc["kind"] == "arch": stage = arch_stage(sc["hl"], False)
            elif sc["kind"] == "title": stage = title_stage(sc)
            elif sc["kind"] == "principle": stage = principle_stage()
            elif sc["kind"] == "stats": stage = stats_stage(sc)
            else: stage = shot_stage(sc)
            for i, sent in enumerate(sents):
                f = OUT / f"{sc['id']}_{i:02d}.png"
                tmp = OUT / "_tmp.html"; tmp.write_text(page(stage, sc, sent))
                await pg.goto(tmp.as_uri()); await pg.wait_for_timeout(120)
                await pg.screenshot(path=str(f))
                plan.append({"file": str(f), "dur": dur * len(sent) / total, "scene": sc["id"], "text": sent})
        await b.close()
    json.dump(plan, open(S / "video/plan.json", "w"), ensure_ascii=False)
    print(len(plan), "quadros;", round(sum(x["dur"] for x in plan), 1), "s")

asyncio.run(main())
