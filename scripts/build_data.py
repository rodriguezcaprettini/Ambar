"""
Convierte los CSV de data/ en los archivos que lee la terminal (index.html):
  data/out/data.json          -> archivo principal liviano (la terminal lo baja al iniciar sesión)
  data/out/ops/AAAA-MM.json   -> operaciones de cada mes (se bajan solo al consultarlas)
Estos archivos NO van al repositorio: el robot los sube al almacenamiento privado de Supabase.
Se ejecuta desde la raíz del repositorio. Requisitos: pip install pandas
"""
import json, os, glob
import numpy as np
import pandas as pd

def num(x, d=6):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)

o = pd.read_csv("data/operaciones.csv")
e = pd.read_csv("data/emisiones.csv")
o["vencimiento"] = pd.to_datetime(o.vencimiento, errors="coerce").dt.date.astype(str)
o = o.sort_values(["fecha", "id"])
fechas = sorted(o.fecha.unique()); FI = {d: i for i, d in enumerate(fechas)}
nombres = dict(zip(e["Código ISIN"], e["Emisor"].fillna(e["Administradora"])))

# Tasa DOP/USD implícita por sesión (monto en DOP / monto en USD); si no hubo operaciones en USD, se arrastra la anterior
u = o[o.moneda == "USD"].groupby("fecha").agg(dop=("monto_dop", "sum"), usd=("monto", "sum"))
fx_dia = (u.dop / u.usd).reindex(fechas).ffill().bfill()
fx = [round(float(x), 4) for x in fx_dia]

# Filtro de precios fuera de mercado: una operación no cuenta para el PRECIO del día si su rendimiento se aleja
# más de 50 pb de la mediana de las 8 operaciones más cercanas en el tiempo del mismo título
# (o su precio más de 1.5% si vence en menos de 1 año, o más de 10% si el título no reporta rendimiento). Sigue contando para el VOLUMEN transado.
o["si"] = o.fecha.map(FI)
o["fuera"] = False
VEC = 8
for isin, g in o.groupby("isin"):
    if len(g) < 4: continue
    si, y, p = g.si.values, g.rendimiento.values.astype(float), g.precio.values.astype(float)
    dv = g["dias_venc"].values.astype(float) if "dias_venc" in g else np.full(len(g), np.nan)
    usa_y = np.isfinite(y).mean() > 0.8
    for k, idx in enumerate(g.index):
        dist = np.abs(si - si[k]).astype(float); dist[k] = np.inf
        cerca = np.argsort(dist, kind="stable")[:VEC]
        if usa_y and np.isfinite(y[k]) and np.isfinite(dv[k]) and dv[k] < 365:
            # bonos con menos de 1 año: el rendimiento es muy sensible, se compara el precio (umbral 1.5%)
            o.at[idx, "fuera"] = abs(p[k] / np.nanmedian(p[cerca]) - 1) > 0.015
        elif usa_y and np.isfinite(y[k]):
            o.at[idx, "fuera"] = abs(y[k] - np.nanmedian(y[cerca])) > 0.5
        else:
            o.at[idx, "fuera"] = abs(p[k] / np.nanmedian(p[cerca]) - 1) > 0.10
print(f"Operaciones excluidas del precio por estar fuera de mercado: {int(o.fuera.sum())} de {len(o)}")

# Catálogo de títulos negociados + historial diario (precio y rendimiento ponderados por monto)
ins, IX = [], {}
for isin, g in o.groupby("isin", sort=False):
    g = g.sort_values("fecha"); last = g.iloc[-1]
    hist = []
    if (~g.fuera).sum() == 0: g = g.assign(fuera=False)
    for d, x in g.groupby("fecha"):
        x = x[~x.fuera]
        if x.empty: continue
        w = x.monto
        hist.append([FI[d], num((x.precio * w).sum() / w.sum()),
                     num((x.rendimiento * w).sum() / w.sum(), 4) if x.rendimiento.notna().any() else None,
                     num(x.monto_dop.sum() / 1e6, 3), int(len(x))])
    tipo = g["tipo"].dropna().iloc[-1] if "tipo" in g and g["tipo"].notna().any() else ""
    IX[isin] = len(ins)
    ins.append({"isin": isin, "titulo": str(last.titulo).strip(), "emisor": str(last.emisor).strip(), "nombre": nombres.get(isin, ""),
                "mercado": last.mercado, "moneda": last.moneda, "tipo": tipo,
                "cupon": num(last.cupon, 4), "venc": last.vencimiento, "frec": None if pd.isna(last.frec_pago) else int(last.frec_pago),
                "h": hist})

