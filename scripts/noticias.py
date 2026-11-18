"""
Recopila titulares económicos (solo titular + enlace) de Diario Libre y Diario Financiero.
Se ejecuta desde la raíz del repositorio. Guarda data/noticias.json (últimos 200 titulares).
Requisitos: pip install requests beautifulsoup4
"""
import json, re, sys
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Ambar)"}
CAT = {"finanzas": "Finanzas", "negocios": "Negocios", "energia": "Energía", "consumo": "Consumo",
       "empleo": "Empleo", "economia": "Economía", "opinion": "Opinión", "banca": "Banca",
       "noticias-nacionales": "Nacionales", "mercado-de-valores": "Mercado de valores",
       "finanzas-y-negocios": "Negocios", "turismo": "Turismo", "macroeconomia": "Economía"}
# Secciones de Diario Financiero que NO son económicas
EXCLUIR_DF = ("politica", "internacionales", "deportes", "entretenimiento", "tecnologia", "salud")

def limpio(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t[:1].upper() + t[1:] if t else t

def diario_libre():
    html = requests.get("https://www.diariolibre.com/economia", headers=UA, timeout=60).text
    out = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        u = a["href"]
        if u.startswith("/"): u = "https://www.diariolibre.com" + u
        m = re.search(r"diariolibre\.com/economia/([a-z-]+)/(\d{4})/(\d\d)/(\d\d)/[^/]+/\d+", u)
        t = limpio(a.get_text(" "))
        if m and len(t) > 25:
            out.append({"s": "Diario Libre", "t": t, "u": u.split("?")[0],
                        "c": CAT.get(m[1], "Economía"), "d": f"{m[2]}-{m[3]}-{m[4]}"})
    return out

def diario_financiero():
    html = requests.get("https://diariofinanciero.do/", headers=UA, timeout=60).text
    out = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        u = a["href"].split("?")[0]
        m = re.match(r"https://diariofinanciero\.do/([a-z-]+)/(?:[a-z-]+/)?[a-z0-9-]{12,}/?$", u)
        t = limpio(a.get_text(" "))
        if not m or len(t) < 25 or m[1] in EXCLUIR_DF or m[1] in ("category", "tag", "author"):
            continue
        f = re.search(r"(\d{1,2})-(?:de-)?noviembre-(\d{4})", u)  # algunas notas traen la fecha en el enlace
        out.append({"s": "Diario Financiero", "t": t, "u": u, "c": CAT.get(m[1], "Economía"),
                    "d": f"{f[2]}-11-{int(f[1]):02d}" if f else None})
    return out

def main():
    try:
        viejas = json.load(open("data/noticias.json", encoding="utf-8"))
    except FileNotFoundError:
        viejas = []
    nuevas = []
    for fuente in (diario_libre, diario_financiero):
        try:
            n = fuente(); nuevas += n; print(f"{fuente.__name__}: {len(n)} titulares")
        except Exception as e:  # si un periódico falla, no detiene el resto
            print(f"{fuente.__name__}: ERROR {e}", file=sys.stderr)
    vistos, todas = set(), []
    for n in nuevas + viejas:  # las nuevas primero; sin duplicados por enlace
        if n["u"] not in vistos:
            vistos.add(n["u"]); todas.append(n)
    json.dump(todas[:200], open("data/noticias.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"Total guardado: {len(todas[:200])}")

if __name__ == "__main__":
    main()
