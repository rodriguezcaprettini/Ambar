#!/usr/bin/env python3
"""Diagnóstico de fuentes públicas BVRD desde GitHub Actions.

Solo realiza GET públicos convencionales; no resuelve desafíos anti-bot,
no usa proxies y no intenta acceder a recursos privados.
Valida tipo/firma de archivos y resume enlaces de boletines encontrados.
"""
from datetime import date
from urllib.parse import urljoin
import re
import requests

S = requests.Session()
S.headers.update({"User-Agent": "AmbarBVRDSourceCheck/1.2 (+https://github.com/rodriguezcaprettini/Ambar)"})
TIMEOUT = 25

KNOWN = [
    "https://cdn.bvrd.com.do/wp-content/uploads/2023/12/05-12-2023-Boletin-BVRD-Consolidado-pdf-1-1.pdf",
]
DATES = [date(2026, 11, 27), date(2026, 11, 26)]
CANDIDATES = []
for d in DATES:
    stem = f"{d:%d-%m-%Y}-Boletin-BVRD-Consolidado"
    month = f"{d:%Y/%m}"
    for name in (f"{stem}-Excel.xlsx", f"{stem}-excel.xlsx",
                 f"{stem}-excel-1.xlsx", f"{stem}-pdf.pdf"):
        CANDIDATES.append(f"https://cdn.bvrd.com.do/wp-content/uploads/{month}/{name}")
    month_name = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto",
                  "Septiembre","Octubre","Noviembre","Diciembre"][d.month-1]
    CANDIDATES.append(
        "https://prod-data.bvrd.com.do/documentos/boletines/"
        f"BOLETINES+Y+PRECIOS+{d.year}/Boletin+Consolidado/"
        f"{d.month}.+{month_name}/{d:%d-%m-%Y}-Boletin+BVRD+Consolidado+excel.xlsx"
    )

# Rutas públicas de descubrimiento de WordPress y fuentes BVRD separadas.
DISCOVERY = [
    "https://bvrd.com.do/robots.txt",
    "https://bvrd.com.do/wp-sitemap.xml",
    "https://bvrd.com.do/wp-json/",
    "https://bvrd.com.do/wp-json/wp/v2/search?search=Boletin&per_page=20",
    "https://bvrd.com.do/wp-json/wp/v2/media?search=Boletin&per_page=20",
    "https://indices.bvrd.com.do/",
    "https://operaciones.bvrd.com.do/",
]
# Aplicaciones públicas que pueden cargar datos desde JavaScript.
APP_PAGES = [
    "https://indices.bvrd.com.do/",
    "https://dashboard.bvrd.exchange/",
]
SIMV_PAGES = [
    "https://simv.gob.do/estadisticas-reportes-y-estudios/",
    "https://simv.gob.do/datos-publicados-en-formatos-abiertos-csv-ods-xls/",
]

PAGES = [
    "https://bvrd.com.do/horarios-de-negociacion/",
    "https://bvrd.com.do/nuestros-emisores/",
    "https://bvrd.com.do/inicio/",
]

def check(url, show_links=False):
    try:
        r = S.get(url, timeout=TIMEOUT, allow_redirects=True)
        first = r.content[:256]
        sig = ("xlsx/zip" if first[:2] == b"PK" else
               "pdf" if first.startswith(b"%PDF") else
               "json" if "json" in (r.headers.get("content-type") or "").lower() or first.lstrip().startswith((b"{", b"[")) else
               "html" if b"<html" in first.lower() or b"<!doctype" in first.lower() else
               repr(first[:24]))
        print(f"{url}\n  status={r.status_code} final={r.url}\n"
              f"  type={r.headers.get('content-type')} length={r.headers.get('content-length')} signature={sig}")
        if show_links and r.status_code == 200 and "html" in (r.headers.get("content-type") or "").lower():
            body = r.content[:2_000_000]
            text = body.decode("utf-8", "ignore")
            links = re.findall(r'''(?:href|src)=["']([^"']+)["']''', text, re.I)
            hits = [urljoin(r.url, x) for x in links if re.search(r"bolet|excel|\.xlsx|\.pdf", x, re.I)]
            for link in hits[:40]:
                print("  BULLETIN_LINK", link)
        elif show_links and r.status_code == 200 and sig == "json":
            body = r.content[:2_000_000]
            text = body.decode("utf-8", "ignore")
            hits = re.findall(r'https?://[^"\\s<>]+', text)
            for link in [x for x in hits if re.search(r"bolet|excel|\.xlsx|\.pdf", x, re.I)][:40]:
                print("  BULLETIN_LINK", link)
        r.close()
    except Exception as e:
        print(f"{url}\n  ERROR {type(e).__name__}: {e}")

