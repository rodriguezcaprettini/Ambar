"""
Convierte los CSV de data/ en los archivos que lee la terminal (index.html):
  data/data.js          -> archivo principal liviano (se carga al abrir)
  data/ops/AAAA-MM.js   -> operaciones de cada mes (se cargan solo al consultarlas)
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
os.makedirs("data/ops", exist_ok=True)
for f in glob.glob("data/ops/*.js"): os.remove(f)
meses = sorted(o.fecha.str[:7].unique())
for m in meses:
    x = o[o.fecha.str[:7] == m][OPS_COLS].copy()
    x["id"] = x["id"].astype(str); x["titulo"] = x.titulo.astype(str).str.strip()
    rows = x.replace({np.nan: None}).values.tolist()
    with open(f"data/ops/{m}.js", "w", encoding="utf-8") as fh:
        fh.write(f"(window.OPS=window.OPS||{{}})[{json.dumps(m)}]=" + json.dumps({"cols": OPS_COLS, "rows": rows}, ensure_ascii=False, default=float) + ";\n")

D = {"fecha": fechas[-1], "fechas": fechas, "fx": fx, "ruedas": ruedas, "meses": meses, "ins": ins, "s": S,
     "cat": cat[cols].replace({np.nan: None}).to_dict("records")}
try:
    noticias = json.load(open("data/noticias.json", encoding="utf-8"))
except FileNotFoundError:
    noticias = []
with open("data/data.js", "w", encoding="utf-8") as fh:
    fh.write("window.D=" + json.dumps(D, ensure_ascii=False, separators=(",", ":"), default=float) + ";\n")
    fh.write("window.NEWS=" + json.dumps(noticias, ensure_ascii=False, separators=(",", ":")) + ";\n")
kb = os.path.getsize("data/data.js") / 1024
print(f"data.js: {kb:,.0f} KB · {len(fechas)} sesiones ({fechas[0]} a {fechas[-1]}) · {len(ins)} títulos · {len(S)} filas de resumen · {len(meses)} archivos mensuales · {len(noticias)} noticias")
