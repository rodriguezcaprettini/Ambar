"""
Recopila titulares económicos (solo titular + enlace + fuente) de medios dominicanos y del Banco Central.
Se ejecuta desde la raíz del repositorio. Guarda data/noticias.json.
Fuentes: Diario Libre, Diario Financiero, Revista Mercado, elDinero, Listín Diario, Hoy, El Día,
Banco Central (noticias y comunicados de política monetaria).
Si una fuente no publica la fecha en el enlace, se usa la fecha en que Ámbar vio el titular por primera vez.
Uso:  python scripts/noticias.py              -> corrida diaria (portadas de cada medio)
      python scripts/noticias.py --historial  -> recorre páginas anteriores (archivo desde 2025)
Requisitos: pip install requests beautifulsoup4
"""
import datetime as dt, json, os, re, sys, time
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
HOY = dt.datetime.now(ZoneInfo("America/Santo_Domingo")).date().isoformat()
POR_FUENTE = 300   # titulares recientes por fuente en el estado del robot (el archivo completo vive en la tabla de Supabase)
DESDE = "1990-01-01"  # el archivo histórico llega hasta donde lo permita cada medio
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
    html = requests.get(url, headers=UA, timeout=60).content  # bytes: BeautifulSoup detecta bien la codificación
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        hd = a.find(["h1", "h2", "h3", "h4"])  # si el enlace envuelve un título, se usa solo el título (sin el resumen)
        yield a["href"].split("?")[0].split("#")[0], limpio((hd or a).get_text(" "))

def diario_libre(url="https://www.diariolibre.com/economia"):
    out = []
    for u, t in anclas(url):
        if u.startswith("/"): u = "https://www.diariolibre.com" + u
        m = re.search(r"diariolibre\.com/economia/([a-z-]+)/(\d{4})/(\d\d)/(\d\d)/[^/]+/\d+", u)
        if m and len(t) > 25:
            out.append({"s": "Diario Libre", "t": t, "u": u, "c": CAT.get(m[1], "Economía"), "d": f"{m[2]}-{m[3]}-{m[4]}"})
    return out

def diario_financiero(url="https://diariofinanciero.do/"):
    out = []
    for u, t in anclas(url):
        m = re.match(r"https://diariofinanciero\.do/([a-z-]+)/(?:[a-z-]+/)?[a-z0-9-]{12,}/?$", u)
        if not m or len(t) < 25 or m[1] in EXCLUIR_DF or m[1] in ("category", "categoria", "tag", "author", "herramientas-financieras", "page") \
                or re.match(r"(Ranking|Comparador|Calculadora|Guía|Precio del dólar)\b", t, re.I):  # herramientas fijas del sitio
            continue
        out.append({"s": "Diario Financiero", "t": t, "u": u, "c": CAT.get(m[1], "Economía"), "d": None})
    return out

def revista_mercado(url="https://revistamercado.do/"):
    out = []
    for u, t in anclas(url):
        m = re.match(r"https://revistamercado\.do/(empresas|money-invest|business|market-brief|actualidad)/(?:([a-z-]+)/)?[a-z0-9-]{12,}/?$", u)
        if m and len(t) > 25 and m[2] != "daily-news":  # "daily-news" mezcla notas no económicas (sismos, premios)
            out.append({"s": "Revista Mercado", "t": t, "u": u, "c": CAT.get(m[1], "Economía"), "d": None})
    return out

