---
name: organizar
description: Ordenar una carpeta (Descargas, Escritorio…) en subcarpetas por tipo de archivo.
activar: organiza, ordena, acomoda, limpia mis, limpia la
---
1. Usa EXACTAMENTE la carpeta que nombró el usuario. Solo si dijo "Descargas", "Escritorio" o "Documentos"
   usa ~/Downloads, ~/Desktop o ~/Documents. Si dio otro nombre (ej. "la carpeta fotos"), es una subcarpeta
   de la carpeta actual: ruta relativa "fotos". Si no existe, búscala con listar_carpeta; no la cambies por otra.
2. Llama organizar_carpeta(ruta, aplicar="si"). Arca le muestra el plan al usuario y le pide permiso antes de mover.
3. Resume cuántos archivos quedaron en cada subcarpeta. Nunca se borra nada.
