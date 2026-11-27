"""
Sube y baja archivos del almacenamiento PRIVADO de Supabase (bucket "ambar-data").
Necesita dos secretos de GitHub (Settings → Secrets and variables → Actions):
  SUPABASE_URL          ej. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  la clave secreta (service_role / sb_secret_...). Nunca va en el código.
Uso (desde la raíz del repositorio):
  python scripts/supa.py bajar-estado   -> trae los CSV/JSON de trabajo del robot (si existen en Supabase)
  python scripts/supa.py subir          -> sube lo que lee la terminal (data/out) y el estado del robot
"""
import glob, mimetypes, os, sys
import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = "ambar-data"
ESTADO = ["operaciones.csv", "primario.csv", "puestos.csv", "precios.csv", "emisiones.csv", "emisiones_fecha.txt", "noticias.json",
          "descargas.json", "publicacion.json", "calendario_red.txt"]

def headers(extra=None, bearer=None):
    h = {"apikey": KEY}
    if bearer if bearer is not None else not KEY.startswith("sb_"):
        h["Authorization"] = f"Bearer {KEY}"
    h.update(extra or {})
    return h

def pedir(metodo, ruta, **kw):
    """Hace la petición; si la clave nueva (sb_secret_) es rechazada sin 'Authorization', reintenta con ella."""
    extra = kw.pop("extra", None)
    import time
    for intento in range(4):  # reintenta si Supabase/Cloudflare responde con un error temporal (5xx) o se corta la conexión
        try:
            r = requests.request(metodo, f"{URL}/storage/v1/{ruta}", headers=headers(extra), timeout=120, **kw)
            if r.status_code < 500: break
        except requests.RequestException:
            if intento == 3: raise
        time.sleep(5 * (intento + 1))
    if r.status_code in (400, 401, 403) and KEY.startswith("sb_"):
        r = requests.request(metodo, f"{URL}/storage/v1/{ruta}", headers=headers(extra, bearer=True), timeout=120, **kw)
    return r

def subir_archivo(local, remoto):
    tipo = "application/json" if local.endswith(".json") else (mimetypes.guess_type(local)[0] or "text/plain")
    with open(local, "rb") as fh:
        r = pedir("POST", f"object/{BUCKET}/{remoto}", data=fh.read(), extra={"x-upsert": "true", "content-type": tipo, "cache-control": "max-age=60"})  # el navegador no guarda copias viejas más de 1 min
    if r.status_code >= 300:
        raise SystemExit(f"Error subiendo {remoto}: {r.status_code} {r.text[:300]}")

def bajar_archivo(remoto, local):
    r = pedir("GET", f"object/authenticated/{BUCKET}/{remoto}")
    if r.status_code == 200:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        open(local, "wb").write(r.content); return True
    if r.status_code in (400, 404):
        return False
    raise SystemExit(f"Error bajando {remoto}: {r.status_code} {r.text[:300]}")

def rest(metodo, ruta, **kw):
    """PostgREST (tablas). Con la clave secreta nueva basta 'apikey'; con la vieja (JWT) también va 'Authorization'."""
    extra = kw.pop("extra", None)
    r = requests.request(metodo, f"{URL}/rest/v1/{ruta}", headers=headers(extra), timeout=120, **kw)
    if r.status_code in (400, 401, 403) and KEY.startswith("sb_") and "Authorization" not in headers():
        r2 = requests.request(metodo, f"{URL}/rest/v1/{ruta}", headers=headers(extra, bearer=True), timeout=120, **kw)
        if r2.status_code < 300: return r2
    return r

COLS_NOT = ("u", "s", "t", "d", "h", "vh", "v", "c")

def subir_noticias(filas):
    """Inserta o actualiza titulares en la tabla public.noticias (clave: el enlace)."""
    unicas = {}
    for f in filas:  # un mismo enlace no puede ir dos veces en el mismo envío
        if f.get("u") and f.get("t"): unicas[f["u"]] = {k: (f.get(k) or None) for k in COLS_NOT}
    filas = list(unicas.values())
    for i in range(0, len(filas), 1000):
        r = rest("POST", "noticias?on_conflict=u", json=filas[i:i + 1000],
                 extra={"Prefer": "resolution=merge-duplicates,return=minimal", "content-type": "application/json"})
        if r.status_code >= 300:
            raise SystemExit(f"Error subiendo noticias: {r.status_code} {r.text[:300]}")
    return len(filas)

def enlaces_noticias():
    """Todos los enlaces ya guardados en la tabla (para no volver a descargar notas conocidas)."""
    out, desde = set(), 0
    while True:
        r = rest("GET", f"noticias?select=u&order=u&offset={desde}&limit=1000")
        if r.status_code >= 300: raise SystemExit(f"Error leyendo noticias: {r.status_code} {r.text[:300]}")
        L = r.json(); out |= {x["u"] for x in L}; desde += len(L)
        if len(L) < 1000: return out

def main():
    if not URL or not KEY:
        raise SystemExit("Faltan los secretos SUPABASE_URL y/o SUPABASE_SERVICE_KEY en GitHub.")
    accion = sys.argv[1] if len(sys.argv) > 1 else ""
    if accion == "bajar-estado":
        n = sum(bajar_archivo(f"estado/{f}", f"data/{f}") for f in ESTADO)
        print(f"Estado bajado de Supabase: {n} de {len(ESTADO)} archivos" + (" (primera vez: se usan los del repositorio)" if n == 0 else ""))
    elif accion == "subir":
        # ruta remota siempre con "/" (en Windows glob devuelve "\")
        archivos = [(f, os.path.relpath(f, "data/out").replace(os.sep, "/")) for f in glob.glob("data/out/**/*.json", recursive=True)]
        archivos += [(f"data/{f}", f"estado/{f}") for f in ESTADO if os.path.exists(f"data/{f}")]
        for local, remoto in archivos:
            subir_archivo(local, remoto)
        print(f"Subidos a Supabase ({BUCKET}): {len(archivos)} archivos")
    else:
        raise SystemExit(__doc__)

if __name__ == "__main__":
    main()
