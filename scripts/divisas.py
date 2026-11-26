"""
Robot de divisas de Ámbar: descarga los archivos públicos del Banco Central (Mercado cambiario,
https://www.bancentral.gov.do/a/d/2538-mercado-cambiario) y arma data/out/fx.json para la pestaña FX.
Se sube a Supabase solo si cambió algo. Uso: python scripts/divisas.py [--no-subir]
"""
import hashlib, io, json, math, os, sys, unicodedata, time
import pandas as pd, requests

B = "https://cdn.bancentral.gov.do/documents/estadisticas/mercado-cambiario/documents/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Ambar/1.0"}
MES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}
OUT = "data/out/fx.json"


def sin(s):
    return unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def bajar(f):
    r = requests.get(B + f, params={"v": time.time_ns()}, headers={**UA, "Cache-Control": "no-cache", "Pragma": "no-cache"}, timeout=90)  # evita la copia vieja del caché del CDN del BCRD
    r.raise_for_status()
    return pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)


def num(v, d=4):
    try:
        x = float(v)
        return None if math.isnan(x) else round(x, d)
    except (TypeError, ValueError):
        return None


def fecha(a, m, d):
    try:
        a, d = int(float(a)), int(float(d))
        mm = MES.get(sin(m)[:3])
        return f"{a:04d}-{mm:02d}-{d:02d}" if mm and 1990 < a < 2100 and 1 <= d <= 31 else None
    except (TypeError, ValueError):
        return None


def diaria(df, c0=3, n=2, d=4):
    """Filas Año | Mes | Día | valores… (el año a veces solo viene en la primera fila del año)."""
    out, ano, mes = [], None, None
    for r in df.itertuples(index=False):
        r = list(r)
        if pd.notna(r[0]) and str(r[0]).strip().isdigit(): ano = r[0]
        if pd.notna(r[1]) and sin(r[1])[:3] in MES: mes = r[1]
        f = fecha(ano, mes, r[2]) if ano and mes and pd.notna(r[2]) else None
        if not f: continue
        v = [num(x, d) for x in r[c0:c0 + n]]
        if any(x is not None for x in v): out.append([f] + v)
    out.sort(key=lambda x: x[0])
    return out


# ---------- PDF "Hoy": el dato del día, que llega antes que los Excel ----------
MESL = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def pdf_texto(f):
    import pdfplumber
    r = requests.get(B + f, params={"v": time.time_ns()}, headers={**UA, "Cache-Control": "no-cache", "Pragma": "no-cache"}, timeout=90)  # evita la copia vieja del caché del CDN del BCRD
    r.raise_for_status()
    return pdfplumber.open(io.BytesIO(r.content))


def poner(rows, fila):
    """Inserta o reemplaza la fila de esa fecha (los PDF del día mandan sobre el Excel si difieren)."""
    for i, r in enumerate(rows):
        if r[0] == fila[0]:
            rows[i] = fila; return "act"
    rows.append(fila); rows.sort(key=lambda x: x[0]); return "nuevo"


def hoy_referencia(fx):
    import re
    with pdf_texto("tasaus_mc.pdf") as p:
        t = " ".join((pg.extract_text() or "") for pg in p.pages)
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"cierre del (\d{1,2}) de ([a-záéíóú]+) de (\d{4}), son de RD\$\s*([\d.,]+)\s*/US\$ y RD\$\s*([\d.,]+)", t, re.I)
    if not m: print("referencia PDF: formato no reconocido"); return
    f = f"{int(m[3]):04d}-{MESL[sin(m[2])]:02d}-{int(m[1]):02d}"
    print("referencia PDF", f, poner(fx["ref"], [f, float(m[4].replace(",", "")), float(m[5].replace(",", ""))]))