# Resumen compacto para gráficas: una fila por sesión, título y rueda -> [sesión, título, rueda, monto RD$ MM, n.º operaciones]
ruedas = sorted(o.rueda.dropna().unique()); RI = {r: i for i, r in enumerate(ruedas)}
s = o.groupby(["fecha", "isin", "rueda"]).agg(m=("monto_dop", "sum"), n=("id", "size")).reset_index()
S = [[FI[r.fecha], IX[r.isin], RI[r.rueda], round(r.m / 1e6, 3), int(r.n)] for r in s.itertuples()]

cat = e.rename(columns={"Código ISIN": "isin", "Nemotécnico Local": "titulo", "Emisor": "emisor", "Administradora": "adm",
                        "Moneda": "moneda", "Tasa Vigente (%)": "tasa", "Tasa Fija (F) o Var. (V)": "tipo_tasa",
                        "Fecha de Vencimiento": "venc", "Monto de Emisión": "monto", "Periodic. Pagos": "pago"})
cat["venc"] = pd.to_datetime(cat.venc, errors="coerce").dt.date.astype(str)
cols = [c for c in ["mercado", "isin", "titulo", "emisor", "adm", "moneda", "tasa", "tipo_tasa", "venc", "pago", "monto"] if c in cat]

# Operaciones por mes (archivos aparte)
OPS_COLS = ["fecha", "id", "rueda", "titulo", "emisor", "precio", "rendimiento", "monto", "moneda", "monto_dop", "fuera"]
os.makedirs("data/out/ops", exist_ok=True)
for f in glob.glob("data/out/ops/*.json"): os.remove(f)
meses = sorted(o.fecha.str[:7].unique())
for m in meses:
    x = o[o.fecha.str[:7] == m][OPS_COLS].copy()
    x["id"] = x["id"].astype(str); x["titulo"] = x.titulo.astype(str).str.strip()
    rows = x.replace({np.nan: None}).values.tolist()
    with open(f"data/out/ops/{m}.json", "w", encoding="utf-8") as fh:
        json.dump({"cols": OPS_COLS, "rows": rows}, fh, ensure_ascii=False, default=float, separators=(",", ":"))

try:
    reg = json.load(open("data/descargas.json", encoding="utf-8"))
except FileNotFoundError:
    reg = {}
try:
    pub = json.load(open("data/publicacion.json", encoding="utf-8"))
except FileNotFoundError:
    pub = {}
# Preliminar = se bajó del servidor pero aún no aparece en la página de la BVRD ni pasó la descarga de las 9 pm
prelim = {d: v.get("primera_vez") for d, v in reg.items()
          if d in FI and not v.get("final", True) and not pub.get(d, {}).get("en_pagina")}

