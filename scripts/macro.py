"""
Robot MACRO de Ámbar: descarga los archivos públicos de precios del Banco Central
(https://www.bancentral.gov.do/a/d/2534-precios) y arma data/out/macro.json para la pestaña MACRO.
Guarda solo los índices mensuales; las variaciones (mensual, acumulada, interanual) se calculan en la terminal.
Uso: python scripts/macro.py [--no-subir] [--local DIR]
"""
import gzip, hashlib, io, json, os, sys, unicodedata, time
import pandas as pd, requests

B = "https://cdn.bancentral.gov.do/documents/estadisticas/precios/documents/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Ambar/1.0"}
MES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}
OUT = "data/out/macro.json"
LOCAL = sys.argv[sys.argv.index("--local") + 1] if "--local" in sys.argv else None


def sin(s):
    return unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def bajar(f):
    if LOCAL:
        return pd.read_excel(os.path.join(LOCAL, f), sheet_name=None, header=None)
    r = requests.get(B + f, params={"v": time.time_ns()}, headers={**UA, "Cache-Control": "no-cache", "Pragma": "no-cache"}, timeout=120)  # evita la copia vieja del caché del CDN del BCRD
    r.raise_for_status()
    return pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)


def hoja(f):
    return next(iter(bajar(f).values()))


def num(v, d=6):
    try:
        x = float(v)
        return None if x != x else round(x, d)
    except (TypeError, ValueError):
        return None


def mensual(df, cols, c_ano=(0, 1), c_mes=(0, 1)):
    """Recorre las filas: el año puede venir en una fila propia o junto al mes; también filas 'Dic. AAAA'.
    Devuelve {AAAA-MM: [valores de cols]}."""
    out, ano = {}, None
    for r in df.itertuples(index=False):
        r = list(r)
        mm = None
        for c in set(c_ano) | set(c_mes):
            v = r[c]
            if pd.isna(v): continue
            t = str(v).strip()
            if t.replace(".0", "").isdigit() and 1900 < int(float(t)) < 2100: ano = int(float(t)); continue
            s = sin(t)
            if s[:3] in MES and len(s) >= 3:
                partes = s.replace(".", " ").split()
                if len(partes) >= 2 and partes[-1].isdigit(): ano = int(partes[-1])
                mm = MES[s[:3]]
        if ano and mm:
            v = [num(r[c]) for c in cols]
            if any(x is not None for x in v): out[f"{ano:04d}-{mm:02d}"] = v
    return out


def cabecera(df, cols, filas=range(2, 8)):
    nombres = []
    for c in cols:
        t = " ".join(str(df.iat[i, c]).strip() for i in filas if pd.notna(df.iat[i, c]) and not sin(df.iat[i, c]).startswith(("indice", "var", "tasa", "inflacion")))
        nombres.append(" ".join(t.replace("*", "").split()))
    return nombres


