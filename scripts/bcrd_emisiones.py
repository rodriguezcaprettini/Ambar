"""
Fechas de emisión de los títulos del Banco Central (Notas y Letras), publicadas por el BCRD:
  - Notas_historico_vigentes.xlsx  (notas en circulación: fecha de emisión, vencimiento, ISIN)
  - Notas_historico_vencidas.pdf   (notas ya vencidas)
  - letras_bc_convocatoria.pdf     (letras de la última subasta: ISIN y fecha de emisión)
Guarda data/emisiones_bcrd.json = {ISIN: "AAAA-MM-DD"} y conserva lo ya guardado (las convocatorias se reemplazan).
Requisitos: pip install requests openpyxl pdfplumber
"""
import io, json, re, sys
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
B = "https://cdn.bancentral.gov.do/documents/instrumentos-de-inversion/instrumentos-operaciones-de-mercado-abierto/documents/"
RUTA = "data/emisiones_bcrd.json"

def fecha(s):
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", s)
    if m: return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m: return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    return None

def notas_vigentes():
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(requests.get(B + "Notas_historico_vigentes.xlsx", headers=UA, timeout=60).content), read_only=True, data_only=True)
    out = {}
    for ws in wb:
        for fila in ws.iter_rows(values_only=True):
            v = [c for c in fila if c not in (None, "")]
            isin = next((str(c).strip() for c in v if re.fullmatch(r"DO\d{10}", str(c).strip())), None)
            f = fecha(v[0]) if v else None
            if isin and f: out[isin] = f
    return out

def _pdf_lineas(url):
    import pdfplumber
    r = requests.get(url, headers=UA, timeout=60)
    if r.status_code != 200 or r.content[:4] != b"%PDF": return []
    with pdfplumber.open(io.BytesIO(r.content)) as p:
        return [l for pg in p.pages for l in (pg.extract_text() or "").splitlines()]

def notas_vencidas():
    out = {}
    for l in _pdf_lineas(B + "Notas_historico_vencidas.pdf"):
        isin = re.search(r"DO\d{10}", l); fs = re.findall(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d\d-\d\d", l)
        if isin and fs: out[isin[0]] = fecha(fs[0])  # la primera fecha de la fila es la de emisión
    return out

def convocatorias():
    out = {}
    for f in ("letras_bc_convocatoria.pdf", "notas_convocatoria.pdf"):
        L = _pdf_lineas(B + f)
        isins = next((re.findall(r"DO\d{10}", l) for l in L if l.startswith("Código ISIN")), [])
        fechas = next((re.findall(r"\d{1,2}/\d{1,2}/\d{4}", l) for l in L if l.startswith("Fecha emisión")), [])
        for i, fe in zip(isins, fechas): out[i] = fecha(fe)
    return out

def main():
    try:
        todo = json.load(open(RUTA, encoding="utf-8"))
    except FileNotFoundError:
        todo = {}
    for fn in (notas_vencidas, notas_vigentes, convocatorias):
        try:
            n = fn(); todo.update({k: v for k, v in n.items() if v}); print(f"{fn.__name__}: {len(n)} títulos")
        except Exception as e:
            print(f"{fn.__name__}: ERROR {e}", file=sys.stderr)
    json.dump(dict(sorted(todo.items())), open(RUTA, "w", encoding="utf-8"), indent=0)
    print(f"Fechas de emisión del Banco Central guardadas: {len(todo)}")

if __name__ == "__main__":
    main()
