---
name: organizar-carpeta
description: Ordenar una carpeta desordenada (Descargas, Escritorio, etc.) moviendo archivos a subcarpetas por tipo. Usar cuando pidan organizar, limpiar u ordenar una carpeta.
---

# Organizar una carpeta

1. Usa `listar_carpeta` sobre la carpeta indicada (por default `~/Downloads`).
2. Propón un plan ANTES de mover nada. Categorías sugeridas:
   - Imágenes (jpg, jpeg, png, gif, heic, webp, svg)
   - Documentos (pdf, doc, docx, pages, txt, md, rtf)
   - Hojas de cálculo (xls, xlsx, csv, numbers)
   - Presentaciones (ppt, pptx, key)
   - Video (mp4, mov, mkv), Audio (mp3, wav, m4a)
   - Instaladores (dmg, pkg, zip, rar, 7z)
   - Otros
3. Muéstrale al usuario cuántos archivos van a cada categoría y espera su OK.
4. Mueve con `terminal` usando `mkdir -p` y `mv -n` (nunca sobrescribas; `-n` evita pisar archivos). Nunca borres nada.
5. Al final reporta qué se movió y dónde.
