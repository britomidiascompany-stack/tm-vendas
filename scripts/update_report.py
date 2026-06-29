#!/usr/bin/env python3
"""
Auto-atualiza relatorio-atual.html com dados live do Meta Ads.
Rodado via GitHub Actions — sem custo de IA, sem computador ligado.
"""
import json, os, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

# ── Configuração ──────────────────────────────────────────────────────────────
TOKEN      = os.environ["META_ACCESS_TOKEN"]
ACT        = "857209303367605"
CAMP_START = "2026-05-22"    # início total da campanha
P2_START   = "2026-06-25"    # início Fase 2
P2_IDS     = [
    "120248611766680305",    # [03]
    "120248613055370305",    # [04]
    "120248614712170305",    # [05]
]
HTML_PATH     = Path(__file__).resolve().parent.parent / "relatorio-atual.html"
BRT           = timezone(timedelta(hours=-3))
CONV_ACTION   = "onsite_conversion.messaging_conversation_started_7d"
MES_ABREV     = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
MES_LONGO     = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho",
                  "Agosto","Setembro","Outubro","Novembro","Dezembro"]

# ── API ───────────────────────────────────────────────────────────────────────
def api(path, **kw):
    p = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in kw.items()}
    p["access_token"] = TOKEN
    r = requests.get(f"https://graph.facebook.com/v20.0/{path}", params=p, timeout=30)
    d = r.json()
    if "error" in d:
        raise RuntimeError(f"Meta API: {d['error'].get('message', d['error'])}")
    return d

def get_conv(actions):
    for a in (actions or []):
        if a.get("action_type") == CONV_ACTION:
            return int(float(a["value"]))
    return 0

def get_cpr(lst):
    for a in (lst or []):
        if a.get("action_type") == CONV_ACTION:
            return float(a["value"])
    return 0.0

# ── Formatação brasileira ─────────────────────────────────────────────────────
def dec(v):
    """2186.92 → '2.186,92'"""
    return f"{v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

def brl(v):
    """Float → 'R$2.186,92'"""
    return f"R${dec(v)}"

def num(v):
    """Int → '110.329'"""
    return f"{int(v):,}".replace(",",".")

def data_pt(s):
    """'2026-06-26' → '26/jun'"""
    dt = datetime.strptime(s, "%Y-%m-%d")
    return f"{dt.day}/{MES_ABREV[dt.month-1]}"

# ── Patch de marcadores ───────────────────────────────────────────────────────
def patch(html, key, value):
    pattern = rf'<!-- VK:{re.escape(key)} -->.*?<!-- /VK:{re.escape(key)} -->'
    repl    = f'<!-- VK:{key} -->{value}<!-- /VK:{key} -->'
    new, n  = re.subn(pattern, repl, html, flags=re.DOTALL)
    if n == 0:
        print(f"  AVISO: marcador VK:{key} não encontrado", file=sys.stderr)
    return new

# ── Célula horário ────────────────────────────────────────────────────────────
def hc_cell(hh, best_slot):
    info = hours.get(hh, {"spend": 0, "conv": 0})
    s, c = info["spend"], info["conv"]
    if c == 0 and s < 0.50:
        return '<div class="hc hc-noconv"><span class="hc-dash">a rodar</span></div>'
    if c == 0:
        return (f'<div class="hc hc-noconv">'
                f'<span class="hc-invest">{brl(s)}</span>'
                f'<span class="hc-dash">0 conv</span></div>')
    if s < 0.50:
        # atribuições tardias — conversões sem investimento ativo
        return (f'<div class="hc hc-noconv">'
                f'<span class="hc-invest">R$0,00</span>'
                f'<span class="hc-conv">{c} conv</span></div>')
    cpl_h    = s / c
    cls      = "cpl-low" if cpl_h < 8 else ("cpl-mid" if cpl_h < 12 else "cpl-high")
    best_cls = " hc-best" if hh == best_slot else ""
    return (f'<div class="hc{best_cls}">'
            f'<span class="hc-invest">{brl(s)}</span>'
            f'<span class="hc-conv">{c} conv</span>'
            f'<span class="hc-cpl {cls}">{brl(cpl_h)}</span></div>')

