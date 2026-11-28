#!/usr/bin/env python3
"""Prueba de acceso a rutas públicas BVRD/CDN desde GitHub Actions.

No resuelve desafíos anti-bot ni usa proxies. Comprueba archivos conocidos y
rutas de boletines recientes, validando la firma real del contenido.
"""
from datetime import date
from urllib.parse import urlparse
import requests

S = requests.Session()
S.headers.update({"User-Agent": "AmbarBVRDSourceCheck/1.1 (+https://github.com/rodriguezcaprettini/Ambar)"})
TIMEOUT = 25

# Archivo histórico cuya URL pública está indexada por buscadores.
KNOWN = [
    "https://cdn.bvrd.com.do/wp-content/uploads/2023/12/05-12-2023-Boletin-BVRD-Consolidado-pdf-1-1.pdf",
]
DATES = [date(2026, 11, 27), date(2026, 11, 26)]
CANDIDATES = []
for d in DATES:
    stem = f"{d:%d-%m-%Y}-Boletin-BVRD-Consolidado"
    month = f"{d:%Y/%m}"
    # Variantes de nombre/ruta de WordPress: solo sondas GET de archivos concretos.
    for name in (f"{stem}-Excel.xlsx", f"{stem}-excel.xlsx",
                 f"{stem}-excel-1.xlsx", f"{stem}-pdf.pdf"):
        CANDIDATES.append(f"https://cdn.bvrd.com.do/wp-content/uploads/{month}/{name}")
    # Ruta de descarga usada actualmente por el robot de Ámbar.
    month_name = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto",
                  "Septiembre","Octubre","Noviembre","Diciembre"][d.month-1]
    CANDIDATES.append(
        "https://prod-data.bvrd.com.do/documentos/boletines/"
        f"BOLETINES+Y+PRECIOS+{d.year}/Boletin+Consolidado/"
        f"{d.month}.+{month_name}/{d:%d-%m-%Y}-Boletin+BVRD+Consolidado+excel.xlsx"
    )

def check(url):
    try:
        r = S.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
        first = next(r.iter_content(16), b"")
        sig = ("xlsx/zip" if first[:2] == b"PK" else
               "pdf" if first.startswith(b"%PDF") else
               "html" if b"<html" in first.lower() else repr(first[:12]))
        print(f"{url}\n  status={r.status_code} final={r.url}\n"
              f"  type={r.headers.get('content-type')} length={r.headers.get('content-length')} signature={sig}")
        r.close()
    except Exception as e:
        print(f"{url}\n  ERROR {type(e).__name__}: {e}")

for u in KNOWN + CANDIDATES:
    check(u)
