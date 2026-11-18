"""
Descarga y procesa el Boletín Consolidado diario de la BVRD.
Se ejecuta desde la raíz del repositorio. Uso:
  python boletin.py                 -> procesa el día de hoy
  python boletin.py 2026-11-17      -> un día específico
  python boletin.py 2026-01-01 2026-11-17   -> rango (reconstruir historia)
  python boletin.py --archivo X.xlsx        -> procesa un Excel ya descargado
Salida (carpeta data/):
  operaciones.csv  -> cada operación del mercado secundario (renta fija y variable)
  precios.csv      -> un precio por título y día (promedio ponderado por monto)
  emisiones.csv    -> catálogo de emisiones vigentes (última foto)
Requisitos: pip install requests pandas openpyxl
"""
import datetime as dt, io, os, sys, time
import pandas as pd, requests

MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto",
         "Septiembre","Octubre","Noviembre","Diciembre"]
BASE = "https://prod-data.bvrd.com.do/documentos/boletines/"

def urls(d):
    meses = [MESES[d.month-1]] + (["Setiembre"] if d.month == 9 else [])
    return [f"{BASE}BOLETINES+Y+PRECIOS+{d.year}/Boletin+Consolidado/"
            f"{d.month}.+{m}/{d:%d-%m-%Y}-Boletin+BVRD+Consolidado+excel.xlsx" for m in meses]

def tablas(xls, hoja, clave):
    """Encuentra cada fila de encabezado que contiene `clave` y lee las filas debajo."""
    raw = pd.read_excel(xls, sheet_name=hoja, header=None)
    out, i = [], 0
    while i < len(raw):
        fila = raw.iloc[i]
        if any(str(c).strip() == clave for c in fila):
            cols = {j: str(c).strip() for j, c in fila.items() if pd.notna(c)}
            seccion = next((str(c).strip() for c in raw.iloc[i-1] if pd.notna(c)), "") if i else ""
            j = i + 1
            while j < len(raw):
                r = raw.iloc[j]
                vals = {cols[k]: (r[k].strip() if isinstance(r[k], str) else r[k]) for k in cols if pd.notna(r[k])}
                if any(str(c).strip() == clave for c in r): break
                if str(r.dropna().iloc[0] if r.notna().any() else "").startswith("Total"): j += 1; continue
                if len(vals) >= len(cols) // 2 and any(k in vals for k in ("Cód. ISIN", "Código ISIN")):
                    vals["seccion"] = seccion; out.append(vals)
                j += 1
            i = j
        else:
            i += 1
    return pd.DataFrame(out)

def procesar(xls, fecha):
    rf = tablas(xls, "BB_RFMSOperDia", "Número Operación")
    rf = rf.rename(columns={"Número Operación":"id","Rueda":"rueda","Cód. Local":"titulo","Cód. ISIN":"isin",
        "Cód. Emisor":"emisor","Fecha Venc.":"vencimiento","Frec. Pago":"frec_pago","Tasa Cupón":"cupon",
        "Valor Negociado":"nominal","Precio":"precio","Valor Transado":"monto","Rend/ Equiv":"rendimiento",
        "Mon":"moneda","Equiv en DOP":"monto_dop","Días Venc.":"dias_venc"})
    rf["mercado"] = "renta_fija"
    rv = tablas(xls, "BB_RVMSOperDia", "Número Operación")
    rv = rv.rename(columns={"Número Operación":"id","Rueda":"rueda","Cód. Local":"titulo","Cód. ISIN":"isin",
        "Cód. Emisor":"emisor","Fecha Venc.":"vencimiento","Cant. de Cuotas":"cantidad","Precio":"precio",
        "Valor Transado":"monto","Mon":"moneda","Equivalente en DOP":"monto_dop","seccion":"tipo"})
    rv["mercado"] = "renta_variable"
    ops = pd.concat([rf, rv], ignore_index=True)
    if ops.empty: return ops, ops
    ops["fecha"] = fecha.isoformat()
    for c in ["titulo","isin","emisor","moneda"]:
        if c in ops: ops[c] = ops[c].astype(str).str.strip()
    for c in ["precio","monto","monto_dop","rendimiento","cupon","nominal","cantidad"]:
        if c in ops: ops[c] = pd.to_numeric(ops[c], errors="coerce")
    # Precio del día por título: promedio ponderado por monto
    g = ops.groupby(["fecha","mercado","isin","titulo","emisor","moneda"], dropna=False)
    precios = g.apply(lambda x: pd.Series({
        "precio": (x.precio*x.monto).sum()/x.monto.sum(),
        "rendimiento": (x.rendimiento*x.monto).sum()/x.monto.sum() if "rendimiento" in x and x.rendimiento.notna().any() else None,
        "precio_min": x.precio.min(), "precio_max": x.precio.max(),
        "operaciones": len(x), "monto_dop": x.monto_dop.sum()}), include_groups=False).reset_index()
    return ops, precios

def emisiones(xls):
    rf = tablas(xls, "BB_RFEmisionesCorpV", "Código ISIN"); rf["mercado"] = "renta_fija"
    rv = tablas(xls, "BB_RVEmisionesCorpV", "Código ISIN"); rv["mercado"] = "renta_variable"
    e = pd.concat([rf, rv], ignore_index=True)
    return e.apply(lambda c: c.str.strip() if c.dtype == object else c)

def agregar(df, ruta, claves):
    if os.path.exists(ruta):
        viejo = pd.read_csv(ruta, dtype=str)
        df = pd.concat([viejo, df.astype(str)]).drop_duplicates(subset=claves, keep="last")
    df.to_csv(ruta, index=False)

def un_dia(fecha, archivo=None):
    if archivo:
        xls = archivo
    else:
        r = None
        for u in urls(fecha):
            r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0 (Ambar)"})
            if r.status_code == 200 and r.content[:2] == b"PK":
                break
        else:
            print(f"{fecha}: sin boletín ({r.status_code if r is not None else '-'}) {urls(fecha)[0]}"); return False
        xls = io.BytesIO(r.content)
    ops, precios = procesar(xls, fecha)
    os.makedirs("data", exist_ok=True)
    if len(ops):
        agregar(ops, "data/operaciones.csv", ["id"])
        agregar(precios, "data/precios.csv", ["fecha","isin"])
    try:
        ultima = open("data/emisiones_fecha.txt").read().strip()
    except FileNotFoundError:
        ultima = ""
    if fecha.isoformat() >= ultima:  # el catálogo solo se reemplaza con un boletín más nuevo
        emisiones(xls).to_csv("data/emisiones.csv", index=False)
        open("data/emisiones_fecha.txt", "w").write(fecha.isoformat())
    print(f"{fecha}: {len(ops)} operaciones, {len(precios)} títulos con precio")
    return True

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--archivo":
        f = dt.date.today() if len(a) < 3 else dt.date.fromisoformat(a[2]); un_dia(f, a[1])
    elif len(a) == 2:
        d, fin = dt.date.fromisoformat(a[0]), dt.date.fromisoformat(a[1])
        ok = 0
        while d <= fin:
            if d.weekday() < 5:
                try:
                    ok += bool(un_dia(d))
                except Exception as e:
                    print(f"{d}: error procesando ({e})")
                time.sleep(2)  # pausa para no sobrecargar el servidor de la BVRD
            d += dt.timedelta(days=1)
        print(f"Resumen: {ok} boletines procesados entre {a[0]} y {a[1]}")
    else:
        un_dia(dt.date.fromisoformat(a[0]) if a else dt.date.today())
