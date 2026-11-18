# Ámbar — Terminal financiera para la República Dominicana

Prototipo desarrollado por JSRC, no para distribución.

## Cómo funciona
- `index.html` — la terminal. Acceso con cuenta (Supabase Auth); el registro exige un código de invitación. Tras iniciar sesión baja `data.json` del almacenamiento privado de Supabase.
- `scripts/boletin.py` — descarga y procesa el Boletín Consolidado diario de la BVRD.
- `scripts/noticias.py` — recopila titulares (solo titular y enlace) de Diario Libre y Diario Financiero.
- `scripts/build_data.py` — convierte los CSV de `data/` en `data/data.js` (archivo principal liviano) y `data/ops/AAAA-MM.js` (operaciones de cada mes, se cargan solo al consultarlas). Además filtra precios fuera de mercado (ver abajo).
- `.github/workflows/diario.yml` — robot automático, lunes a viernes (hora RD): 8:15 am noticias; cada hora de 1:00 a 7:00 pm busca el boletín del día (se muestra como PRELIMINAR); 9:05 pm descarga definitiva. Solo guarda cambios si el archivo de la BVRD cambió.
- `.github/workflows/historial.yml` — carga histórica de boletines entre dos fechas (se corre a mano).

## Datos (en Supabase, carpeta `estado/` del bucket privado; ya no en este repositorio)
- `operaciones.csv` — cada operación del mercado secundario.
- `precios.csv` — precio y rendimiento por título y día (promedio ponderado por monto).
- `emisiones.csv` — catálogo de emisiones corporativas vigentes (último boletín).
- `noticias.json` — últimos 200 titulares.
- `publicacion.json` — para cada boletín: hora (RD) en que apareció en el servidor de la BVRD (`en_servidor`) y primera hora en que se vio en la página pública boletines.bvrd.com.do (`en_pagina`). Lo llena `scripts/calendario.py`, que abre la página con un navegador automático.
- `calendario_red.txt` — direcciones que consulta el calendario de la BVRD (diagnóstico).
- `descargas.json` — registro de cada boletín: primera vez que apareció en el servidor de la BVRD, última descarga, número de versiones y si ya es definitivo (descargado a partir de las 9:00 pm hora RD o un día posterior). Sirve para saber a qué hora publica la BVRD.

## Si algo falla
GitHub envía un correo al dueño del repositorio cuando un robot falla.
Revisa la pestaña **Actions**, abre la corrida en rojo y lee el paso que falló. Para trabajar localmente con los datos: `python scripts/supa.py bajar-estado` (con los secretos como variables de entorno).
Mensajes comunes:
- `sin boletín (404)` — ese día no hubo boletín (feriado) o la BVRD cambió la dirección del archivo.
- `ERROR` en noticias — el periódico cambió su página; el resto sigue funcionando.

## Precios fuera de mercado
Una operación no se usa para el precio del día si su rendimiento se aleja más de 50 pb de la mediana de las 8 operaciones
más cercanas del mismo título (o su precio más de 1.5% si vence en menos de un año, o más de 10% si no reporta rendimiento). Sigue contando para el volumen.
En la pestaña Operaciones se marcan con ⚑. Umbral configurable en `scripts/build_data.py`.

## Acceso y datos privados (Supabase)
- Proyecto: https://xuspbkdedaaymngynmxe.supabase.co · bucket privado `ambar-data` (solo usuarios con sesión pueden leer).
- `scripts/calendario.py` — lee la lista `prod-data.bvrd.com.do/json/boletines.json` (la misma que usa el calendario público) y anota la primera hora en que aparece cada boletín. Si la lista falla, usa un navegador automático de respaldo.
- `scripts/supa.py` — el robot baja su estado (`estado/*.csv|json`) al empezar y sube `data.json`, `ops/AAAA-MM.json` y el estado al terminar.
- Secretos de GitHub necesarios: `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` (clave secreta; nunca en el código).
- Códigos de invitación: tabla `invite_codes` (ver `ambar_supabase_setup.sql`, que se ejecutó una vez en el SQL Editor). Quién usó cada código: tabla `invite_redemptions`.
