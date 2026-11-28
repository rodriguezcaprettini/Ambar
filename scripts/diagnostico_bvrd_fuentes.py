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
        r = S.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
        first = next(r.iter_content(256), b"")
        sig = ("xlsx/zip" if first[:2] == b"PK" else
               "pdf" if first.startswith(b"%PDF") else
               "json" if "json" in (r.headers.get("content-type") or "").lower() or first.lstrip().startswith((b"{", b"[")) else
               "html" if b"<html" in first.lower() or b"<!doctype" in first.lower() else
               repr(first[:24]))
        print(f"{url}\n  status={r.status_code} final={r.url}\n"
              f"  type={r.headers.get('content-type')} length={r.headers.get('content-length')} signature={sig}")
        if show_links and r.status_code == 200 and "html" in (r.headers.get("content-type") or "").lower():
            body = first + r.raw.read(2_000_000)
            text = body.decode("utf-8", "ignore")
            links = re.findall(r'''(?:href|src)=["']([^"']+)["']''', text, re.I)
            hits = [urljoin(r.url, x) for x in links if re.search(r"bolet|excel|\.xlsx|\.pdf", x, re.I)]
            for link in hits[:40]:
                print("  BULLETIN_LINK", link)
        elif show_links and r.status_code == 200 and sig == "json":
            body = first + r.raw.read(2_000_000)
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
                        for match in re.finditer(r'prod-data\\.bvrd\\.com\\.do', js.text, re.I):
                            print("  PRODDATA_CONTEXT", js.text[max(0, match.start()-350):match.end()+700].replace("\\n", " ")[:1100])
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
