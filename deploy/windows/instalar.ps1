# Instala en Windows la carga de boletines de Ámbar (una sola vez).
# Uso: en PowerShell ->  powershell -ExecutionPolicy Bypass -File instalar.ps1
# No instala navegadores automatizados: la descarga del boletín la haces tú en tu navegador.
$ErrorActionPreference = "Stop"
$Base = "C:\AmbarBot"

function Falta($cmd, $donde) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] Falta $cmd. Instálalo desde $donde y vuelve a ejecutar este instalador." -ForegroundColor Red
        exit 1
    }
}
Falta "python" "https://www.python.org/downloads/ (marca 'Add python.exe to PATH')"
Falta "git" "https://git-scm.com/download/win"

Write-Host "1/4 Carpeta y código..."
New-Item -ItemType Directory -Force -Path $Base, "$Base\descargas", "$Base\procesados" | Out-Null
if (Test-Path "$Base\repo\.git") { git -C "$Base\repo" pull --ff-only -q }
else { git clone -q https://github.com/rodriguezcaprettini/Ambar.git "$Base\repo" }

Write-Host "2/4 Python y paquetes (puede tardar unos minutos)..."
if (-not (Test-Path "$Base\venv\Scripts\python.exe")) { python -m venv "$Base\venv" }
& "$Base\venv\Scripts\python.exe" -m pip install -q --upgrade pip
& "$Base\venv\Scripts\python.exe" -m pip install -q requests pandas openpyxl beautifulsoup4 numpy tzdata

Write-Host "3/4 Credenciales de Supabase (quedan solo en $Base\.env)"
if (-not (Test-Path "$Base\.env")) {
    $url = Read-Host "SUPABASE_URL (https://xxxx.supabase.co)"
    $sec = Read-Host "SUPABASE_SERVICE_KEY (no se verá al escribir)" -AsSecureString
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    [IO.File]::WriteAllText("$Base\.env", "SUPABASE_URL=$url`r`nSUPABASE_SERVICE_KEY=$key`r`n")
    # solo tu usuario puede leer el archivo
    icacls "$Base\.env" /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
}

Write-Host "4/4 Acceso directo en el Escritorio..."
Copy-Item -Force "$Base\repo\deploy\windows\cargar_boletines.bat" "$Base\cargar_boletines.bat"
$esc = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$esc\Cargar boletines Ambar.lnk")
$lnk.TargetPath = "$Base\cargar_boletines.bat"
$lnk.WorkingDirectory = $Base
$lnk.Save()

Write-Host ""
Write-Host "Listo. Descarga los boletines en tu navegador y usa el acceso directo 'Cargar boletines Ambar' del Escritorio." -ForegroundColor Green