def main():
    M = {"fuente": "Banco Central de la República Dominicana · Precios", "meta": {"centro": 4.0, "rango": 1.0}}
    S, nombres = {}, {}

    def poner(clave, datos, i, nombre):
        S[clave] = {k: v[i] for k, v in datos.items() if v[i] is not None}
        nombres[clave] = nombre

    gen = mensual(hoja("ipc_base_2019-2020.xls"), [2])
    poner("gen", gen, 0, "IPC general")
    sub = mensual(hoja("ipc_subyacente_base_2019-2020.xlsx"), [2], (0, 1), (0, 1))
    poner("sub", sub, 0, "IPC subyacente")
    tnt = mensual(hoja("ipc_tnt_base_2019-2020.xls"), [5, 8])
    poner("tra", tnt, 0, "Bienes transables")
    poner("ntra", tnt, 1, "Bienes no transables")
    df = hoja("ipc_grupos_base_2019-2020.xls")
    gc = [c for c in range(1, df.shape[1]) if sin(df.iat[5, c]).startswith("indice")]
    gn = cabecera(df, gc, range(3, 4))
    g = mensual(df, gc)
    for i, n in enumerate(gn): poner(f"g{i + 1:02d}", g, i, n)
    df = hoja("ipc_regiones_base_2019-2020.xls")
    rc = [2, 4, 6, 8]
    rn = [" ".join(str(df.iat[5, c]).replace("*", "").split()) for c in rc]
    r = mensual(df, rc)
    for i, n in enumerate(rn): poner(f"r{i + 1}", r, i, n)
    df = hoja("ipc_quintiles_base_2019-2020.xls")
    qc = [2, 4, 6, 8, 10]
    q = mensual(df, qc)
    for i in range(5): poner(f"q{i + 1}", q, i, f"Quintil {i + 1}")

    fechas = sorted(set(k for s in S.values() for k in s))
    M["fechas"] = fechas
    M["series"] = {k: [s.get(f) for f in fechas] for k, s in S.items()}
    M["nombres"] = nombres
    M["grupos"] = [f"g{i + 1:02d}" for i in range(len(gn))]

    # artículos: jerarquía (grupo > subgrupo > clase > subclase > artículo), ponderación e índice mensual desde oct-2020
    df = hoja("ipc_articulos_base_2019-2020.xlsx")
    hdr = next(i for i in range(10) if sin(df.iat[i, 0]) == "grupo")
    anos, ano = [], None
    for c in range(6, df.shape[1]):
        for i in range(hdr):
            v = df.iat[i, c]
            if pd.notna(v) and str(v).strip().replace(".0", "").isdigit(): ano = int(float(v))
        mm = MES.get(sin(df.iat[hdr, c])[:3]) if pd.notna(df.iat[hdr, c]) else None
        anos.append(f"{ano:04d}-{mm:02d}" if ano and mm else None)
    arts = []
    for i in range(hdr + 1, len(df)):
        nivel = next((c for c in range(5) if pd.notna(df.iat[i, c]) and str(df.iat[i, c]).strip()), None)
        if nivel is None: continue
        t = " ".join(str(df.iat[i, nivel]).split())
        cod, _, nom = t.partition(" ")
        if not cod.isdigit(): continue
        w = num(df.iat[i, 5])
        v = [num(df.iat[i, c], 4) for c in range(6, df.shape[1])]
        arts.append([cod, nom, nivel, w, v])
    M["art"] = {"fechas": [a for a in anos if a], "filas": [[a[0], a[1], a[2], a[3], [x for x, f in zip(a[4], anos) if f]] for a in arts]}
    g0 = [a for a in arts if a[2] == 0]
    M["pond_grupos"] = {k: (g0[i][3] if i < len(g0) else None) for i, k in enumerate(M["grupos"])}
    for i, k in enumerate(M["grupos"]):
        if i < len(g0): nombres[k] = g0[i][1].strip()

    print("fechas", fechas[0], "→", fechas[-1], "·", len(fechas))
    for k in S: print(k, nombres[k], len(S[k]), max(S[k]) if S[k] else None)
    print("artículos", len(arts), M["art"]["fechas"][0], "→", M["art"]["fechas"][-1])
    print("ponderaciones grupos", M["pond_grupos"])

    cuerpo = json.dumps(M, sort_keys=True).encode()
    M["hash"] = hashlib.sha1(cuerpo).hexdigest()
    M["actualizado"] = pd.Timestamp.now(tz="America/Santo_Domingo").strftime("%Y-%m-%d %H:%M")
    os.makedirs("data/out", exist_ok=True)
    crudo = json.dumps(M, ensure_ascii=False, separators=(",", ":")).encode()
    open(OUT, "wb").write(crudo)
    open(OUT + ".gz", "wb").write(gzip.compress(crudo, 9))
    print("macro.json", len(crudo) // 1024, "KB · comprimido", os.path.getsize(OUT + ".gz") // 1024, "KB")
    if "--no-subir" in sys.argv: return
    sys.path.insert(0, os.path.dirname(__file__))
    import supa
    anterior = None
    if supa.bajar_archivo("estado/macro_hash.txt", "data/macro_hash.txt"): anterior = open("data/macro_hash.txt").read().strip()
    if anterior == M["hash"]:
        print("Sin cambios en los datos del Banco Central."); return
    supa.subir_archivo(OUT + ".gz", "macro.json.gz")
    open("data/macro_hash.txt", "w").write(M["hash"])
    supa.subir_archivo("data/macro_hash.txt", "estado/macro_hash.txt")
    print("Subido macro.json (datos nuevos).")


if __name__ == "__main__":
    main()
