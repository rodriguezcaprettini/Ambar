"""
Revisa la página pública de boletines de la BVRD (https://boletines.bvrd.com.do/) con un navegador
automático y anota la PRIMERA hora (RD) en que aparece cada boletín en la página.
El calendario se arma con JavaScript, por eso se abre con un navegador real (Chromium sin pantalla).

Guarda:
  data/publicacion.json  -> {fecha: {"en_servidor": hora, "en_pagina": hora}}
  data/calendario_red.txt -> direcciones que consulta el calendario (para diagnóstico)
Solo escribe los archivos si hay algo nuevo. Requisitos: pip install playwright && playwright install chromium
Se ejecuta desde la raíz del repositorio.
"""
import datetime as dt, json, os, re, sys
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

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

    textos, red = [], set()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="es-DO", timezone_id="America/Santo_Domingo", viewport={"width": 1366, "height": 900})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        pg = ctx.new_page()
        fallas = []
        pg.on("requestfailed", lambda r: fallas.append(f"FALLÓ {r.url} {r.failure}"))
        def resp(r):
            u = r.url
            if any(u.endswith(x) for x in (".png", ".jpg", ".svg", ".woff", ".woff2", ".css", ".ico")): return
            red.add(u.split("?")[0])
            try:
                if "json" in (r.headers.get("content-type") or "") or "api" in u.lower():
                    textos.append(r.text())
            except Exception:
                pass
        pg.on("response", resp)
        estado = pg.goto(URL, wait_until="networkidle", timeout=90_000)
        pg.wait_for_timeout(6000)
        html = pg.content(); textos.append(html)
        texto_visible = pg.inner_text("body") if pg.query_selector("body") else ""
        textos += [a for a in pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href + ' ' + e.textContent)")]
        b.close()
    todo = "\n".join(textos)
    todo_dec = todo.replace("+", " ").replace("%20", " ")

    cambios = False
    for d in vigilar:
        k = d.isoformat(); visto = any(x in todo or x in todo_dec for x in patrones(d)[:1])
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
             + "\n\n# HTML (primeros 3000 caracteres)\n" + html[:3000] + "\n")
    try:
        viejo = open("data/calendario_red.txt", encoding="utf-8").read()
    except FileNotFoundError:
        viejo = ""
    if nuevo != viejo:
        open("data/calendario_red.txt", "w", encoding="utf-8").write(nuevo)
    print(f"Estado HTTP {estado.status if estado else '-'} · direcciones consultadas: {len(red)} · peticiones fallidas: {len(set(fallas))} · textos revisados: {len(textos)} ({len(todo):,} caracteres)")
    print("Texto visible:", re.sub(r"\s+", " ", texto_visible)[:300])
    if len(todo) < 2000:
        print("AVISO: la página devolvió muy poco contenido; puede que el calendario no haya cargado.", file=sys.stderr)

if __name__ == "__main__":
    main()
