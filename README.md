# Ámbar — Terminal financiera para la República Dominicana

Prototipo desarrollado por JSRC, no para distribución.

## Cómo funciona
- `index.html` — la terminal. Lee los datos de `data/data.js`.
- `scripts/boletin.py` — descarga y procesa el Boletín Consolidado diario de la BVRD.
- `scripts/noticias.py` — recopila titulares (solo titular y enlace) de Diario Libre y Diario Financiero.
- `scripts/build_data.py` — convierte los CSV de `data/` en `data/data.js`.
- `.github/workflows/diario.yml` — robot automático: lunes a viernes, 8:15 am (noticias) y 6:00 pm hora RD (boletín + noticias).
- `.github/workflows/historial.yml` — carga histórica de boletines entre dos fechas (se corre a mano).

## Datos (carpeta `data/`)
- `operaciones.csv` — cada operación del mercado secundario.
- `precios.csv` — precio y rendimiento por título y día (promedio ponderado por monto).
- `emisiones.csv` — catálogo de emisiones corporativas vigentes (último boletín).
- `noticias.json` — últimos 200 titulares.

## Si algo falla
GitHub envía un correo al dueño del repositorio cuando un robot falla.
Revisa la pestaña **Actions**, abre la corrida en rojo y lee el paso que falló.
Mensajes comunes:
- `sin boletín (404)` — ese día no hubo boletín (feriado) o la BVRD cambió la dirección del archivo.
- `ERROR` en noticias — el periódico cambió su página; el resto sigue funcionando.
