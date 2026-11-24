"""
Registro de versiones de Ámbar (control interno): arma docs/Registro_de_versiones_Ambar.xlsx
a partir del historial de git y de docs/versiones.json (una fila por versión publicada).
Para una versión nueva: agregarla a docs/versiones.json (commit y rama de respaldo) y correr
  python scripts/registro_versiones.py
"""
import datetime, json, os, re, subprocess
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

REPO = "https://github.com/rodriguezcaprettini/Ambar"
OUT = "docs/Registro_de_versiones_Ambar.xlsx"
NAVY, GOLD, GRIS = "14233B", "E09A2C", "F4F6F9"
F = "Arial"

AREAS = [  # (palabras al inicio o dentro del mensaje, área)
    (r"^(MKT|Mercado|Tablero|Franja|Métricas|Metricas)", "MKT · Mercado"), (r"^(Curva|Ficha)", "MKT · Curva y fichas"),
    (r"^(Cinta)", "Cinta"), (r"^(RF|FND|EMI|OPS|Renta fija|Tablas)", "RF · FND · EMI · OPS"),
    (r"^(PDB|Puestos)", "PDB · Puestos de bolsa"), (r"^(NEWS|Noticias|Archivo de noticias|Robot de noticias|Barra de búsqueda)", "Noticias"),
    (r"^(Chat|Usuario|Perfil|Foto|Compañía|Botón de usuario)", "Usuarios y chat"), (r"(FX|Divisas|divisas)", "FX · Divisas"),
    (r"^(MACRO|Publicaciones|NUEVO)", "MACRO · Publicaciones"), (r"^(Gráficas|Herramientas|Datos quitados|Montos)", "Gráficas"),
    (r"^(Pestañas|Pantalla de carga|Medición|Tipografía|Logo|Nuevo logo|Inicio de sesión|Nueva fachada|Fechas|Hora de RD|Zona horaria|Configuración|Filtros|Terminal)", "Interfaz general"),
    (r"^(Robots?|Boletín|Calendario|Supabase|Respaldo|Banco Central|Acceso|Datos fuera|Add |Create |Delete |Organizar|Initial|Crear cuenta)", "Robots e infraestructura"),
]


def area(msg):
    for pat, a in AREAS:
        if re.search(pat, msg): return a
    return "Otros"


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()


