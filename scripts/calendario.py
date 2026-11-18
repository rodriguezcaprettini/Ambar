"""
Revisa si cada boletín ya aparece en la página pública de la BVRD (https://boletines.bvrd.com.do/) y anota
la PRIMERA hora (RD) en que aparece. El calendario de esa página se arma con la lista
https://prod-data.bvrd.com.do/json/boletines.json, así que se lee esa lista directamente (rápido).
Si la lista falla, se usa como respaldo un navegador automático (python scripts/calendario.py --navegador).

Guarda:
  data/publicacion.json  -> {fecha: {"en_servidor": hora, "en_pagina": hora}}
  data/calendario_red.txt -> direcciones que consulta el calendario (para diagnóstico)
Solo escribe los archivos si hay algo nuevo. Requisitos: pip install requests (y playwright solo para el respaldo con --navegador)
Se ejecuta desde la raíz del repositorio.
"""
import datetime as dt, json, os, re, sys
from zoneinfo import ZoneInfo
import requests

LISTA = os.environ.get("CALENDARIO_LISTA", "https://prod-data.bvrd.com.do/json/boletines.json")

RD = ZoneInfo("America/Santo_Domingo")
URL = os.environ.get("CALENDARIO_URL", "https://boletines.bvrd.com.do/")

def cargar(ruta, defecto):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defecto

def patrones(d):
    """Formas en que puede aparecer la fecha de un boletín en la página o en sus datos."""
    return [f"{d:%d-%m-%Y}-Boletin", f"{d:%d-%m-%Y}", f"{d:%Y-%m-%d}", f"{d:%d/%m/%Y}"]

def main():
    ahora = dt.datetime.now(RD); hoy = ahora.date()
    pub = cargar("data/publicacion.json", {}); desc = cargar("data/descargas.json", {})
    # fechas a vigilar: solo boletines que el robot vio llegar al servidor (descargas.json) en los últimos 7 días
    # y que aún no aparecen en la página. Los días anteriores al registro no se miden: ya estaban publicados.
    vigilar = [dt.date.fromisoformat(k) for k, v in desc.items()
               if v.get("primera_vez") and (hoy - dt.date.fromisoformat(k)).days <= 7
               and not pub.get(k, {}).get("en_pagina")]
    if not vigilar:
        print("Nada pendiente."); return

    textos, red, fallas, estado, html, texto_visible = [], set(), [], None, "", ""
    usar_nav = "--navegador" in sys.argv
    if not usar_nav:
        try:
            r = requests.get(LISTA, timeout=60, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36",
                                                         "Referer": "https://boletines.bvrd.com.do/"})
            r.raise_for_status(); r.json()
            textos.append(r.text); red.add(LISTA); html = r.text; texto_visible = "(lista JSON)"
            class E: status = r.status_code
            estado = E()
        except Exception as e:
            print(f"No se pudo leer la lista JSON ({e}); hace falta el navegador.", file=sys.stderr)
            sys.exit(3)  # el robot instala el navegador y vuelve a correr con --navegador
    else:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
            ctx = b.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="es-DO", timezone_id="America/Santo_Domingo", viewport={"width": 1366, "height": 900})
            ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            pg = ctx.new_page()
            pg.on("requestfailed", lambda r: fallas.append(f"FALLÓ {r.url} {r.failure}"))
            def resp(r):
                u = r.url
                if any(u.endswith(x) for x in (".png", ".jpg", ".svg", ".woff", ".woff2", ".css", ".ico")): return
                red.add(u.split("?")[0])
                try:
                    if "json" in (r.headers.get("content-type") or "") or u.endswith(".json"): textos.append(r.text())
                except Exception: pass
            pg.on("response", resp)
            estado = pg.goto(URL, wait_until="networkidle", timeout=90_000)
            pg.wait_for_timeout(6000)
            html = pg.content(); textos.append(html)
            texto_visible = pg.inner_text("body") if pg.query_selector("body") else ""
            b.close()
    todo = "\n".join(textos)
    todo_dec = todo.replace("+", " ").replace("%20", " ")

    cambios = False
    for d in vigilar:
        k = d.isoformat(); visto = any(x in todo or x in todo_dec for x in patrones(d))
        reg = pub.setdefault(k, {})
        if desc.get(k, {}).get("primera_vez") and reg.get("en_servidor") != desc[k]["primera_vez"]:
            reg["en_servidor"] = desc[k]["primera_vez"]; cambios = True
        if visto:
            reg["en_pagina"] = ahora.strftime("%Y-%m-%d %H:%M"); cambios = True
            print(f"{k}: ✔ aparece en la página ({reg['en_pagina']})")
        else:
            print(f"{k}: aún no aparece en la página")
    pub = {k: v for k, v in pub.items() if v}
    if cambios:
        json.dump(dict(sorted(pub.items())), open("data/publicacion.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # diagnóstico: direcciones que usa el calendario y lo que devolvió la página (solo se guarda si cambia)
    nuevo = (f"Estado HTTP: {estado.status if estado else '-'}\n\n# Direcciones consultadas\n" + "\n".join(sorted(red))
             + "\n\n# Peticiones fallidas\n" + "\n".join(sorted(set(fallas)))
             + "\n\n# Texto visible (primeros 1500 caracteres)\n" + texto_visible[:1500]
             + "\n\n# Contenido recibido (primeros 3000 caracteres)\n" + html[:3000] + "\n")
    try:
        viejo = open("data/calendario_red.txt", encoding="utf-8").read()
    except FileNotFoundError:
        viejo = ""
    if nuevo != viejo:
        open("data/calendario_red.txt", "w", encoding="utf-8").write(nuevo)
    print(f"Estado HTTP {estado.status if estado else '-'} · direcciones consultadas: {len(red)} · peticiones fallidas: {len(set(fallas))} · textos revisados: {len(textos)} ({len(todo):,} caracteres)")
    print("Texto visible:", re.sub(r"\s+", " ", texto_visible)[:300])
    if len(todo) < 500:
        print("AVISO: se recibió muy poco contenido; puede que la lista o el calendario no hayan cargado.", file=sys.stderr)

if __name__ == "__main__":
    main()
