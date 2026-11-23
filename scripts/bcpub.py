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
    cats = [{"id": int(c["value"]), "nombre": c.get("categoryName") or c["displayText"].split("/")[-1].strip()}
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
                items.append({"id": a["id"], "cat": c["id"], "t": titulo(a, c["nombre"]), "f": (a.get("auxiliarDatetime1") or "")[:10],
                              "sub": (a.get("creationTime") or "")[:19], "u": url(a)})
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
    nom = {c["id"]: c["nombre"] for c in cats}
    ev = [{"fuente": "Banco Central", "conjunto": f"bcpub_{i['cat']}", "titulo": i["t"], "periodo": str(i["id"]), "ruta": "macro:pub",
           "url": i["u"], "categoria": nom[i["cat"]], "detectado": (i["sub"] + "Z") if i["sub"] else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} for i in items]
    nuevos = 0
    for k in range(0, len(ev), 500):
        r = supa.rest("POST", "publicaciones?on_conflict=conjunto,periodo", json=ev[k:k + 500],
                      extra={"Prefer": "resolution=ignore-duplicates,return=representation", "content-type": "application/json"})
        if r.status_code >= 300: print("Error registrando:", r.status_code, r.text[:300]); break
        nuevos += len(r.json() or [])
    print("publicaciones nuevas registradas:", nuevos)
    ant = None
    if supa.bajar_archivo("estado/bcpub_hash.txt", "data/bcpub_hash.txt"): ant = open("data/bcpub_hash.txt").read().strip()
    if ant == h: print("Sin cambios."); return
    supa.subir_archivo(OUT + ".gz", "bcpub.json.gz")
    open("data/bcpub_hash.txt", "w").write(h)
    supa.subir_archivo("data/bcpub_hash.txt", "estado/bcpub_hash.txt")
    print("Subido bcpub.json.")


if __name__ == "__main__":
    main()
