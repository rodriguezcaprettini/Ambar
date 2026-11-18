# Ámbar — Terminal financiera para la República Dominicana

Prototipo desarrollado por JSRC, no para distribución.

## Cómo funciona
- `index.html` — la terminal. Lee los datos de `data/data.js`.
- `scripts/boletin.py` — descarga y procesa el Boletín Consolidado diario de la BVRD.
- `scripts/noticias.py` — recopila titulares (solo titular y enlace) de Diario Libre y Diario Financiero.
- `scripts/build_data.py` — convierte los CSV de `data/` en `data/data.js` (archivo principal liviano) y `data/ops/AAAA-MM.js` (operaciones de cada mes, se cargan solo al consultarlas). Además filtra precios fuera de mercado (ver abajo).
- `.github/workflows/diario.yml` — robot automático, lunes a viernes (hora RD): 8:15 am noticias; cada hora de 1:00 a 7:00 pm busca el boletín del día (se muestra como PRELIMINAR); 9:05 pm descarga definitiva. Solo guarda cambios si el archivo de la BVRD cambió.
- `.github/workflows/historial.yml` — carga histórica de boletines entre dos fechas (se corre a mano).

## Datos (carpeta `data/`)
- `operaciones.csv` — cada operación del mercado secundario.
- `precios.csv` — precio y rendimiento por título y día (promedio ponderado por monto).
- `emisiones.csv` — catálogo de emisiones corporativas vigentes (último boletín).
- `noticias.json` — últimos 200 titulares.
- `descargas.json` — registro de cada boletín: primera vez que apareció en el servidor de la BVRD, última descarga, número de versiones y si ya es definitivo (descargado a partir de las 9:00 pm hora RD o un día posterior). Sirve para saber a qué hora publica la BVRD.

## Si algo falla
GitHub envía un correo al dueño del repositorio cuando un robot falla.
Revisa la pestaña **Actions**, abre la corrida en rojo y lee el paso que falló.
Mensajes comunes:
- `sin boletín (404)` — ese día no hubo boletín (feriado) o la BVRD cambió la dirección del archivo.
- `ERROR` en noticias — el periódico cambió su página; el resto sigue funcionando.

## Precios fuera de mercado
Una operación no se usa para el precio del día si su rendimiento se aleja más de 50 pb de la mediana de las 8 operaciones
más cercanas del mismo título (o su precio más de 1.5% si vence en menos de un año, o más de 10% si no reporta rendimiento). Sigue contando para el volumen.
En la pestaña Operaciones se marcan con ⚑. Umbral configurable en `scripts/build_data.py`.
