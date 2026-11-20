"""
Respaldo completo de Ámbar en Supabase: esquema (migraciones, funciones, políticas), todas las tablas,
usuarios (sin contraseñas) y todos los archivos de almacenamiento (datos de la terminal y fotos de perfil).
Genera un .zip y lo sube al bucket PRIVADO "respaldos" (se conservan los últimos 8).
Necesita SUPABASE_URL y SUPABASE_SERVICE_KEY (secretos de GitHub).
Uso: python scripts/respaldo.py
"""
import datetime, io, json, os, zipfile
import requests

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
H = {"apikey": KEY} if KEY.startswith("sb_") else {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
BUCKETS = ["ambar-data", "avatars"]
CONSERVAR = 8


def rpc(nombre):
    r = requests.post(f"{URL}/rest/v1/rpc/{nombre}", headers=H, json={}, timeout=120)
    r.raise_for_status()
    return r.json()


def tabla(nombre):
    filas, desde, paso = [], 0, 1000
    while True:
        r = requests.get(f"{URL}/rest/v1/{nombre}?select=*", headers={**H, "Range-Unit": "items", "Range": f"{desde}-{desde+paso-1}"}, timeout=120)
        r.raise_for_status()
        lote = r.json()
        filas += lote
        if len(lote) < paso:
            return filas
        desde += paso


def usuarios():
    out, pag = [], 1
    while True:
        r = requests.get(f"{URL}/auth/v1/admin/users", headers=H, params={"page": pag, "per_page": 1000}, timeout=120)
        r.raise_for_status()
        lote = r.json().get("users", [])
        out += [{k: u.get(k) for k in ("id", "email", "created_at", "last_sign_in_at", "email_confirmed_at", "user_metadata")} for u in lote]
        if len(lote) < 1000:
            return out
        pag += 1


def listar(bucket, prefijo=""):
    items, off = [], 0
    while True:
        r = requests.post(f"{URL}/storage/v1/object/list/{bucket}", headers=H, json={"prefix": prefijo, "limit": 1000, "offset": off}, timeout=120)
        r.raise_for_status()
        lote = r.json()
        for it in lote:
            ruta = f"{prefijo}{it['name']}"
            if it.get("id") is None:  # carpeta
                items += listar(bucket, ruta + "/")
            else:
                items.append(ruta)
        if len(lote) < 1000:
            return items
        off += 1000


def main():
    hoy = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d_%H%M")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        esq = rpc("ambar_esquema")
        z.writestr("esquema/esquema.json", json.dumps(esq, ensure_ascii=False, indent=1))
        for m in esq.get("migraciones") or []:
            z.writestr(f"esquema/migraciones/{m['version']}_{m['nombre']}.sql", m["sql"] + ";\n")
        z.writestr("esquema/funciones.sql", "\n\n".join(f["sql"] + ";" for f in esq.get("funciones") or []))
        for t in esq.get("tablas_lista") or []:
            filas = tabla(t)
            z.writestr(f"tablas/{t}.json", json.dumps(filas, ensure_ascii=False))
            print(f"tabla {t}: {len(filas)} filas")
        u = usuarios()
        z.writestr("usuarios/usuarios.json", json.dumps(u, ensure_ascii=False, indent=1))
        print(f"usuarios: {len(u)}")
        for b in BUCKETS:
            rutas = listar(b)
            for ruta in rutas:
                r = requests.get(f"{URL}/storage/v1/object/{b}/{ruta}", headers=H, timeout=300)
                r.raise_for_status()
                z.writestr(f"almacenamiento/{b}/{ruta}", r.content)
            print(f"almacenamiento {b}: {len(rutas)} archivos")
        z.writestr("LEEME.txt", "Respaldo de Ámbar del " + hoy + " (UTC).\n"
                   "esquema/: migraciones SQL en orden, funciones y políticas de seguridad.\n"
                   "tablas/: cada tabla en JSON (noticias, perfiles, chat, códigos de invitación, preferencias…).\n"
                   "usuarios/: cuentas (correo, fechas, datos de registro). Las contraseñas NO se guardan: al restaurar, cada usuario debe pedir una nueva.\n"
                   "almacenamiento/: archivos de los buckets ambar-data (datos de la terminal) y avatars (fotos de perfil).\n")
    datos = buf.getvalue()
    nombre = f"ambar_respaldo_{hoy}.zip"
    r = requests.post(f"{URL}/storage/v1/object/respaldos/{nombre}", headers={**H, "content-type": "application/zip", "x-upsert": "true"}, data=datos, timeout=600)
    r.raise_for_status()
    print(f"Subido respaldos/{nombre} ({len(datos)/1e6:.1f} MB)")
    viejos = sorted(listar("respaldos"))[:-CONSERVAR]
    if viejos:
        requests.delete(f"{URL}/storage/v1/object/respaldos", headers=H, json={"prefixes": viejos}, timeout=120)
        print(f"Borrados {len(viejos)} respaldos antiguos")


if __name__ == "__main__":
    main()