def hoy_otras(fx):
    import re
    with pdf_texto("TMC4001.pdf") as p:
        t = "\n".join((pg.extract_text() or "") for pg in p.pages)
    m = re.search(r"CORRESPONDIENTES AL \w+ (\d{1,2}) DE ([A-ZÁÉÍÓÚ]+) DE (\d{4})", t, re.I)
    if not m: print("otras PDF: formato no reconocido"); return
    f = f"{int(m[3]):04d}-{MESL[sin(m[2])]:02d}-{int(m[1]):02d}"
    vals = {}
    for ln in t.splitlines():
        q = re.match(r"^[A-Z]{3}\s+(.+?)\*{0,3}\s+([\d.]+)$", ln.strip())
        if q: vals[sin(q[1]).replace("*", "").strip()] = float(q[2])
    fila = [f] + [vals.get(sin(n).replace("*", "").strip()) for n in fx["otras"]["monedas"]]
    if sum(v is not None for v in fila[1:]) >= len(fila[1:]) // 2:
        print("otras PDF", f, poner(fx["otras"]["rows"], fila))


def hoy_sondeo(fx):
    import re
    for mon, mf in (("USD", "DOLAR"), ("EUR", "EURO")):
        for ins, inf in (("ventanilla", "VENTANILLA"), ("transferencia", "TRANSFERENCIA"), ("cheque", "CHEQUE")):
            try:
                with pdf_texto(f"SONDEO_{inf}_{mf}.pdf") as p:
                    t = "\n".join((pg.extract_text() or "") for pg in p.pages)
                L = re.findall(r"^(\d{2})/(\d{2})/(\d{2}) ([\d.]+) - ([\d.]+) -$", t, re.M)
                if len(L) < 2: continue
                (d, mm, a, c1, v1), (_, _, _, c2, v2) = L[0], L[1]
                f = f"20{a}-{mm}-{d}"
                k = f"{mon}_{ins}"
                print("sondeo PDF", k, f, poner(fx["sondeo"].setdefault(k, []), [f, float(c1), float(v1), float(c2), float(v2)]))
            except Exception as e:
                print("sondeo PDF", mon, ins, "error:", e)