def main():
    V = json.load(open("docs/versiones.json", encoding="utf-8"))
    log = [l.split("\x1f") for l in git("log", "--reverse", "--format=%H\x1f%h\x1f%cI\x1f%s").splitlines()]
    pos = {h: i for i, (h, *_rest) in enumerate(log)}
    full = {r[1]: r[0] for r in log}
    for v in V: v["full"] = full.get(v["commit"]) or git("rev-parse", v["commit"]); v["i"] = pos[v["full"]]
    V.sort(key=lambda v: v["i"])
    rd = datetime.timezone(datetime.timedelta(hours=-4))
    filas = []
    for i, (h, hc, fecha, msg) in enumerate(log):
        if msg.startswith("Registro de versiones"): continue
        ver = next((v for v in V if v["i"] >= i), None)
        t = datetime.datetime.fromisoformat(fecha).astimezone(rd)
        filas.append([t.date(), t.strftime("%H:%M"), ver["version"] if ver else "En desarrollo", hc, area(msg), msg, f"{REPO}/commit/{h}"])

    wb = Workbook()
    hdr_font, hdr_fill = Font(name=F, bold=True, color="FFFFFF", size=10), PatternFill("solid", fgColor=NAVY)
    body, link = Font(name=F, size=10), Font(name=F, size=10, color="1F5FBF", underline="single")
    thin = Border(bottom=Side(style="thin", color="E3E8EF"))

    # --- Versiones ---
    ws = wb.active; ws.title = "Versiones"
    ws["A1"] = "TERMINAL ÁMBAR · REGISTRO DE VERSIONES"; ws["A1"].font = Font(name=F, bold=True, size=14, color=NAVY)
    ws["A2"] = "Control interno. Cada versión enlaza al código completo de la terminal en GitHub (zip descargable) y a su rama de respaldo."
    ws["A2"].font = Font(name=F, size=10, italic=True, color="6B7789")
    H = ["Versión", "Nombre", "Fecha", "Commit", "Rama de respaldo", "Cambios incluidos", "Resumen", "Descargar terminal (zip)", "Ver en GitHub"]
    for c, h in enumerate(H, 1):
        x = ws.cell(4, c, h); x.font, x.fill = hdr_font, hdr_fill; x.alignment = Alignment(vertical="center", wrap_text=True)
    for r, v in enumerate(V, 5):
        vals = [v["version"], v["nombre"], datetime.date.fromisoformat(v["fecha"]), v["commit"], v["rama"],
                f'=COUNTIF(Cambios!$C$5:$C${len(filas) + 4},A{r})', v["resumen"], "Descargar", "Abrir"]
        for c, val in enumerate(vals, 1):
            x = ws.cell(r, c, val); x.font = body; x.border = thin; x.alignment = Alignment(vertical="top", wrap_text=c == 7)
        ws.cell(r, 3).number_format = "DD-MMM-YYYY"
        ws.cell(r, 8).hyperlink = f"{REPO}/archive/{v['full']}.zip"; ws.cell(r, 8).font = link
        ws.cell(r, 9).hyperlink = f"{REPO}/tree/{v['rama']}"; ws.cell(r, 9).font = link
    tot = len(V) + 5
    ws.cell(tot, 5, "Total de cambios").font = Font(name=F, bold=True, size=10)
    ws.cell(tot, 6, f"=SUM(F5:F{tot - 1})").font = Font(name=F, bold=True, size=10)
    ws.cell(tot + 2, 1, "Nota: “Cambios incluidos” cuenta los cambios (commits) de la hoja Cambios asignados a cada versión. Los enlaces de descarga apuntan al commit exacto, así que no cambian aunque la terminal siga avanzando.").font = Font(name=F, size=9, italic=True, color="6B7789")
    for c, w in enumerate([9, 15, 13, 10, 23, 11, 90, 14, 12], 1): ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A5"

    # --- Cambios ---
    wc = wb.create_sheet("Cambios")
    wc["A1"] = "TERMINAL ÁMBAR · HISTORIAL DE CAMBIOS"; wc["A1"].font = Font(name=F, bold=True, size=14, color=NAVY)
    wc["A2"] = "Cada fila es un cambio publicado (commit en GitHub). Hora de República Dominicana (UTC-4)."; wc["A2"].font = Font(name=F, size=10, italic=True, color="6B7789")
    HC = ["Fecha", "Hora (RD)", "Versión", "Commit", "Área", "Descripción del cambio", "Enlace"]
    for c, h in enumerate(HC, 1):
        x = wc.cell(4, c, h); x.font, x.fill = hdr_font, hdr_fill
    for r, f in enumerate(filas, 5):
        for c, val in enumerate(f[:6] + ["Ver cambio"], 1):
            x = wc.cell(r, c, val); x.font = body; x.alignment = Alignment(vertical="top", wrap_text=c == 6)
        wc.cell(r, 1).number_format = "DD-MMM-YYYY"
        wc.cell(r, 7).hyperlink = f[6]; wc.cell(r, 7).font = link
    end = len(filas) + 4
    t = Table(displayName="Cambios", ref=f"A4:G{end}"); t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True); wc.add_table(t)
    for c, w in enumerate([13, 10, 9, 10, 24, 100, 12], 1): wc.column_dimensions[get_column_letter(c)].width = w
    wc.freeze_panes = "A5"

    # --- Resumen por área ---
    wa = wb.create_sheet("Por área")
    wa["A1"] = "CAMBIOS POR ÁREA Y VERSIÓN"; wa["A1"].font = Font(name=F, bold=True, size=14, color=NAVY)
    areas = sorted({f[4] for f in filas})
    wa.cell(3, 1, "Área").font = hdr_font; wa.cell(3, 1).fill = hdr_fill
    for j, v in enumerate(V, 2):
        x = wa.cell(3, j, "V" + v["version"]); x.font, x.fill = hdr_font, hdr_fill; x.alignment = Alignment(horizontal="center")
    x = wa.cell(3, len(V) + 2, "Total"); x.font, x.fill = hdr_font, hdr_fill
    for i, a in enumerate(areas, 4):
        wa.cell(i, 1, a).font = body
        for j, v in enumerate(V, 2):
            wa.cell(i, j, f'=COUNTIFS(Cambios!$E$5:$E${end},$A{i},Cambios!$C$5:$C${end},"{v["version"]}")').font = body
        wa.cell(i, len(V) + 2, f"=SUM(B{i}:{get_column_letter(len(V) + 1)}{i})").font = Font(name=F, bold=True, size=10)
    last = len(areas) + 4
    wa.cell(last, 1, "Total").font = Font(name=F, bold=True, size=10)
    for j in range(2, len(V) + 3):
        col = get_column_letter(j); wa.cell(last, j, f"=SUM({col}4:{col}{last - 1})").font = Font(name=F, bold=True, size=10)
    wa.column_dimensions["A"].width = 28
    for j in range(2, len(V) + 3): wa.column_dimensions[get_column_letter(j)].width = 9

    os.makedirs("docs", exist_ok=True)
    wb.save(OUT)
    print(OUT, len(V), "versiones,", len(filas), "cambios")


if __name__ == "__main__":
    main()