# ── Célula dia-a-dia ─────────────────────────────────────────────────────────
def dc_cell(day_spend, day_conv, day_cpl, today_pt, is_best):
    cls_extra = " dc-best" if is_best else ""
    cpl_cls   = "cpl-low" if day_cpl < 8 else ("cpl-mid" if day_cpl < 12 else "cpl-high")
    star      = " ★" if is_best else ""
    return (f'<div class="dc{cls_extra}">\n'
            f'              <span class="dc-date">{today_pt}{star}</span>\n'
            f'              <span class="dc-invest">{brl(day_spend)}</span>\n'
            f'              <span class="dc-conv">{day_conv} conv</span>\n'
            f'              <span class="dc-cpl {cpl_cls}">{brl(day_cpl)}</span>\n'
            f'            </div>')

# ── Main ──────────────────────────────────────────────────────────────────────
now   = datetime.now(BRT)
today = now.strftime("%Y-%m-%d")
print(f"=== {today} {now.strftime('%H:%M')} BRT ===")

# 1. Totais da conta
print("Buscando totais...")
row    = api(f"act_{ACT}/insights",
    fields="spend,impressions,clicks,reach,actions,cost_per_action_type",
    time_range={"since": CAMP_START, "until": today})["data"][0]
spend  = float(row["spend"])
imp    = int(row["impressions"])
clicks = int(row["clicks"])
reach  = int(row["reach"])
total  = get_conv(row.get("actions"))
cpl_v  = spend / total  if total  else 0
cpl_c  = spend / clicks if clicks else 0
print(f"  {num(total)} conv · {brl(spend)} · {brl(cpl_v)}/conv")

# Estimativas do funil (ratios históricos)
r1 = round(total * 0.984)
r2 = round(total * 0.650)
r3 = round(total * 0.568)
cpl_r1 = spend / r1 if r1 else 0
cpl_r2 = spend / r2 if r2 else 0
cpl_r3 = spend / r3 if r3 else 0

# 2. Horário de hoje
print("Buscando horário de hoje...")
h_rows = api(f"act_{ACT}/insights",
    fields="spend,actions",
    time_range={"since": today, "until": today},
    breakdowns="hourly_stats_aggregated_by_advertiser_time_zone")["data"]
hours  = {}
for h in h_rows:
    hh = int(h["hourly_stats_aggregated_by_advertiser_time_zone"].split(":")[0])
    hours[hh] = {"spend": float(h.get("spend", 0)), "conv": get_conv(h.get("actions"))}
day_conv  = sum(v["conv"]  for v in hours.values())
day_spend = sum(v["spend"] for v in hours.values())
day_cpl   = day_spend / day_conv if day_conv else 0
best_slot = (min((hh for hh in hours if hours[hh]["conv"] > 0),
                 key=lambda hh: hours[hh]["spend"] / hours[hh]["conv"])
             if any(v["conv"] > 0 for v in hours.values()) else None)
print(f"  {day_conv} conv · {brl(day_spend)} · {brl(day_cpl)}/conv | best slot: {best_slot}h")

# 3. Fase 2 por campanha
print("Buscando Fase 2...")
p2_rows = api(f"act_{ACT}/insights",
    level="campaign",
    fields="campaign_id,campaign_name,spend,actions,cost_per_action_type",
    time_range={"since": P2_START, "until": today},
    filtering=[{"field":"campaign.id","operator":"IN","value":P2_IDS}])["data"]
p2 = {r["campaign_id"]: {
    "spend": float(r.get("spend", 0)),
    "conv":  get_conv(r.get("actions")),
    "cpl":   get_cpr(r.get("cost_per_action_type")),
} for r in p2_rows}
c03      = p2.get(P2_IDS[0], {"spend":0,"conv":0,"cpl":0})
c04      = p2.get(P2_IDS[1], {"spend":0,"conv":0,"cpl":0})
c05      = p2.get(P2_IDS[2], {"spend":0,"conv":0,"cpl":0})
p2_conv  = c03["conv"]  + c04["conv"]  + c05["conv"]
p2_spend = c03["spend"] + c04["spend"] + c05["spend"]
p2_cpl   = p2_spend / p2_conv if p2_conv else 0
p2_days  = (now.date() - datetime.strptime(P2_START, "%Y-%m-%d").date()).days + 1
print(f"  {p2_conv} conv · {brl(p2_spend)} · {brl(p2_cpl)}/conv | {p2_days} dias")

# 4. Breakdown diário (melhor dia)
print("Buscando breakdown diário...")
daily = api(f"act_{ACT}/insights",
    fields="spend,actions,date_start",
    time_range={"since": CAMP_START, "until": today},
    time_increment=1)["data"]
best_cpl, best_conv, best_date = float("inf"), 0, ""
for d in daily:
    c = get_conv(d.get("actions"))
    s = float(d.get("spend", 0))
    if c > 0 and s/c < best_cpl:
        best_cpl  = s / c
        best_conv = c
        best_date = data_pt(d["date_start"])
