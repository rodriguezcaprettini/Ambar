"""
Publicaciones del Banco Central (https://bancentral.gov.do/Publicaciones/Consulta): informes periódicos y anuales
(Informe de la Economía, Resultados Preliminares, Boletín Trimestral, IPC mensual y anual, Política Monetaria,
Remesas, Turismo, Mercado de Trabajo, etc.). Usa la misma lista JSON que carga la página del BCRD.
Arma data/out/bcpub.json para MACRO → Publicaciones y anota las nuevas en la tabla public.publicaciones
con la fecha en que el BCRD las subió a su sitio.
Uso: python scripts/bcpub.py [--no-subir]
"""
import gzip, hashlib, json, os, re, sys, time
import requests

W = "https://bancentral.gov.do"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "X-Requested-With": "XMLHttpRequest", "Referer": W + "/Publicaciones/Consulta?CategoryId=84"}
OUT = "data/out/bcpub.json"


def post(s, ruta, datos):
    for i in range(4):
        try:
            r = s.post(W + ruta, data=datos, headers=H, timeout=90)
            if r.status_code < 500: r.raise_for_status(); return r.json()
        except requests.RequestException:
            if i == 3: raise
        time.sleep(5 * (i + 1))
    raise SystemExit(f"{ruta}: el Banco Central no respondió")


MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
         "octubre": 10, "noviembre": 11, "diciembre": 12, "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8,
         "sep": 9, "oct": 10, "nov": 11, "dic": 12}
# frecuencia de cada serie del BCRD: M mensual, T trimestral, S semestral, A anual, H histórica (ya no se publica)
FREC = {81: "T", 82: "T", 83: "T", 84: "M", 85: "A", 86: "H", 87: "H", 88: "M", 89: "A", 90: "A", 91: "T", 92: "M", 93: "T", 94: "H",
        128: "S", 138: "T", 140: "M", 145: "S"}


def periodo(u, t, f):
    """Periodo de referencia (año, mes final) a partir del nombre del archivo; si no, del título o la fecha auxiliar."""
    n = re.sub(r"\?.*$", "", u.rsplit("/", 1)[-1]).lower()
    m = re.search(r"((?:19|20)\d{2})[-_ ]?(i{1,2})(?![a-z])", n)  # PERN_2026-II
    if m: return int(m.group(1)), 6 if m.group(2) == "i" else 12
    m = re.search(r"(?<!\d)(\d{2})((?:19|20)\d{2})(?!\d)", n)  # ..._062019
    if m and 1 <= int(m.group(1)) <= 12: return int(m.group(2)), int(m.group(1))
    m = re.search(r"((?:19|20)\d{2})[-_]?(\d{2})(?!\d)", n)  # 2026-06, 2025_09, boletin2025-09
    if m and 1 <= int(m.group(2)) <= 12: return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?<![a-z])e-([md])_((?:19|20)\d{2})", n)  # E-M_2020 (enero-marzo), E-D_2019 (enero-diciembre)
    if m: return int(m.group(2)), 3 if m.group(1) == "m" else 12
    ano = re.search(r"(?:19|20)\d{2}", n) or re.search(r"(?:19|20)\d{2}", t)
    if ano:
        meses = [MESES[w] for w in re.findall(r"[a-záéíóú]+", n + " " + t.lower()) if w in MESES]
        return int(ano.group(0)), (meses[-1] if meses else None)
    return (int(f[:4]), int(f[5:7])) if f else (None, None)


def titulo(a, cat):
    t = " ".join(str(a.get("title") or "").split())
    if re.fullmatch(r"[\w.-]+", t) and ("_" in t or t.islower()):  # nombres de archivo (p. ej. cipc_anual2025)
        ano = re.search(r"(19|20)\d{2}", t)
        t = cat + (" " + ano.group(0) if ano else "")
    return t


def url(a):
    if a.get("customUrl"): return a["customUrl"]
    for f in a.get("articleFiles") or []:
        n = f.get("fileName") or ""
        if n: return n if n.startswith("http") else W + "/Publicaciones/" + n
    return W + "/a/d/" + str(a.get("stringId") or a.get("id"))


