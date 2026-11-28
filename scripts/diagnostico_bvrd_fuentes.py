#!/usr/bin/env python3
"""Diagnóstico de fuentes públicas alternativas para los Excel diarios de la BVRD.

No intenta resolver ni evadir desafíos de Cloudflare. Comprueba si la propia web
pública o sus enlaces publicados ofrecen una URL de Excel descargable desde CI.
"""
import re
import sys
from urllib.parse import urljoin, urlparse

import requests

S = requests.Session()
S.headers.update({"User-Agent": "AmbarBVRDSourceCheck/1.0 (+https://github.com/rodriguezcaprettini/Ambar)"})
TIMEOUT = 30
SOURCES = [
    "https://prod-data.bvrd.com.do/json/boletines.json",
    "https://bvrd.com.do/inicio/",
    "https://bvrd.com.do/",
]
seen = set()
excel_urls = set()

def report(url, response):
    body = response.content
    sig = "xlsx/zip" if body[:2] == b"PK" else "html" if b"<html" in body[:500].lower() else "other"
    print(f"URL {url}\n  status={response.status_code} final={response.url}\n  type={response.headers.get('content-type')} bytes={len(body)} signature={sig}")

for url in SOURCES:
    try:
        r = S.get(url, timeout=TIMEOUT)
        report(url, r)
        seen.add(r.url)
        if r.ok:
            text = r.text
            # JSON may contain absolute or relative document links.
            for raw in re.findall(r'https?[^\\"\'<> ]+|(?:[^\\"\'<> ]+\.xlsx(?:\?[^\\"\'<> ]*)?)', text, re.I):
                candidate = urljoin(r.url, raw.replace("\\/", "/"))
                if ".xlsx" in candidate.lower():
                    excel_urls.add(candidate)
            # Public-page anchors: keep links whose href or label mentions Excel/boletín.
            if "html" in r.headers.get("content-type", "").lower():
                for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.I | re.S):
                    combined = re.sub(r"<[^>]+>", " ", label)
                    if "excel" in (href + " " + combined).lower() or "boletin" in (href + " " + combined).lower():
                        candidate = urljoin(r.url, href)
                        if candidate.startswith("http"):
                            excel_urls.add(candidate)
    except Exception as e:
        print(f"URL {url}\n  ERROR {type(e).__name__}: {e}")

print(f"\nCANDIDATE_LINKS {len(excel_urls)}")
for url in sorted(excel_urls):
    try:
        # Avoid downloading large files during discovery; GET with streaming and inspect headers.
        r = S.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
        chunk = next(r.iter_content(4), b"")
        print(f"LINK {url}\n  status={r.status_code} final={r.url}\n  type={r.headers.get('content-type')} signature={'xlsx/zip' if chunk[:2] == b'PK' else chunk[:16]!r}")
        r.close()
    except Exception as e:
        print(f"LINK {url}\n  ERROR {type(e).__name__}: {e}")

if not excel_urls:
    print("\nRESULT: no se descubrieron enlaces Excel desde estas fuentes.")