print("=== DISCOVERY ENDPOINTS ===")
for u in DISCOVERY:
    check(u, show_links=True)
print("=== PUBLIC APP / DATA DISCOVERY ===")
for u in APP_PAGES + SIMV_PAGES:
    check(u, show_links=True)
    try:
        r = S.get(u, timeout=TIMEOUT)
        if r.status_code == 200:
            html = r.text[:3_000_000]
            scripts = re.findall(r'''<script[^>]+src=["']([^"']+)''', html, re.I)
            for src in scripts[:30]:
                asset = urljoin(r.url, src)
                print("  SCRIPT", asset)
                try:
                    js = S.get(asset, timeout=TIMEOUT)
                    if js.status_code == 200:
                        print("  JS_LENGTH", len(js.text))
                        for match in re.finditer(r'prod-data', js.text, re.I):
                            print("  PRODDATA_CONTEXT", js.text[max(0, match.start()-350):match.end()+700].replace("\\n", " ")[:1100])
                        # Extrae rutas/API de bundles SPA sin limitarse a URLs absolutas.
                        if "dashboard.bvrd.exchange" in asset:
                            for kw in ("axios.create", "baseURL", "fetch(", "graphql",
                                       "api/", "/api", "operaciones", "emisores",
                                       "instrumentos", "acciones", "renta", "precios",
                                       "hechos", "ultim", "dashboard"):
                                starts = [m.start() for m in re.finditer(re.escape(kw), js.text, re.I)]
                                for pos in starts[:12]:
                                    print("  DASH_CONTEXT", kw, js.text[max(0,pos-260):pos+520].replace("\\n"," ")[:800])
                            patterns = re.findall(
                                r'''(?:https?://[^"\\'\\s<>]+|["\\']/(?:api|graphql|data|v[0-9]+|dashboard|operaciones|emisores|instrumentos|acciones|renta|precios)[^"\\']*)''',
                                js.text, re.I)
                            for endpoint in sorted(set(patterns))[:160]:
                                print("  DASH_ENDPOINT", endpoint[:500])
                        patterns = re.findall(
                            r'''(?:https?://[^"\\'\\s<>]+|["\\']/(?:api|graphql|data|wp-json)/[^"\\']+)''',
                            js.text, re.I)
                        for endpoint in patterns[:30]:
                            print("  JS_ENDPOINT", endpoint[:1000])
                except Exception as e:
                    print("  SCRIPT_ERROR", type(e).__name__, str(e)[:180])
        r.close()
    except Exception as e:
        print("  PAGE_ERROR", type(e).__name__, str(e)[:180])

print("=== PUBLIC PAGES ===")
for u in PAGES:
    check(u, show_links=True)
print("=== KNOWN/HISTORICAL AND MISSING DATES (prior CDN probe retained for comparison) ===")
for u in KNOWN + CANDIDATES:
    check(u)


print("=== PRUEBA API PUBLICA DEL DASHBOARD BVRD ===")
API_BASE = "https://dashboard.bvrd.exchange/apis/dashboard_emisores"
API_ROUTES = [
    "/dashboard_home",
    "/ultimos_precios",
    "/fecha_validate",
    "/precios_diarios_db",
    "/operaciones_totales",
    "/precio_ops_dia",
    "/variaciones_precio",
    "/ranking_bvrd_db",
    "/monitoreo_navs_db",
    "/variaciones_navs_db",
]
def brief_json(value, limit=1800):
    import json
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        raw = str(value)
    return raw[:limit].replace("\\n", " ")

