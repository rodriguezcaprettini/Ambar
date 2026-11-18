"""
Convierte los CSV de data/ en data/data.js, que es lo que lee la terminal (index.html).
Se ejecuta desde la raíz del repositorio. Requisitos: pip install pandas
"""
import json
import numpy as np
import pandas as pd

o = pd.read_csv("data/operaciones.csv")
e = pd.read_csv("data/emisiones.csv")
o["vencimiento"] = pd.to_datetime(o.vencimiento, errors="coerce").dt.date.astype(str)
nombres = dict(zip(e["Código ISIN"], e["Emisor"].fillna(e["Administradora"])))
usd = o[o.moneda == "USD"].sort_values("fecha").tail(60)  # tasa implícita: últimas operaciones en USD
fx = float(usd.monto_dop.sum() / usd.monto.sum()) if len(usd) else None
fechas = sorted(o.fecha.unique())

def universo(mercado):
    out = []
    for isin, g in o[o.mercado == mercado].groupby("isin"):
        g = g.sort_values("fecha"); hist = []
        for d, x in g.groupby("fecha"):
            w = x.monto
            hist.append({"f": d, "p": round(float((x.precio * w).sum() / w.sum()), 6),
                         "y": round(float((x.rendimiento * w).sum() / w.sum()), 4) if x.rendimiento.notna().any() else None,
                         "m": float(x.monto_dop.sum()), "n": int(len(x))})
        tipo = g["tipo"].dropna().iloc[0] if "tipo" in g and g["tipo"].notna().any() else ""
        out.append({"isin": isin, "titulo": g.titulo.iloc[0], "emisor": g.emisor.iloc[0], "nombre": nombres.get(isin, ""),
                    "moneda": g.moneda.iloc[0], "tipo": tipo,
                    "cupon": None if pd.isna(g.cupon.iloc[-1]) else float(g.cupon.iloc[-1]),
                    "venc": g.vencimiento.iloc[-1], "frec": None if pd.isna(g.frec_pago.iloc[-1]) else int(g.frec_pago.iloc[-1]),
                    "ult": g.fecha.max(), "precio": hist[-1]["p"], "rend": hist[-1]["y"], "dias": len(hist),
                    "monto_tot": float(g.monto_dop.sum()), "hist": hist})
    return out

cat = e.rename(columns={"Código ISIN": "isin", "Nemotécnico Local": "titulo", "Emisor": "emisor", "Administradora": "adm",
                        "Moneda": "moneda", "Tasa Vigente (%)": "tasa", "Tasa Fija (F) o Var. (V)": "tipo_tasa",
                        "Fecha de Vencimiento": "venc", "Monto de Emisión": "monto", "Periodic. Pagos": "pago"})
cat["venc"] = pd.to_datetime(cat.venc, errors="coerce").dt.date.astype(str)
cols = [c for c in ["mercado", "isin", "titulo", "emisor", "adm", "moneda", "tasa", "tipo_tasa", "venc", "pago", "monto"] if c in cat]
ops_cols = ["fecha", "id", "rueda", "mercado", "tipo", "isin", "titulo", "emisor", "moneda", "cupon", "vencimiento",
            "frec_pago", "precio", "rendimiento", "monto", "monto_dop", "dias_venc", "cantidad"]
D = {"fecha": fechas[-1], "fechas": fechas, "fx": round(fx, 4) if fx else None,
     "ops": o[[c for c in ops_cols if c in o]].replace({np.nan: None}).to_dict("records"),
     "rf": universo("renta_fija"), "rv": universo("renta_variable"),
     "cat": cat[cols].replace({np.nan: None}).to_dict("records")}
try:
    noticias = json.load(open("data/noticias.json", encoding="utf-8"))
except FileNotFoundError:
    noticias = []
with open("data/data.js", "w", encoding="utf-8") as fh:
    fh.write("window.D=" + json.dumps(D, ensure_ascii=False, default=float) + ";\n")
    fh.write("window.NEWS=" + json.dumps(noticias, ensure_ascii=False) + ";\n")
print(f"data.js: {len(fechas)} sesiones ({fechas[0]} a {fechas[-1]}), {len(D['ops'])} operaciones, {len(noticias)} noticias")
