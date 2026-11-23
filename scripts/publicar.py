"""
Registro de publicaciones: cada robot, al terminar, anota en la tabla public.publicaciones el último periodo
que encontró de cada conjunto de datos (BVRD y Banco Central). La clave (conjunto, periodo) es única, así que
cada dato nuevo se anota una sola vez, con la hora en que el robot lo vio por primera vez.
Uso: python scripts/publicar.py   (lee lo que haya en data/out: data.json, fx.json, macro.json)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import supa

BC = "Banco Central"
EV = []


def ult(rows, col=None):
    """Último periodo con dato (las filas empiezan con la fecha)."""
    for r in reversed(rows or []):
        if col is None or (len(r) > col and r[col] is not None): return r[0]
    return None


def poner(fuente, conjunto, titulo, periodo, ruta):
    import datetime
    if periodo and str(periodo)[:7] < (datetime.date.today() - datetime.timedelta(days=400)).isoformat()[:7]:
        return  # serie que el Banco Central ya no actualiza (p. ej. derivados): no se anuncia
    if periodo: EV.append({"fuente": fuente, "conjunto": conjunto, "titulo": titulo, "periodo": str(periodo), "ruta": ruta})


def leer(f):
    p = os.path.join("data/out", f)
    if not os.path.exists(p): return None
    try: return json.load(open(p, encoding="utf-8"))
    except Exception as e: print(f, "no se pudo leer:", e); return None


d = leer("data.json")
if d and d.get("D", {}).get("fecha"):
    poner("BVRD", "bvrd_boletin", "Boletín consolidado de la BVRD (sesión)", d["D"]["fecha"], "mercado")
fx = leer("fx.json")
if fx:
    poner(BC, "fx_ref", "Tasa de cambio de referencia USD/DOP", ult(fx.get("ref"), 2), "fx:ref")
    poner(BC, "fx_prom", "Tasas promedio de compra y venta (entidades y agentes)", ult(fx.get("ef"), 2), "fx:prom")
    poner(BC, "fx_otras", "Tasas de otras monedas", ult(fx.get("otras", {}).get("rows")), "fx:otr")
    poner(BC, "fx_sondeo", "Sondeo de cotizaciones (dólar y euro)", max([ult(v) for v in fx.get("sondeo", {}).values() if v] or [None]), "fx:son")
    poner(BC, "fx_der", "Mercado de derivados cambiarios", ult(fx.get("der")), "fx:der")
    poner(BC, "fx_vol", "Volatilidad cambiaria", max([ult(v.get("rows")) for v in fx.get("vol", {}).values() if v.get("rows")] or [None]), "fx:vol")
    poner(BC, "fx_volumen", "Volumen de operaciones cambiarias (mensual)", ult(fx.get("volumen", {}).get("rows")), "fx:volu")
mc = leer("macro.json")
if mc:
    F, s = mc["fechas"], mc["series"]
    def mes(k): return next((F[i] for i in range(len(F) - 1, -1, -1) if s.get(k) and s[k][i] is not None), None)
    poner(BC, "ipc", "Índice de Precios al Consumidor (inflación)", mes("gen"), "macro:inf")
    poner(BC, "ipc_sub", "IPC subyacente", mes("sub"), "macro:inf")
    poner(BC, "ipc_art", "IPC por artículos", (mc.get("art", {}).get("fechas") or [None])[-1], "macro:inf")

if not EV:
    print("Nada que registrar."); sys.exit(0)
r = supa.rest("POST", "publicaciones?on_conflict=conjunto,periodo", json=EV,
              extra={"Prefer": "resolution=ignore-duplicates,return=representation", "content-type": "application/json"})
if r.status_code >= 300:
    print("Error registrando publicaciones:", r.status_code, r.text[:300]); sys.exit(0)
nuevos = r.json() if r.text else []
print(f"{len(EV)} conjuntos revisados · {len(nuevos)} publicaciones nuevas:", [(n['conjunto'], n['periodo']) for n in nuevos])