for route in API_ROUTES:
    url = API_BASE + route
    try:
        resp = S.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"})
        ctype = resp.headers.get("content-type", "")
        print(f"API_PROBE {route} status={resp.status_code} type={ctype} bytes={len(resp.content)}")
        if resp.status_code == 200 and "json" in ctype.lower():
            try:
                data = resp.json()
                print("API_DATA", route, brief_json(data))
                if route == "/dashboard_home":
                    def walk(obj, depth=0):
                        if depth > 4:
                            return
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if any(x in k.lower() for x in ("titulo", "instrument", "id", "emis")):
                                    print("API_ID_CANDIDATE", k, brief_json(v, 500))
                                walk(v, depth+1)
                        elif isinstance(obj, list):
                            for item in obj[:20]:
                                walk(item, depth+1)
                    walk(data)
            except Exception as exc:
                print("API_JSON_ERROR", route, type(exc).__name__, str(exc)[:180], resp.text[:300])
        else:
            print("API_BODY", route, resp.text[:500].replace("\\n", " "))
        resp.close()
    except Exception as exc:
        print("API_ERROR", route, type(exc).__name__, str(exc)[:200])


print("=== PRUEBAS API CON PARAMETROS REALES DEL DASHBOARD ===")
PARAM_TESTS = [
    ("/precios_diarios_db", {"titulo_id": "AOCISA", "desde": "2026-11-01"}),
    ("/operaciones_totales", {"titulo_id": "AOCISA", "desde": "2026-11-01"}),
    ("/precio_ops_dia", {"titulo_id": "AOCISA"}),
    ("/variaciones_precio", {"titulo_id": "AOCISA"}),
    ("/ranking_bvrd_db", {"titulo_id": "AOCISA", "top_pb": 3}),
    ("/monitoreo_navs_db", {"titulo_id": "VF1RIC01", "desde": "2026-11-01"}),
    ("/variaciones_navs_db", {"titulo_id": "VF1RIC01"}),
]
for route, params in PARAM_TESTS:
    try:
        resp = S.get(API_BASE + route, params=params, timeout=TIMEOUT,
                     headers={"Accept": "application/json"})
        ctype = resp.headers.get("content-type", "")
        print(f"API_PARAM_PROBE {route} params={params} status={resp.status_code} type={ctype} bytes={len(resp.content)} url={resp.url}")
        if resp.status_code == 200 and "json" in ctype.lower():
            try:
                data = resp.json()
                print("API_PARAM_DATA", route, brief_json(data, 3500))
            except Exception as exc:
                print("API_PARAM_JSON_ERROR", route, type(exc).__name__, str(exc)[:160])
        else:
            print("API_PARAM_BODY", route, resp.text[:350].replace("\\n", " "))
        resp.close()
    except Exception as exc:
        print("API_PARAM_ERROR", route, type(exc).__name__, str(exc)[:180])


print("=== COBERTURA TEMPORAL Y UNIVERSO DE INSTRUMENTOS ===")
for ticker in ("AOCISA", "APPRO", "VF1RIC01"):
    for start in ("2026-11-26", "2026-10-01", "2025-01-01"):
        for route in ("/precios_diarios_db", "/operaciones_totales"):
            try:
                resp=S.get(API_BASE+route,params={"titulo_id":ticker,"desde":start},timeout=TIMEOUT,headers={"Accept":"application/json"})
                try:
                    data=resp.json() if resp.status_code==200 else None
                except Exception:
                    data=None
                count=len(data) if isinstance(data,list) else None
                dates=sorted({str(row.get("fecha_operacion") or row.get("fecha_hora_operacion",""))[:10] for row in data}) if isinstance(data,list) else []
                print(f"API_COVERAGE ticker={ticker} route={route} desde={start} status={resp.status_code} count={count} first={dates[0] if dates else None} last={dates[-1] if dates else None}")
                if start=="2026-11-26" and ticker=="AOCISA" and isinstance(data,list):
                    print("API_RECOVERY_SAMPLE",route,brief_json(data,2200))
                resp.close()
            except Exception as exc:
                print("API_COVERAGE_ERROR",ticker,route,start,type(exc).__name__,str(exc)[:140])