def el_dinero(url="https://eldinero.com.do/"):
    out = []
    for u, t in anclas(url):
        if re.match(r"https://eldinero\.com\.do/\d{5,}/[a-z0-9-]{12,}/?$", u) and len(t) > 25:
            out.append({"s": "elDinero", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def listin(url="https://listindiario.com/economia"):
    out = []
    for u, t in anclas(url):
        if u.startswith("/"): u = "https://listindiario.com" + u
        m = re.match(r"https://listindiario\.com/economia/(?:([a-z-]+)/)?(\d{4})(\d\d)(\d\d)/[^/]+_\d+\.html$", u)
        if m and len(t) > 25:
            out.append({"s": "Listín Diario", "t": t, "u": u, "c": CAT.get(m[1] or "economia", "Economía"), "d": f"{m[2]}-{m[3]}-{m[4]}"})
    return out

def hoy(url="https://hoy.com.do/economia/"):
    out = []
    for u, t in anclas(url):
        if re.match(r"https://hoy\.com\.do/economia/[a-z0-9-]{10,}_\d+\.html$", u) and len(t) > 25:
            out.append({"s": "Hoy", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def el_dia(url="https://eldia.com.do/secciones/economicas/"):
    out = []
    for u, t in anclas(url):
        m = re.match(r"https://eldia\.com\.do/([a-z0-9-]+)/?$", u)
        if m and m[1].count("-") >= 4 and len(t) > 25 and not m[1].startswith(("secciones", "author", "tag", "category")):
            out.append({"s": "El Día", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def banco_central(pagina=0, tam=15):
    out = []
    for cc, cat in (("CAT-037", "Banco Central"), ("CAT-036", "Política monetaria")):
        r = requests.post("https://www.bancentral.gov.do/Home/GetArticles", timeout=60,
                          headers={**UA, "X-Requested-With": "XMLHttpRequest"},
                          data={"categoryCode": cc, "languageName": "es", "requestIsFromPortal": "true",
                                "filter": "", "skipCount": pagina, "maxResultCount": tam})
        for it in r.json()["result"]["items"]:
            f = (it.get("auxiliarDatetime1") or "")[:10]
            fc, hc = a_rd(it.get("creationTime"))
            if not f or f.startswith("0001"): f = fc
            out.append({"s": "Banco Central", "t": limpio(it["title"]), "u": f"https://www.bancentral.gov.do/a/d/{it['stringId']}",
                        "c": cat, "d": f, "h": hc if fc == f else None})
    return out

def el_nuevo_diario(url="https://elnuevodiario.com.do/economia/"):
    out = []
    for u, t in anclas(url):
        m = re.match(r"https://elnuevodiario\.com\.do/([a-z0-9-]+)/?$", u)
        if m and m[1].count("-") >= 4 and len(t) > 25 and not m[1].startswith(("politica-de-", "terminos-", "aviso-")):
            out.append({"s": "El Nuevo Diario", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def n_digital(url="https://n.com.do/economia/"):
    out = []
    for u, t in anclas(url):
        m = re.match(r"https://n\.com\.do/(\d{4})/(\d\d)/(\d\d)/[a-z0-9-]{12,}/?$", u)
        t = re.sub(r"^.*?\d+\s*Min\s+", "", t)  # quita "Artículo Actualidad · octubre 13, 2026 · 4 Min"
        if m and len(t) > 25 and len(t) < 220:
            out.append({"s": "N Digital", "t": t, "u": u, "c": "Economía", "d": f"{m[1]}-{m[2]}-{m[3]}"})
    return out

def cdn(url="https://cdn.com.do/economicas/"):
    out = []
    for u, t in anclas(url):
        if re.match(r"https://cdn\.com\.do/economicas/[a-z0-9-]{12,}/?$", u) and len(t) > 25:
            out.append({"s": "CDN", "t": t, "u": u, "c": "Economía", "d": None})
    return out

def acento():
    """Acento no tiene portada de economía estable: se usa su sitemap de Google News (trae título y fecha)."""
    x = requests.get("https://acento.com.do/sitemaps/sitemaps-googlenews.xml", headers=UA, timeout=60).text
    res = []
    for b in re.findall(r"<url>(.*?)</url>", x, re.S):
        u = re.search(r"<loc>\s*(.*?)\s*</loc>", b); t = re.search(r"<news:title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</news:title>", b, re.S)
        f = re.search(r"<news:publication_date>\s*(.*?)\s*</news:publication_date>", b)
        if u and t and "/economia/" in u[1]:
            d, hr = a_rd(f[1]) if f else (None, None)
            res.append({"s": "Acento", "t": limpio(BeautifulSoup(t[1], "html.parser").get_text()), "u": u[1], "c": "Economía", "d": d, "h": hr})
    return res

def micm(url="https://micm.gob.do/noticias/"):
    out = []
    for u, t in anclas(url):
        m = re.match(r"https://micm\.gob\.do/([a-z0-9-]+)/?$", u)
        if m and m[1].count("-") >= 4 and len(t) > 25:
            out.append({"s": "MICM", "t": t, "u": u, "c": "Comercio e industria", "d": None})
    return out

def dgii(url="https://dgii.gov.do/noticias/Paginas/default.aspx"):
    out = []
    for u, t in anclas(url):
        if u.startswith("/"): u = "https://dgii.gov.do" + u
        u = u.replace("http://", "https://")
        if re.search(r"dgii\.gov\.do/noticias/Paginas/(?!default).+\.aspx$", u) and len(t) > 25:
            f = re.search(r"(\d\d)/(\d\d)/(\d{4})\s*$", t)
            out.append({"s": "DGII", "t": re.sub(r"\s*\d\d/\d\d/\d{4}\s*$", "", t), "u": u, "c": "Impuestos",
                        "d": f"{f[3]}-{f[2]}-{f[1]}" if f else None})
    return out

def superintendencia_bancos(url="https://sb.gob.do/publicaciones/cronologia-sb/publicaciones-de-prensa/archivo-de-prensa/"):
    out = []
    for u, t in anclas(url):
        if u.startswith("/"): u = "https://sb.gob.do" + u
        if re.match(r"https://(www\.)?sb\.gob\.do/publicaciones/cronologia-sb/publicaciones-de-prensa/archivo-de-prensa/[^/]{12,}/?$", u) and len(t) > 25:
            out.append({"s": "Superintendencia de Bancos", "t": t, "u": u, "c": "Banca", "d": None})
    return out

def el_brifin(url=None):
    """Sección Economía y finanzas + el resumen diario (El Brifin publica pocas notas sueltas de economía)."""
    out = []
    urls = [url] if url else ["https://elbrifin.com/category/temas/economia-y-finanzas/", "https://elbrifin.com/category/el-brifin-diario/"]
    for u, t in (x for v in urls for x in anclas(v)):
        m = re.match(r"https://elbrifin\.com/([a-z0-9-]+)/?$", u)
        if m and m[1].count("-") >= 3 and len(t) > 25 and not m[1].startswith(("category", "la-guagua", "brifeos-por", "para-entender-los-talibanes")):
            out.append({"s": "El Brifin", "t": t, "u": u, "c": "Economía y finanzas", "d": None})
    return out

EXCLUIR_U = ("elbrifin.com/brifeos-por", "elbrifin.com/para-entender-los-talibanes")
MESES_C = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

def cevaldom(url="https://www.cevaldom.com/noticias/"):
    out = []
    for u, t in anclas(url):
        if u.startswith("/"): u = "https://www.cevaldom.com" + u
        if not re.match(r"https://www\.cevaldom\.com/noticias/[a-z0-9-]{12,}/?$", u) or len(t) < 25: continue
        m = re.search(r"\s(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sept?|oct|nov|dic)\w*\.?\s+(\d{4})", t, re.I)
        d = f"{m[3]}-{MESES_C[m[2][:3].lower()]:02d}-{int(m[1]):02d}" if m else None
        out.append({"s": "CEVALDOM", "t": t[:m.start()].strip() if m else t, "u": u, "c": "Mercado de valores", "d": d})
    return out

# Bloqueados por Cloudflare para robots (no se intenta saltar esa protección): El Caribe, SIMV (Superintendencia del Mercado de Valores), BVRD, Ministerio de Hacienda, MEPyD.
FUENTES = (diario_libre, diario_financiero, revista_mercado, el_dinero, listin, hoy, el_dia, banco_central,
           el_nuevo_diario, n_digital, cdn, acento, micm, dgii, superintendencia_bancos, el_brifin, cevaldom)

RDZ = ZoneInfo("America/Santo_Domingo")
_ISO = r'(\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:?\d\d)?)?)'

def a_rd(s):
    """'2026-11-18T14:35:00-04:00' -> ('2026-11-18', '14:35') en hora de RD. Sin hora -> (fecha, None)."""
    if not s: return None, None
    s = s.strip().replace(" ", "T")
    if len(s) == 10: return s, None
    try:
        x = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if x.tzinfo: x = x.astimezone(RDZ)
        hh = x.strftime("%H:%M")
        return x.date().isoformat(), (None if hh == "00:00" else hh)  # 00:00 = el medio solo publica la fecha
    except ValueError:
        return s[:10], None

def _publicado(h):
    for rx in (r'property="article:published_time"\s+content="' + _ISO, r'content="' + _ISO + r'"\s+property="article:published_time"',
               r'"datePublished"\s*:\s*"' + _ISO, r'itemprop="datePublished"[^>]*content="' + _ISO, r'<time[^>]+datetime="' + _ISO):
        m = re.search(rx, h)
        if m: return a_rd(m[1])
    return None, None

def fecha_articulo(u, con_hora=False):
    """Fecha (y hora RD) de publicación leída de la propia nota (metadatos estándar de los periódicos)."""
    try:
        h = requests.get(u, headers=UA, timeout=30).text[:400000]
    except Exception:
        return (None, None) if con_hora else None
    f, hr = _publicado(h)
    return (f, hr) if con_hora else f

# Páginas anteriores de cada medio (las que tienen paginación estable)
PAGINAS = [
    (diario_financiero, lambda n: f"https://diariofinanciero.do/category/economia/page/{n}/", 400),
    (revista_mercado, lambda n: f"https://revistamercado.do/category/empresas/page/{n}/", 400),
    (revista_mercado, lambda n: f"https://revistamercado.do/category/money-invest/page/{n}/", 400),
    (listin, lambda n: f"https://listindiario.com/economia/{n}", 1500),
    (hoy, lambda n: f"https://hoy.com.do/economia/{n}/", 1000),
    (el_nuevo_diario, lambda n: f"https://elnuevodiario.com.do/economia/page/{n}/", 3000),
    (n_digital, lambda n: f"https://n.com.do/economia/page/{n}/", 1500),
    (micm, lambda n: f"https://micm.gob.do/noticias/page/{n}/", 600),
    (el_brifin, lambda n: f"https://elbrifin.com/category/temas/economia-y-finanzas/page/{n}/", 30),
    
]

def historial(conocidas):
    """Recorre páginas anteriores hasta llegar a 2025 (o hasta que una página no traiga nada nuevo)."""
    res = []
    for fn, url, maxp in PAGINAS:
        vacias = 0
        for n in range(2, maxp + 1):
            try:
                L = [x for x in fn(url(n)) if x["u"] not in conocidas]
            except Exception as e:
                print(f"{url(n)}: ERROR {e}", file=sys.stderr); break
            # sin fecha en el enlace: se lee la fecha de la primera nota de la página y se aplica a toda la página
            # (las páginas van de la más nueva a la más vieja, así que el margen es de uno o dos días)
            f0 = None
            if any(not x.get("d") for x in L):
                f0 = fecha_articulo(L[-1]["u"]); time.sleep(0.3)
            for x in L:
                conocidas.add(x["u"])
                if not x.get("d"): x["d"] = f0
            res += L
            fechas = [x["d"] for x in L if x.get("d")]
            print(f"{url(n)}: {len(L)} nuevos · {min(fechas) if fechas else '-'}")
            vacias = vacias + 1 if not L else 0
            if vacias >= 3 or (fechas and max(fechas) < DESDE): break
            time.sleep(1)
    for pg in range(0, 40):  # Banco Central: API paginada
        L = [x for x in banco_central(pg, 50) if x["u"] not in conocidas]
        for x in L: conocidas.add(x["u"])
        res += L
        fechas = [x["d"] for x in L if x.get("d")]
        print(f"Banco Central página {pg}: {len(L)} · {min(fechas) if fechas else '-'}")
        if not L or (fechas and max(fechas) < DESDE): break
    return res

# ---------- Archivo vía sitemaps (las portadas solo muestran las últimas semanas) ----------
def _locs(url):
    try:
        c = requests.get(url, headers=UA, timeout=60).content
        try:
            import gzip; x = gzip.decompress(c).decode("utf-8", "ignore")  # algunos sitemaps vienen comprimidos (.xml.gz)
        except OSError:
            x = c.decode("utf-8", "ignore")
    except Exception:
        return []
    return re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", x)

def _locs_fecha(url):
    """Como _locs, pero con la fecha <lastmod> de cada nota (sirve para descartar notas viejas sin abrirlas)."""
    try:
        c = requests.get(url, headers=UA, timeout=60).content
        try:
            import gzip; x = gzip.decompress(c).decode("utf-8", "ignore")
        except OSError:
            x = c.decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    if "<url" not in x:  # sitemap en texto plano (una URL por línea)
        return [(l.strip(), None) for l in x.splitlines() if l.strip().startswith("http")]
    for b in re.findall(r"<url>(.*?)</url>", x, re.S):
        m = re.search(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", b)
        lm = re.search(r"<lastmod>\s*(\d{4}-\d\d-\d\d)", b)
        if m: out.append((m[1], lm[1] if lm else None))
    return out

def _meses():
    d, fin, out = dt.date(int(DESDE[:4]), int(DESDE[5:7]), 1), dt.date.fromisoformat(HOY), []
    while d <= fin:
        out.append(d); d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out

def _indice(url, filtro):
    return [s for s in _locs(url) if filtro(s)]

ARCHIVO = [  # (fuente, sitemaps, filtro de URL de nota económica, categoría)
    ("Diario Libre", lambda: _indice("https://www.diariolibre.com/sitemap.xml", lambda s: "sitemapnoticias" in s),
     lambda u: re.search(r"diariolibre\.com/economia/[a-z-]+/(\d{4})/\d\d/\d\d/", u), "Economía"),
    # Listín Diario no publica sitemaps de noticias posteriores a mayo de 2023: su archivo solo llega hasta donde llega su portada
    ("Hoy", lambda: _indice("https://hoy.com.do/sitemap-index.xml", lambda s: "sitemap-noticias-" in s),
     lambda u: re.search(r"hoy\.com\.do/economia/[a-z0-9-]{10,}_\d+\.html", u), "Economía"),
    ("Diario Financiero", lambda: _indice("https://diariofinanciero.do/sitemap_index.xml", lambda s: "post-sitemap" in s),
     lambda u: (m := re.match(r"https://diariofinanciero\.do/([a-z-]+)/[a-z0-9-]{12,}/?$", u)) and m[1] not in EXCLUIR_DF + ("herramientas-financieras",), "Economía"),
    ("CDN", lambda: _indice("https://cdn.com.do/sitemaps.xml", lambda s: "sitemap-post-" in s),
     lambda u: re.match(r"https://cdn\.com\.do/economicas/[a-z0-9-]{12,}/?$", u), "Economía"),
    ("Acento", lambda: _indice("https://acento.com.do/sitemaps/sitemaps-index.xml", lambda s: "acento-" in s),
     lambda u: re.match(r"https://acento\.com\.do/economia/", u), "Economía"),
    ("MICM", lambda: _indice("https://micm.gob.do/sitemap_index.xml", lambda s: "post-sitemap" in s),
     lambda u: re.match(r"https://micm\.gob\.do/[a-z0-9-]{25,}/?$", u), "Comercio e industria"),
    ("Superintendencia de Bancos", lambda: ["https://sb.gob.do/sitemap/"],
     lambda u: re.match(r"https://(www\.)?sb\.gob\.do/publicaciones/cronologia-sb/publicaciones-de-prensa/archivo-de-prensa/[^/]{12,}/?$", u), "Banca"),
    ("DGII", lambda: ["https://dgii.gov.do/sitemap0.xml"],
     lambda u: re.search(r"dgii\.gov\.do/noticias/Paginas/(?!default).+\.aspx$", u), "Impuestos"),
    ("Revista Mercado", lambda: _indice("https://www.revistamercado.do/sitemap_index.xml", lambda s: "post-sitemap" in s),
     lambda u: re.match(r"https://revistamercado\.do/(empresas|money-invest|business|market-brief)/(?!daily-news)", u), "Empresas"),
]

def nota(u):
    """Título y fecha de publicación leídos de la propia nota."""
    try:
        h = requests.get(u, headers=UA, timeout=30).text[:400000]
    except Exception:
        return None, (None, None)
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', h) or re.search(r"<title>(.*?)</title>", h, re.S)
    t = limpio(BeautifulSoup(m[1], "html.parser").get_text()) if m else None
    if t: t = re.sub(r"\s*[|–-]\s*(Diario Libre|Listín Diario|Hoy Digital|Diario Financiero|Revista Mercado|Mercado|El Nuevo Diario|N Digital|CDN|Acento|MICM|DGII|SB|Superintendencia de Bancos[^|]*)\s*$", "", t)
    f = _publicado(h)
    if not f[0]:  # páginas sin metadatos (p. ej. DGII): primera fecha dd/mm/aaaa del texto
        m = re.search(r"\b(\d\d)/(\d\d)/(20\d\d)\b", re.sub(r"<[^>]+>", " ", h))
        if m: f = (f"{m[3]}-{m[2]}-{m[1]}", None)
    return t, f

def archivo(conocidas, maximo, subir=None):
    cand = []
    for fuente, sitemaps, filtro, cat in ARCHIVO:
        n0 = len(cand)
        for s in sitemaps():
            for u, lm in _locs_fecha(s):
                u = u.split("?")[0].replace("http://dgii.gov.do:80/", "https://dgii.gov.do/").replace("http://dgii.gov.do/", "https://dgii.gov.do/")
                if lm and lm < DESDE: continue  # nota modificada por última vez antes de 2025: no puede ser de 2025 en adelante
                if u not in conocidas and filtro(u):
                    conocidas.add(u); m = re.search(r"/(\d{4})/?(\d\d)/?(\d\d)/", u)
                    cand.append({"s": fuente, "u": u, "c": cat, "d": f"{m[1]}-{m[2]}-{m[3]}" if m else None})
            time.sleep(0.5)
        print(f"Archivo {fuente}: {len(cand) - n0} notas nuevas en los sitemaps")
    cand = [c for c in cand if not c["d"] or c["d"] >= DESDE]
    cand.sort(key=lambda c: c["d"] or "9999", reverse=True)
    por = {}
    for c in cand: por.setdefault(c["s"], []).append(c)
    cand = [c for grupo in zip(*[g + [None] * (max(map(len, por.values())) - len(g)) for g in por.values()]) for c in grupo if c] if por else []
    out = []
    from concurrent.futures import ThreadPoolExecutor
    lote = cand[:maximo]
    with ThreadPoolExecutor(max_workers=10) as ex:  # 6 descargas a la vez (repartidas entre 5 medios)
        for i, (c, (t, (f, hr))) in enumerate(zip(lote, ex.map(lambda c: nota(c["u"]), lote))):
            if t and len(t) > 20:
                c["t"] = t
                if not c["d"] or c["d"] == f: c["d"], c["h"] = f or c["d"], hr
                if c["d"] and c["d"] >= DESDE: out.append(c)
            if i % 500 == 0: print(f"  … {i} de {len(lote)}", flush=True)
            if subir and len(out) >= 1000:  # sube por partes: el avance se ve en la terminal sin esperar al final
                subir(out); print(f"  subidos {len(out)}", flush=True); out = []
    print(f"Archivo: {len(out)} titulares agregados ({max(0, len(cand) - maximo)} pendientes para la próxima corrida)")
    return out

def solo_archivo(maximo):
    """Tanda del archivo histórico: va directo a la tabla de Supabase (no toca el estado del robot de 30 minutos)."""
    import supa
    k = supa.enlaces_noticias()
    try:
        k |= {n["u"] for n in json.load(open("data/noticias.json", encoding="utf-8"))}
    except FileNotFoundError:
        pass
    print(f"Titulares ya guardados en la tabla: {len(k)}")
    limpio_ = lambda L: [n for n in L if n.get("t") and n.get("d") and "/categoria/" not in n["u"] and "/category/" not in n["u"]]
    sub = lambda L: supa.subir_noticias(limpio_(L))
    print(f"Páginas anteriores: {sub(historial(k))} subidos", flush=True)
    print(f"Sitemaps (último lote): {sub(archivo(k, maximo, sub))} subidos")

def main():
    if "--archivo" in sys.argv:
        i = sys.argv.index("--archivo")
        return solo_archivo(int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 12000)
    try:
        viejas = json.load(open("data/noticias.json", encoding="utf-8"))
    except FileNotFoundError:
        viejas = []
    previas = {n["u"]: n for n in viejas}
    nuevas, de_archivo = [], set()
    AHORA = dt.datetime.now(RDZ).strftime("%H:%M")  # hora en que el robot ve el titular (hora RD)
    for fuente in FUENTES:
        try:
            n = fuente(); nuevas += n; print(f"{fuente.__name__}: {len(n)} titulares")
        except Exception as e:  # si una fuente falla, no detiene el resto
            print(f"{fuente.__name__}: ERROR {e}", file=sys.stderr)
    # titulares nuevos: se lee la fecha y la hora de publicación en la propia nota (máx. 150 por corrida)
    vistas_ahora, sin_hora = set(), []
    for n in nuevas:
        if n["u"] not in previas and n["u"] not in vistas_ahora and not n.get("h"):
            vistas_ahora.add(n["u"]); sin_hora.append(n)
    for n in sin_hora[:150]:
        f, hr = fecha_articulo(n["u"], True); time.sleep(0.2)
        if f and (not n.get("d") or n["d"] == f): n["d"], n["h"] = f, hr
        elif not n.get("d"): n["d"] = f
    print(f"Fecha/hora leídas de la nota: {sum(1 for n in sin_hora[:150] if n.get('h'))} con hora de {len(sin_hora[:150])}")
    # titulares ya guardados de los últimos 3 días que aún no tienen hora (una sola vez por titular)
    lim = (dt.date.fromisoformat(HOY) - dt.timedelta(days=3)).isoformat()
    pend = [n for n in viejas if (n.get("d") or "") >= lim and not n.get("h") and not n.get("ht")][:300]
    for n in pend:
        f, hr = fecha_articulo(n["u"], True); time.sleep(0.2); n["ht"] = 1
        if f and n.get("d") in (None, f, n.get("v")): n["d"], n["h"] = f, hr
    if pend: print(f"Hora agregada a titulares recientes: {sum(1 for n in pend if n.get('h'))} de {len(pend)}")
    nuevas = [n for n in nuevas if not n.get("d") or n["d"] >= DESDE]
    vistos, todas = set(), []
    for n in nuevas + viejas:  # sin duplicados por enlace
        if n["u"] in vistos or "/categoria/" in n["u"] or "/category/" in n["u"] or any(x in n["u"] for x in EXCLUIR_U): continue  # páginas de sección o notas descartadas
        vistos.add(n["u"])
        p = previas.get(n["u"])
        n["v"] = (p or {}).get("v") or n.get("v") or (None if p else HOY)  # primera vez que Ámbar vio el titular
        if p and p.get("vh"): n["vh"] = p["vh"]
        elif not p and n["u"] not in de_archivo: n["vh"] = AHORA  # hora RD de esa primera vez
        if not n.get("d"): n["d"] = (p or {}).get("d") or n["v"]
        for k in ("h", "ht"):  # conservar la hora ya leída (la portada vuelve a traer el titular sin hora)
            if p and p.get(k) and not n.get(k): n[k] = p[k]  # sin fecha publicada: se usa la primera vez visto
        todas.append(n)
    todas.sort(key=lambda n: (n.get("d") or "", n.get("h") or "", n.get("v") or ""), reverse=True)
    cuenta, final = {}, []
    for n in todas:
        cuenta[n["s"]] = cuenta.get(n["s"], 0) + 1
        if cuenta[n["s"]] <= POR_FUENTE: final.append(n)
    json.dump(final, open("data/noticias.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    if os.environ.get("SUPABASE_URL"):
        import supa
        print(f"Titulares enviados a la tabla de Supabase: {supa.subir_noticias(todas)}")
    print(f"Total guardado: {len(final)} · " + ", ".join(f"{k}: {min(v, POR_FUENTE)}" for k, v in cuenta.items()))

if __name__ == "__main__":
    main()
