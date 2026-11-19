"""
Recopila titulares económicos (solo titular + enlace + fuente) de medios dominicanos y del Banco Central.
Se ejecuta desde la raíz del repositorio. Guarda data/noticias.json.
Fuentes: Diario Libre, Diario Financiero, Revista Mercado, elDinero, Listín Diario, Hoy, El Día,
Banco Central (noticias y comunicados de política monetaria).
Si una fuente no publica la fecha en el enlace, se usa la fecha en que Ámbar vio el titular por primera vez.
Requisitos: pip install requests beautifulsoup4
"""
import datetime as dt, json, re, sys
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
HOY = dt.datetime.now(ZoneInfo("America/Santo_Domingo")).date().isoformat()
POR_FUENTE = 80  # titulares guardados por fuente (para que una fuente muy activa no desplace a las demás)
CAT = {"finanzas": "Finanzas", "negocios": "Negocios", "energia": "Energía", "consumo": "Consumo",
       "empleo": "Empleo", "economia": "Economía", "opinion": "Opinión", "banca": "Banca",
       "noticias-nacionales": "Nacionales", "mercado-de-valores": "Mercado de valores",
       "finanzas-y-negocios": "Negocios", "turismo": "Turismo", "macroeconomia": "Economía",
       "empresas": "Empresas", "money-invest": "Finanzas", "business": "Negocios", "market-brief": "Economía",
       "actualidad": "Economía", "agropecuaria": "Agro", "zona-franca": "Negocios"}
EXCLUIR_DF = ("politica", "internacionales", "deportes", "entretenimiento", "tecnologia", "salud")

def limpio(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t[:1].upper() + t[1:] if t else t

def anclas(url):
    html = requests.get(url, headers=UA, timeout=60).text
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        yield a["href"].split("?")[0].split("#")[0], limpio(a.get_text(" "))

def diario_libre():
    out = []
    for u, t in anclas("https://www.diariolibre.com/economia"):
        if u.startswith("/"): u = "https://www.diariolibre.com" + u
        m = re.search(r"diariolibre\.com/economia/([a-z-]+)/(\d{4})/(\d\d)/(\d\d)/[^/]+/\d+", u)
        if m and len(t) > 25:
            out.append({"s": "Diario Libre", "t": t, "u": u, "c": CAT.get(m[1], "Economía"), "d": f"{m[2]}-{m[3]}-{m[4]}"})
    return out

def diario_financiero():
    out = []
    for u, t in anclas("https://diariofinanciero.do/"):
        m = re.match(r"https://diariofinanciero\.do/([a-z-]+)/(?:[a-z-]+/)?[a-z0-9-]{12,}/?$", u)
        if not m or len(t) < 25 or m[1] in EXCLUIR_DF or m[1] in ("category", "tag", "author") \
                or re.match(r"(Ranking|Comparador|Calculadora|Guía|Precio del dólar)\b", t, re.I):  # herramientas fijas del sitio
            continue
        out.append({"s": "Diario Financiero", "t": t, "u": u, "c": CAT.get(m[1], "Economía"), "d": None})
    return out

def revista_mercado():
    out = []
    for u, t in anclas("https://revistamercado.do/"):
        m = re.match(r"https://revistamercado\.do/(empresas|money-invest|business|market-brief|actualidad)/(?:([a-z-]+)/)?[a-z0-9-]{12,}/?$", u)
        if m and len(t) > 25 and m[2] != "daily-news":  # "daily-news" mezcla notas no económicas (sismos, premios)
            out.append({"s": "Revista Mercado", "t": t, "u": u, "c": CAT.get(m[1], "Economía"), "d": None})
    return out

def el_dinero():
    out = []
    for u, t in anclas("https://eldinero.com.do/"):
        if re.match(r"https://eldinero\.com\.do/\d{5,}/[a-z0-9-]{12,}/?$", u) and len(t) > 25:
            out.append({"s": "elDinero", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def listin():
    out = []
    for u, t in anclas("https://listindiario.com/economia"):
        if u.startswith("/"): u = "https://listindiario.com" + u
        m = re.match(r"https://listindiario\.com/economia/(?:([a-z-]+)/)?(\d{4})(\d\d)(\d\d)/[^/]+_\d+\.html$", u)
        if m and len(t) > 25:
            out.append({"s": "Listín Diario", "t": t, "u": u, "c": CAT.get(m[1] or "economia", "Economía"), "d": f"{m[2]}-{m[3]}-{m[4]}"})
    return out

def hoy():
    out = []
    for u, t in anclas("https://hoy.com.do/economia/"):
        if re.match(r"https://hoy\.com\.do/economia/[a-z0-9-]{10,}_\d+\.html$", u) and len(t) > 25:
            out.append({"s": "Hoy", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def el_dia():
    out = []
    for u, t in anclas("https://eldia.com.do/secciones/economicas/"):
        m = re.match(r"https://eldia\.com\.do/([a-z0-9-]+)/?$", u)
        if m and m[1].count("-") >= 4 and len(t) > 25 and not m[1].startswith(("secciones", "author", "tag", "category")):
            out.append({"s": "El Día", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def banco_central():
    out = []
    for cc, cat in (("CAT-037", "Banco Central"), ("CAT-036", "Política monetaria")):
        r = requests.post("https://www.bancentral.gov.do/Home/GetArticles", timeout=60,
                          headers={**UA, "X-Requested-With": "XMLHttpRequest"},
                          data={"categoryCode": cc, "languageName": "es", "requestIsFromPortal": "true",
                                "filter": "", "skipCount": 0, "maxResultCount": 15})
        for it in r.json()["result"]["items"]:
            f = (it.get("auxiliarDatetime1") or "")[:10]
            if not f or f.startswith("0001"): f = (it.get("creationTime") or "")[:10] or None
            out.append({"s": "Banco Central", "t": limpio(it["title"]), "u": f"https://www.bancentral.gov.do/a/d/{it['stringId']}",
                        "c": cat, "d": f})
    return out

FUENTES = (diario_libre, diario_financiero, revista_mercado, el_dinero, listin, hoy, el_dia, banco_central)

def main():
    try:
        viejas = json.load(open("data/noticias.json", encoding="utf-8"))
    except FileNotFoundError:
        viejas = []
    previas = {n["u"]: n for n in viejas}
    nuevas = []
    for fuente in FUENTES:
        try:
            n = fuente(); nuevas += n; print(f"{fuente.__name__}: {len(n)} titulares")
        except Exception as e:  # si una fuente falla, no detiene el resto
            print(f"{fuente.__name__}: ERROR {e}", file=sys.stderr)
    vistos, todas = set(), []
    for n in nuevas + viejas:  # sin duplicados por enlace
        if n["u"] in vistos: continue
        vistos.add(n["u"])
        p = previas.get(n["u"])
        n["v"] = (p or {}).get("v") or n.get("v") or (None if p else HOY)  # primera vez que Ámbar vio el titular
        if not n.get("d"): n["d"] = (p or {}).get("d") or n["v"]  # sin fecha publicada: se usa la primera vez visto
        todas.append(n)
    todas.sort(key=lambda n: (n.get("d") or "", n.get("v") or ""), reverse=True)
    cuenta, final = {}, []
    for n in todas:
        cuenta[n["s"]] = cuenta.get(n["s"], 0) + 1
        if cuenta[n["s"]] <= POR_FUENTE: final.append(n)
    json.dump(final, open("data/noticias.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"Total guardado: {len(final)} · " + ", ".join(f"{k}: {min(v, POR_FUENTE)}" for k, v in cuenta.items()))

if __name__ == "__main__":
    main()
