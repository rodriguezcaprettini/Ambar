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
import datetime as dt, hashlib, io, json, os, sys, time
from zoneinfo import ZoneInfo

def hoy_rd():
    """Fecha de hoy en República Dominicana (los servidores de GitHub usan UTC)."""
    return dt.datetime.now(ZoneInfo("America/Santo_Domingo")).date()
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

PRIM = [("BB_RFMPOperDia", "renta_fija", "subasta"), ("BB_RFMPOperDiaFirme", "renta_fija", "firme"),
        ("BB_RVMPOperDia", "renta_variable", "subasta"), ("BB_RVMPOperDiaFirme", "renta_variable", "firme")]

def primario(xls, fecha):
    """Colocaciones del MERCADO PRIMARIO (nuevas emisiones vendidas por el emisor).
    'subasta' = operaciones del día en la BVRD; 'firme' = registro de colocaciones en firme."""
    partes = []
    for hoja, mercado, modo in PRIM:
        try:
            t = tablas(xls, hoja, "Número Operación")
        except ValueError:  # boletines viejos sin esa hoja
            continue
        if t.empty: continue
        t = t.rename(columns={"Número Operación":"id","Rueda":"rueda","Cód. Local":"titulo","Cód. ISIN":"isin",
            "Cód. Emisor":"emisor","Fecha Venc.":"vencimiento","Tasa Cupón":"cupon","Valor Negociado":"nominal",
            "Precio":"precio","Valor Transado":"monto","Rend/ Equiv":"rendimiento","Mon":"moneda",
            "Equiv en DOP":"monto_dop","Equivalente en DOP":"monto_dop","Cant. de Cuotas":"cantidad"})
        t["mercado"] = mercado; t["modo"] = modo
        partes.append(t)
    if not partes: return pd.DataFrame()
    p = pd.concat(partes, ignore_index=True)
    keep = [c for c in ["id","rueda","titulo","isin","emisor","vencimiento","cupon","nominal","precio","monto",
                        "rendimiento","moneda","monto_dop","cantidad","mercado","modo"] if c in p]
    p = p[keep].copy(); p["fecha"] = fecha.isoformat()
    for c in ["titulo","isin","emisor","moneda","rueda"]:
        if c in p: p[c] = p[c].astype(str).str.strip()
    return p

def guardar_primario(p, fecha, ruta="data/primario.csv"):
    """Reemplaza las colocaciones de esa fecha (aunque hoy no haya ninguna)."""
    viejo = pd.read_csv(ruta, dtype=str) if os.path.exists(ruta) else pd.DataFrame(columns=["fecha"])
    viejo = viejo[viejo["fecha"] != fecha.isoformat()]
    df = pd.concat([viejo, p.astype(str)]) if len(p) else viejo
    os.makedirs("data", exist_ok=True)
    df.sort_values("fecha", kind="stable").to_csv(ruta, index=False)

def solo_primario(desde, hasta):
    """Recarga histórica SOLO del mercado primario (no toca el registro ni el mercado secundario)."""
    d, n = desde, 0
    while d <= hasta:
        if d.weekday() < 5:
            for u in urls(d):
                r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0 (Ambar)"})
                if r.status_code == 200 and r.content[:2] == b"PK":
                    try:
                        b = io.BytesIO(r.content)
                        p = primario(b, d); guardar_primario(p, d)
                        q = puestos(b, d); guardar_primario(q, d, "data/puestos.csv"); n += 1
                        print(f"{d}: {len(p)} operaciones de mercado primario, {len(q)} filas por puesto")
                    except Exception as e:
                        print(f"{d}: error ({e})")
                    break
            time.sleep(1.5)
        d += dt.timedelta(days=1)
    print(f"Resumen: {n} boletines leídos para mercado primario")

# Volumen por puesto de bolsa / participante (agregado, NO por título: el boletín no dice quién transó cada bono)
PUESTOS = [("BB_RFMSVTPBolsa", "rf_sec"), ("BB_RFRegistro", "rf_reg"), ("BB_RFVTransPuestoBolsaMP", "rf_pri"),
           ("BB_RVVTransPBolsa", "rv_sec"), ("BB_RVVTransPuestoBolsa", "rv_pri")]

