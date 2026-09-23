---
name: investigar
description: Investigar un tema en internet y entregar un reporte con fuentes. Usar cuando pidan investigar, comparar opciones, "qué hay de nuevo sobre", o un reporte.
---

# Investigar un tema

1. Divide la pregunta en 2–4 búsquedas concretas.
2. Para cada una usa `buscar_web`. Elige los 2–3 resultados más confiables (fuentes oficiales, medios serios, documentación).
3. Lee cada fuente con `leer_web`. Si una página no carga o sale vacía (sitios con mucho JavaScript), ábrela con `chrome_abrir` y léela con `chrome_leer`.
4. Contrasta: si las fuentes no coinciden, dilo. No rellenes huecos inventando.
5. Escribe el reporte en markdown:
   - Resumen de 3–5 líneas al inicio con la respuesta directa.
   - Hallazgos por sección.
   - "Fuentes:" al final con los links que usaste.
6. Si el usuario quiere archivo, guárdalo con `escribir_archivo` en `~/Documents/Arca/<tema>.md` y dile la ruta.