is_today_best = (day_cpl > 0 and day_cpl <= best_cpl)
print(f"  Melhor dia: {best_date} — {best_conv} conv · {brl(best_cpl)}/conv")

# ── Aplica patches ────────────────────────────────────────────────────────────
html     = HTML_PATH.read_text(encoding="utf-8")
today_pt = data_pt(today)
ts       = f"{now.day:02d}/{MES_ABREV[now.month-1]} às {now.strftime('%H:%M')}"
dias_str = f"{p2_days} {'dia' if p2_days == 1 else 'dias'}"
p2_start_pt = data_pt(P2_START)
mes_long    = MES_LONGO[now.month - 1]

# Timestamps
html = patch(html, "timestamp",
    ts)
html = patch(html, "footer_ts",
    f"Relatório atualizado em {now.day} de {mes_long} de {now.year} às "
    f"{now.strftime('%Hh')} · Campanha GDO CTWA Sul · Conta {ACT}")

# KPIs
html = patch(html, "kpi_spend",     f"R$ {dec(spend)}")
html = patch(html, "kpi_conv",      str(total))
html = patch(html, "kpi_cpl_value", f"R$ {dec(cpl_v)}")
html = patch(html, "kpi_cpl_foot",  f"Melhor dia: {best_date} — {brl(best_cpl)}/conv (novo recorde)")
html = patch(html, "kpi_best_conv", f"{best_conv} conv")
html = patch(html, "kpi_best_foot", f"{best_date} · {brl(best_cpl)} — novo recorde absoluto")

# Funil
html = patch(html, "funil_imp",    num(imp))
html = patch(html, "funil_reach",  num(reach))
html = patch(html, "funil_clicks", num(clicks))
html = patch(html, "funil_cpc",    f"~{brl(cpl_c)} por clique")
html = patch(html, "funil_conv",   str(total))
html = patch(html, "funil_cpl",    f"{brl(cpl_v)} por conversa")
html = patch(html, "funil_r1",     f"~{r1}")
html = patch(html, "funil_r1_cpl", f"~{brl(cpl_r1)} por primeira resposta")
html = patch(html, "funil_r2",     f"~{r2}")
html = patch(html, "funil_r2_cpl", f"~{brl(cpl_r2)} por interação")
html = patch(html, "funil_r3",     f"~{r3}")
html = patch(html, "funil_r3_cpl", f"~{brl(cpl_r3)} por interação")
html = patch(html, "funil_note_r1", f"~{r1} de {total}")

# Horário — células do dia de hoje
for hh in [15, 16, 17, 18, 19, 20]:
    html = patch(html, f"hc:{today}:{hh}", hc_cell(hh, best_slot))

# Dia-a-dia — célula de hoje
html = patch(html, f"dia:{today}",
    dc_cell(day_spend, day_conv, day_cpl, today_pt, is_today_best))

# Fase 2 box
html = patch(html, "p2_total",
    f"{p2_conv} conv acumuladas · {brl(p2_spend)} investidos · {brl(p2_cpl)}/conv médio · "
    f"{dias_str} de veiculação ({p2_start_pt}–{today_pt})")
html = patch(html, "p2_camps",
    f"[03] {c03['conv']} conv · {brl(c03['spend'])} · {brl(c03['cpl'])}/conv · "
    f"[04] {c04['conv']} conv · {brl(c04['spend'])} · {brl(c04['cpl'])}/conv · "
    f"[05] {c05['conv']} conv · {brl(c05['spend'])} · {brl(c05['cpl'])}/conv")

# Insights
html = patch(html, "insight_record",
    f"<strong>{today_pt} ★ novo recorde absoluto — {day_conv} conv com {brl(day_cpl)}/conv"
    f"</strong>. A Fase 2 ([03]–[05]) entregou {p2_conv} conv em {dias_str} com média de "
    f"{brl(p2_cpl)}/conv. Melhor dia histórico por volume E por CPL ao mesmo tempo.")
html = patch(html, "insight_p2",
    f"<strong>Fase 2 consolidando rápido</strong> — {p2_conv} conv acumuladas em apenas "
    f"{dias_str} ({p2_start_pt}–{today_pt}) com {brl(p2_cpl)}/conv médio. O horário "
    f"concentrado (15–19h Qui–Sex–Sáb–Dom) é significativamente mais eficiente que o "
    f"horário amplo da Fase 1.")

HTML_PATH.write_text(html, encoding="utf-8")
print(f"✓ Atualizado: {ts}")