def _n(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0

def puestos(xls, fecha):
    """Una fila por hoja y participante: acumulado del mes y del año en RD$ equivalentes."""
    out = []
    for hoja, seg in PUESTOS:
        try:
            raw = pd.read_excel(xls, sheet_name=hoja, header=None)
        except ValueError:
            continue
        hi = next((i for i in range(len(raw)) if any(str(c).strip() in ("Participante", "Puesto de Bolsa") for c in raw.iloc[i])), None)
        if hi is None: continue
        H = {j: str(c).strip() for j, c in raw.iloc[hi].items() if pd.notna(c)}
        cp = next(j for j, c in H.items() if c in ("Participante", "Puesto de Bolsa"))
        cm = next((j for j, c in H.items() if "Mes" in c), None)
        ca = max((j for j, c in H.items() if "Año" in c or "Acumulado Al" in c), default=None)
        cu = [j for j, c in H.items() if c in ("Transado USD", "Total Transado USD")]
        for i in range(hi + 1, len(raw)):
            r = raw.iloc[i]; nom = r[cp]
            if pd.isna(nom): continue
            nom = str(nom).strip()
            if not nom or nom.startswith("Total") or nom.startswith("Departamento") or nom.startswith("Nota"): break
            out.append({"fecha": fecha.isoformat(), "seg": seg, "part": nom,
                        "mes": _n(r[cm]) if cm is not None else 0.0, "anio": _n(r[ca]) if ca is not None else 0.0,
                        "anio_usd": _n(r[cu[-1]]) if len(cu) > 1 else None})
    try:
        rk = pd.read_excel(xls, sheet_name="BB_RentaFijaVolumenTransadoPues", header=None)
        hi = next(i for i in range(len(rk)) if "Ranking" in [str(c).strip() for c in rk.iloc[i]])
        for i in range(hi + 1, len(rk)):
            v = [c for c in rk.iloc[i] if pd.notna(c)]
            if len(v) < 3 or not str(v[0]).strip().isdigit(): continue
            out.append({"fecha": fecha.isoformat(), "seg": "ranking", "part": str(v[1]).strip(), "mes": _n(v[2]), "anio": 0.0, "anio_usd": None})
    except (ValueError, StopIteration):
        pass
    return pd.DataFrame(out)

def emisiones(xls):
    rf = tablas(xls, "BB_RFEmisionesCorpV", "Código ISIN"); rf["mercado"] = "renta_fija"
    rv = tablas(xls, "BB_RVEmisionesCorpV", "Código ISIN"); rv["mercado"] = "renta_variable"
    e = pd.concat([rf, rv], ignore_index=True)
    return e.apply(lambda c: c.str.strip() if c.dtype == object else c)

def agregar(df, ruta, claves):
    """Guarda los datos del día REEMPLAZANDO todo lo que ya hubiera de esa misma fecha.
    Así, si la BVRD publica una versión corregida del boletín, se eliminan las operaciones anuladas."""
    if os.path.exists(ruta):
        viejo = pd.read_csv(ruta, dtype=str)
        fechas = set(df["fecha"].astype(str))
        viejo = viejo[~viejo["fecha"].isin(fechas)]
        df = pd.concat([viejo, df.astype(str)]).drop_duplicates(subset=claves, keep="last")
    df.sort_values("fecha", kind="stable").to_csv(ruta, index=False)

RD = ZoneInfo("America/Santo_Domingo")
HORA_FINAL = 21  # a partir de las 9:00 pm hora RD el boletín del día se considera definitivo

def leer_registro():
    try:
        return json.load(open("data/descargas.json", encoding="utf-8"))
    except FileNotFoundError:
        return {}

def guardar_registro(reg):
    json.dump(dict(sorted(reg.items())), open("data/descargas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def es_final(fecha):
    """Un boletín es definitivo si se descarga a partir de las 9 pm del mismo día o cualquier día posterior."""
    ahora = dt.datetime.now(RD)
    return fecha < ahora.date() or ahora.hour >= HORA_FINAL

def un_dia(fecha, archivo=None):
    reg = leer_registro(); k = fecha.isoformat(); ahora = dt.datetime.now(RD).strftime("%Y-%m-%d %H:%M")
    if archivo:
        xls = archivo
        contenido = open(archivo, "rb").read()
    else:
        r = None
        for u in urls(fecha):
            r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0 (Ambar)"})
            if r.status_code == 200 and r.content[:2] == b"PK":
                break
        else:
            print(f"{fecha}: sin boletín ({r.status_code if r is not None else '-'}) {urls(fecha)[0]}"); return False
        xls = io.BytesIO(r.content)
        contenido = r.content
    sha = hashlib.sha256(contenido).hexdigest()[:16]
    previo = reg.get(k, {})
    final = True if archivo else es_final(fecha)
    if previo.get("sha") == sha:  # mismo archivo que la última vez: no se reprocesa
        if final and not previo.get("final"):
            previo.update(final=True, confirmado=ahora); reg[k] = previo; guardar_registro(reg)
            print(f"{fecha}: sin cambios desde {previo['ultima']}; ahora se marca como definitivo")
        else:
            print(f"{fecha}: sin cambios desde {previo.get('ultima')}")
        return True
    reg[k] = {"primera_vez": previo.get("primera_vez", ahora), "ultima": ahora, "sha": sha, "final": final,
              "versiones": previo.get("versiones", 0) + 1}
    ops, precios = procesar(xls, fecha)
    os.makedirs("data", exist_ok=True)
    try:
        guardar_primario(puestos(xls, fecha), fecha, "data/puestos.csv")
    except Exception as e:
        print(f"{fecha}: no se pudo leer el volumen por puesto ({e})")
    try:
        guardar_primario(primario(xls, fecha), fecha)
    except Exception as e:
        print(f"{fecha}: no se pudo leer el mercado primario ({e})")
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
    guardar_registro(reg)
    estado = "definitivo" if final else "PRELIMINAR"
    print(f"{fecha}: {len(ops)} operaciones, {len(precios)} títulos con precio ({estado}, versión {reg[k]['versiones']})")
    return True

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--primario":
        solo_primario(dt.date.fromisoformat(a[1]), dt.date.fromisoformat(a[2]))
    elif a and a[0] == "--archivo":
        f = hoy_rd() if len(a) < 3 else dt.date.fromisoformat(a[2]); un_dia(f, a[1])
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
    elif a:
        un_dia(dt.date.fromisoformat(a[0]))
    else:
        # Días anteriores que quedaron preliminares (p. ej., si GitHub se saltó la corrida de las 9 pm)
        for k, v in leer_registro().items():
            if not v.get("final", True) and dt.date.fromisoformat(k) < hoy_rd():
                un_dia(dt.date.fromisoformat(k))
        if hoy_rd().weekday() < 5:
            un_dia(hoy_rd())