def main():
    s = requests.Session()
    s.get(W + "/Publicaciones/Consulta?CategoryId=84", headers=H, timeout=90)
    cats = [{"id": int(c["value"]), "frec": FREC.get(int(c["value"]), "I"), "nombre": c.get("categoryName") or c["displayText"].split("/")[-1].strip()}
            for c in post(s, "/Home/GetPublicationCategories", {"categoryId": 84})["result"]]
    items = []
    for c in cats:
        salto = 0
        while True:
            j = post(s, "/Home/GetArticles", {"languageName": "", "requestIsFromPortal": "true", "filter": "", "categoryId": c["id"],
                                              "auxiliarDatetime1Year": "", "categoryCode": "", "showInSlider": "false", "showInList": "false",
                                              "orderByDateAuxiliarDateTime1": "desc", "skipCount": salto, "maxResultCount": 150, "sorting": ""})["result"]
            lote = j.get("items") or []
            for a in lote:
                if a.get("isDeleted") or a.get("isActive") is False: continue
                u, f = url(a), (a.get("auxiliarDatetime1") or "")[:10]
                if any(i["u"] == u for i in items): continue  # el BCRD repite algunos archivos
                py, pm = periodo(u, a.get("title") or "", f)
                items.append({"id": a["id"], "cat": c["id"], "t": titulo(a, c["nombre"]), "f": f, "py": py, "pm": pm,
                              "sub": (a.get("creationTime") or "")[:19], "u": u})
            salto += len(lote)
            if not lote or salto >= (j.get("totalCount") or 0): break
        print(c["id"], c["nombre"], sum(1 for i in items if i["cat"] == c["id"]))
    items.sort(key=lambda i: (i["sub"], i["id"]), reverse=True)
    P = {"fuente": "Banco Central de la República Dominicana · Publicaciones", "cats": cats, "items": items}
    h = hashlib.sha1(json.dumps(P, sort_keys=True).encode()).hexdigest()
    P["hash"] = h
    os.makedirs("data/out", exist_ok=True)
    crudo = json.dumps(P, ensure_ascii=False, separators=(",", ":")).encode()
    open(OUT, "wb").write(crudo)
    open(OUT + ".gz", "wb").write(gzip.compress(crudo, 9))
    print("bcpub.json", len(items), "publicaciones ·", len(crudo) // 1024, "KB")
    if "--no-subir" in sys.argv: return
    sys.path.insert(0, os.path.dirname(__file__))
    import supa
    ant = None
    if supa.bajar_archivo("estado/bcpub_hash.txt", "data/bcpub_hash.txt"): ant = open("data/bcpub_hash.txt").read().strip()
    if ant == h: print("Sin cambios."); return
    nom = {c["id"]: c["nombre"] for c in cats}
    ev = [{"fuente": "Banco Central", "conjunto": f"bcpub_{i['cat']}", "titulo": i["t"], "periodo": str(i["id"]), "ruta": "macro:pub",
           "url": i["u"], "categoria": nom[i["cat"]], "cat": i["cat"], "py": i["py"], "pm": i["pm"], "detectado": (i["sub"] + "Z") if i["sub"] else ((i["f"] + "T12:00:00Z") if i["f"] else "2018-01-18T12:00:00Z")} for i in items]
    nuevos = 0
    for k in range(0, len(ev), 500):
        r = supa.rest("POST", "publicaciones?on_conflict=conjunto,periodo", json=ev[k:k + 500],
                      extra={"Prefer": "resolution=merge-duplicates,return=representation", "content-type": "application/json"})
        if r.status_code >= 300: print("Error registrando:", r.status_code, r.text[:300]); break
        nuevos += len(r.json() or [])
    print("publicaciones registradas o actualizadas:", nuevos)
    supa.subir_archivo(OUT + ".gz", "bcpub.json.gz")
    open("data/bcpub_hash.txt", "w").write(h)
    supa.subir_archivo("data/bcpub_hash.txt", "estado/bcpub_hash.txt")
    print("Subido bcpub.json.")


if __name__ == "__main__":
    main()