# Mercado primario (colocaciones): una fila por fecha, título, modo, precio y rendimiento
PRI_COLS = ["fecha", "isin", "titulo", "emisor", "mercado", "moneda", "venc", "cupon", "modo", "rueda", "precio", "rend", "monto", "monto_dop", "n"]
PRI = []
if os.path.exists("data/primario.csv") and os.path.getsize("data/primario.csv") > 10:
    pr = pd.read_csv("data/primario.csv")
    if len(pr):
        for c in ["precio", "rendimiento", "monto", "monto_dop", "cupon"]:
            if c not in pr: pr[c] = np.nan
            pr[c] = pd.to_numeric(pr[c], errors="coerce")
        pr["venc"] = pd.to_datetime(pr.get("vencimiento"), errors="coerce").dt.date.astype(str).replace("NaT", None)
        pr["precio_r"] = pr.precio.round(6); pr["rend_r"] = pr.rendimiento.round(6)
        k = ["fecha", "isin", "titulo", "emisor", "mercado", "moneda", "venc", "cupon", "modo", "rueda", "precio_r", "rend_r"]
        g = pr.groupby(k, dropna=False).agg(monto=("monto", "sum"), monto_dop=("monto_dop", "sum"), n=("id", "size")).reset_index()
        g = g.sort_values(["fecha", "monto_dop"], ascending=[False, False])
        PRI = [[r.fecha, r.isin, str(r.titulo).strip(), str(r.emisor).strip(), r.mercado, r.moneda, r.venc if isinstance(r.venc, str) else None,
                num(r.cupon, 4), r.modo, r.rueda, num(r.precio_r), num(r.rend_r, 4), num(r.monto, 2), num(r.monto_dop, 2), int(r.n)] for r in g.itertuples()]
print(f"Mercado primario: {len(PRI)} filas")

# Volumen por puesto de bolsa: se guarda el último corte de cada mes (acumulado del mes y del año)
PUE_COLS = ["m", "fecha", "seg", "part", "mes", "anio", "anio_usd"]
PUE = []
if os.path.exists("data/puestos.csv") and os.path.getsize("data/puestos.csv") > 10:
    pu = pd.read_csv("data/puestos.csv")
    if len(pu):
        pu["m"] = pu.fecha.str[:7]
        full = pu.copy()
        ult = pu.groupby(["m", "seg"]).fecha.max().reset_index()
        pu = pu.merge(ult, on=["m", "seg", "fecha"])
        PUE = [[r.m, r.fecha, r.seg, str(r.part).strip(), num(r.mes, 2), num(r.anio, 2), num(r.anio_usd, 2)] for r in pu.itertuples()]
        # corte anterior al último (para calcular el volumen del día = diferencia de acumulados del año)
        for seg, g in full.groupby("seg"):
            fs = sorted(g.fecha.unique())
            if len(fs) >= 2:
                PUE += [["_prev", r.fecha, r.seg, str(r.part).strip(), num(r.mes, 2), num(r.anio, 2), num(r.anio_usd, 2)] for r in g[g.fecha == fs[-2]].itertuples()]
print(f"Puestos de bolsa: {len(PUE)} filas")

D = {"prelim": prelim, "fecha": fechas[-1], "fechas": fechas, "fx": fx, "ruedas": ruedas, "meses": meses, "ins": ins, "s": S,
     "cat": cat[cols].replace({np.nan: None}).to_dict("records"), "pri": {"cols": PRI_COLS, "rows": PRI}, "pue": {"cols": PUE_COLS, "rows": PUE}}
try:
    noticias = json.load(open("data/noticias.json", encoding="utf-8"))
except FileNotFoundError:
    noticias = []
# Archivo completo de noticias aparte (se baja solo al abrir NEWS); en data.json van las 25 más recientes de cada fuente
with open("data/out/noticias.json", "w", encoding="utf-8") as fh:
    json.dump(noticias, fh, ensure_ascii=False, separators=(",", ":"))
_c, recientes = {}, []
for n in sorted(noticias, key=lambda n: (n.get("d") or "", n.get("h") or "", n.get("v") or ""), reverse=True):
    _c[n["s"]] = _c.get(n["s"], 0) + 1
    if _c[n["s"]] <= 25: recientes.append(n)
with open("data/out/data.json", "w", encoding="utf-8") as fh:
    json.dump({"D": D, "NEWS": recientes}, fh, ensure_ascii=False, separators=(",", ":"), default=float)
kb = os.path.getsize("data/out/data.json") / 1024
print(f"data.json: {kb:,.0f} KB · {len(fechas)} sesiones ({fechas[0]} a {fechas[-1]}) · {len(ins)} títulos · {len(S)} filas de resumen · {len(meses)} archivos mensuales · {len(noticias)} noticias · preliminares: {list(prelim) or 'ninguno'}")
