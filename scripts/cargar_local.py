"""
Carga en Ámbar los Boletines Consolidados de la BVRD que descargaste a mano en tu navegador.
No se conecta a la BVRD: solo procesa los Excel que ya están en tu computadora y sube el resultado a Supabase.

Busca archivos *Consolidado*.xlsx en tu carpeta Descargas y en <base>\\descargas, toma la fecha del nombre
(DD-MM-AAAA), los procesa del más antiguo al más nuevo (si hay dos del mismo día, queda el descargado último)
y los mueve a <base>\\procesados.

Uso (Windows):  C:\\AmbarBot\\venv\\Scripts\\python.exe C:\\AmbarBot\\repo\\scripts\\cargar_local.py
Opciones:       --base C:\\AmbarBot      carpeta de instalación (por defecto, la carpeta que contiene el repositorio)
                archivo1.xlsx ...        procesar solo esos archivos
Credenciales:   <base>\\.env con SUPABASE_URL y SUPABASE_SERVICE_KEY
"""
import os, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATRON = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

def cargar_env(p: Path):
    if not p.exists():
        sys.exit(f"[ERROR] No encuentro {p}. Ejecuta primero el instalador.")
    for linea in p.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        sys.exit(f"[ERROR] Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY en {p}")

def buscar(base: Path, explicitos):
    if explicitos:
        return [Path(a).resolve() for a in explicitos]
    carpetas = [Path.home() / "Downloads", base / "descargas"]
    vistos, out = set(), []
    for c in carpetas:
        if c.is_dir():
            for f in c.glob("*Consolidado*.xlsx"):
                if f.resolve() not in vistos:
                    vistos.add(f.resolve()); out.append(f.resolve())
    return out

def fecha_de(f: Path):
    m = PATRON.search(f.name)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None

def es_excel(f: Path):
    try:
        with open(f, "rb") as fh:
            return fh.read(2) == b"PK"
    except OSError:
        return False

def correr(*args, obligatorio=True):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, *args], cwd=REPO, env=env)
    if r.returncode != 0 and obligatorio:
        sys.exit(f"[ERROR] Falló: {' '.join(args)}")
    return r.returncode == 0

def main():
    a = sys.argv[1:]
    base = REPO.parent
    if a[:1] == ["--base"]:
        base, a = Path(a[1]), a[2:]
    cargar_env(base / ".env")
    procesados = base / "procesados"; procesados.mkdir(parents=True, exist_ok=True)

    lista, malos = [], []
    for f in buscar(base, a):
        d = fecha_de(f)
        if not f.exists() or not d:
            malos.append(f"{f.name}: sin fecha DD-MM-AAAA en el nombre"); continue
        if not es_excel(f):
            malos.append(f"{f.name}: no es un Excel válido (¿se guardó una página de error?)"); continue
        lista.append((d, f.stat().st_mtime, f))
    for m in malos:
        print(f"[AVISO] Se omite {m}")
    if not lista:
        sys.exit("[ERROR] No hay boletines para cargar. Descárgalos primero en tu navegador.")
    lista.sort()

    print("Boletines a cargar:")
    for d, _, f in lista:
        print(f"  {d}  {f.name}")

    if shutil.which("git"):
        subprocess.run(["git", "-C", str(REPO), "pull", "--ff-only", "-q"])
    print("\n[1/4] Trayendo el estado desde Supabase...")
    correr("scripts/supa.py", "bajar-estado")
    print("\n[2/4] Procesando boletines...")
    for d, _, f in lista:
        correr("scripts/boletin.py", "--archivo", str(f), d)
    print("\n[3/4] Preparando los datos de la terminal...")
    correr("scripts/build_data.py")
    print("\n[4/4] Subiendo a Supabase...")
    correr("scripts/supa.py", "subir")
    correr("scripts/publicar.py", obligatorio=False)

    for _, _, f in lista:
        destino = procesados / f.name
        if destino.exists():
            destino = procesados / f"{f.stem}-{int(f.stat().st_mtime)}{f.suffix}"
        shutil.move(str(f), str(destino))
    print(f"\nListo: {len(lista)} boletín(es) cargado(s). Los archivos quedaron en {procesados}. Recarga Ámbar.")

if __name__ == "__main__":
    main()