def hoy_promedio(fx):
    """TAC4009: tabla del año (días × meses, compra y venta). Se leen las palabras por su posición."""
    import re
    for clave, f in (("ef", "PRI"), ("ag", "AGE")):
        anio = pd.Timestamp.now(tz="America/Santo_Domingo").year
        try:
            with pdf_texto(f"TAC4009_{f}_{anio}.pdf") as p:
                pg = p.pages[0]
                W = pg.extract_words()
            hdr = [w for w in W if w["text"] in ("Compra", "Venta")]
            hdr.sort(key=lambda w: w["x0"])
            if not hdr: continue
            cent = [(w["x0"] + w["x1"]) / 2 for w in hdr]
            filas = {}
            for w in W:
                filas.setdefault(round(w["top"]), []).append(w)
            n = 0
            for top, ws in filas.items():
                ws.sort(key=lambda w: w["x0"])
                if not re.fullmatch(r"\d{2}", ws[0]["text"]) or ws[0]["x1"] > cent[0]: continue
                dia = int(ws[0]["text"])
                cel = {}
                for w in ws[1:]:
                    if not re.fullmatch(r"\d+\.\d+", w["text"]): continue
                    x = (w["x0"] + w["x1"]) / 2
                    k = min(range(len(cent)), key=lambda i: abs(cent[i] - x))
                    cel[k] = float(w["text"])
                for mes in range(len(cent) // 2):
                    c, v = cel.get(2 * mes), cel.get(2 * mes + 1)
                    if c is None and v is None: continue
                    fe = f"{anio:04d}-{mes + 1:02d}-{dia:02d}"
                    ult = fx[clave][-1][0] if fx[clave] else ""
                    if fe > ult or fe >= (pd.Timestamp(ult) - pd.Timedelta(days=7)).strftime("%Y-%m-%d"):
                        poner(fx[clave], [fe, c, v]); n += 1
            print("promedio PDF", clave, n, "filas recientes", fx[clave][-1])
        except Exception as e:
            print("promedio PDF", clave, "error:", e)


def main():
    fx = {"fuente": "Banco Central de la República Dominicana · Mercado cambiario"}
    # 1) Referencia (spot): tasa de cambio de referencia del mercado, desde 1991
    fx["ref"] = diaria(bajar("TASA_DOLAR_REFERENCIA_MC.xlsx")["Diaria"])
    # 2) Tasa promedio de compra y venta: entidades financieras y agentes de cambio
    fx["ef"] = diaria(next(iter(bajar("TASA_ENTIDADES_FINANCIERAS.xls").values())))
    fx["ag"] = diaria(next(iter(bajar("TASAS_AGENTES_CAMBIO.xls").values())))
    # 3) Otras monedas (DOP por unidad), desde 2004
    df = next(iter(bajar("TASAS_CONVERTIBLES_OTRAS_MONEDAS.xlsx").values()))
    hdr = next(i for i in range(10) if sin(df.iat[i, 0]) == "ano")
    nombres = [str(x).strip().title() for x in df.iloc[hdr, 3:] if pd.notna(x)]
    filas = diaria(df.iloc[hdr + 1:], 3, len(nombres), 4)
    vivas = [i for i, n in enumerate(nombres) if not n.startswith("*") and any(r[i + 1] is not None for r in filas[-30:])]
    fx["otras"] = {"monedas": [nombres[i].replace("Brasileno", "Brasileño").replace("Japones", "Japonés") for i in vivas], "rows": [[r[0]] + [r[i + 1] for i in vivas] for r in filas]}
    # 4) Sondeo de cotizaciones: dólar/euro × ventanilla/transferencia/cheque (entidades y agentes, compra y venta)
    fx["sondeo"] = {}
    for mon, mf in (("USD", "DOLAR"), ("EUR", "EURO")):
        for ins, inf in (("ventanilla", "VENTANILLA"), ("transferencia", "TRANSFERENCIA"), ("cheque", "CHEQUE")):
            try:
                fx["sondeo"][f"{mon}_{ins}"] = diaria(next(iter(bajar(f"{mf}_{inf}_SONDEO.xlsx").values())), 3, 4)
            except Exception as e:
                print("sondeo", mon, ins, "no disponible:", e)
    # 5) Volatilidad (bancos múltiples)
    fx["vol"] = {}
    for mon, f in (("USD", "VOLATILIDAD_DOLAR.xls"), ("EUR", "VOLATILIDAD_EURO.xls")):
        df = next(iter(bajar(f).values()))
        filas = []
        for r in df.itertuples(index=False):
            r = list(r)
            fe = fecha(r[1], r[2], r[3]) if len(r) > 6 else None
            if fe and num(r[4]) is not None: filas.append([fe, num(r[4]), num(r[6], 6)])
        de = vo = None
        for i in range(min(12, len(df))):
            t = sin(df.iat[i, 3]) if pd.notna(df.iat[i, 3]) else ""
            if t.startswith("desviacion"): de = num(df.iat[i, 6], 6)
            if t.startswith("volatilidad"): vo = num(df.iat[i, 6], 6)
        fx["vol"][mon] = {"rows": filas, "desv": de, "vol": vo}
    # 6) Mercado de derivados financieros (dólar)
    fx["der"] = diaria(next(iter(bajar("TASA_DOLAR_MERCADO_DERIVADOS.xls").values())))
    # 7) Volumen de operaciones cambiarias (US$ millones, mensual)
    df = bajar("Operaciones_us.xls")
    m = next(v for k, v in df.items() if "mensual" in sin(k))
    filas, ano = [], None
    for r in m.itertuples(index=False):
        r = list(r)
        if pd.notna(r[0]) and str(r[0]).strip().split(".")[0].isdigit(): ano = int(float(r[0]))
        mm = MES.get(sin(r[1])[:3]) if pd.notna(r[1]) else None
        if ano and mm:
            v = [num(x, 3) for x in r[2:14]]
            if any(x is not None for x in v): filas.append([f"{ano:04d}-{mm:02d}"] + v)
    fx["volumen"] = {"cols": ["ef_net_c", "ef_net_v", "ef_br_c", "ef_br_v", "ag_net_c", "ag_net_v", "ag_br_c", "ag_br_v", "tot_net_c", "tot_net_v", "tot_br_c", "tot_br_v"], "rows": filas}
    # no perder días ya publicados: se combinan con la versión anterior (lo nuevo manda)
    try:
        import gzip
        sys.path.insert(0, os.path.dirname(__file__))
        import supa
        if supa.URL and supa.bajar_archivo("fx.json.gz", "data/fx_prev.json.gz"):
            prev = json.loads(gzip.decompress(open("data/fx_prev.json.gz", "rb").read()))
            def unir(nuevo, viejo):
                d = {r[0]: r for r in viejo}
                d.update({r[0]: r for r in nuevo})
                return [d[k] for k in sorted(d)]
            for k in ("ref", "ef", "ag", "der"):
                if k != "der": fx[k] = unir(fx[k], prev.get(k, []))
            for k, v in prev.get("sondeo", {}).items():
                fx["sondeo"][k] = unir(fx["sondeo"].get(k, []), v)
            if prev.get("otras", {}).get("monedas") == fx["otras"]["monedas"]:
                fx["otras"]["rows"] = unir(fx["otras"]["rows"], prev["otras"]["rows"])
            print("combinado con la versión anterior")
    except Exception as e:
        print("sin versión anterior:", e)
    for paso in (hoy_referencia, hoy_otras, hoy_sondeo, hoy_promedio):
        try: paso(fx)
        except Exception as e: print(paso.__name__, "error:", e)
    fx["actualizado"] = pd.Timestamp.now(tz="America/Santo_Domingo").strftime("%Y-%m-%d %H:%M")
    for k in ("ref", "ef", "ag", "der"): print(k, len(fx[k]), fx[k][-1] if fx[k] else None)
    print("otras", len(fx["otras"]["rows"]), fx["otras"]["monedas"])
    print("sondeo", {k: len(v) for k, v in fx["sondeo"].items()})
    print("vol", {k: (len(v["rows"]), v["desv"], v["vol"]) for k, v in fx["vol"].items()})
    print("volumen", len(filas), filas[-1] if filas else None)
    os.makedirs("data/out", exist_ok=True)
    cuerpo = {k: v for k, v in fx.items() if k != "actualizado"}
    h = hashlib.sha1(json.dumps(cuerpo, sort_keys=True).encode()).hexdigest()
    fx["hash"] = h
    import gzip
    crudo = json.dumps(fx, ensure_ascii=False, separators=(",", ":")).encode()
    open(OUT, "wb").write(crudo)
    open(OUT + ".gz", "wb").write(gzip.compress(crudo, 9))
    print("fx.json", len(crudo) // 1024, "KB · comprimido", os.path.getsize(OUT + ".gz") // 1024, "KB")
    if "--no-subir" in sys.argv: return
    sys.path.insert(0, os.path.dirname(__file__))
    import supa
    anterior = os.path.exists("data/fx_hash.txt") and open("data/fx_hash.txt").read().strip()
    if supa.bajar_archivo("estado/fx_hash.txt", "data/fx_hash.txt"): anterior = open("data/fx_hash.txt").read().strip()
    if anterior == h:
        print("Sin cambios en los datos del Banco Central."); return
    supa.subir_archivo(OUT + ".gz", "fx.json.gz")
    open("data/fx_hash.txt", "w").write(h)
    supa.subir_archivo("data/fx_hash.txt", "estado/fx_hash.txt")
    print("Subido fx.json (datos nuevos).")


if __name__ == "__main__":
    main()
