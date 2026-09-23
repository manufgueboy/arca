---
name: crear-skill
description: Crear una skill nueva para Arca a partir de una tarea que el usuario quiera repetir. Usar cuando diga "crea una skill", "enséñate a hacer X", "guarda esto como proceso".
---

# Crear una skill nueva

1. Pregunta (si no está claro): qué tarea resuelve, cuándo debe activarse y qué pasos sigue.
2. Elige un nombre corto en minúsculas con guiones (ej. `reporte-semanal`).
3. Escribe el archivo `~/.arca/skills/<nombre>/SKILL.md` con `escribir_archivo`, con este formato exacto:

```
---
name: <nombre>
description: <una frase: qué hace y CUÁNDO usarla, con palabras que diría el usuario>
---

# <Título>

1. Paso concreto usando las herramientas de Arca (terminal, applescript, chrome_*, buscar_web, leer_archivo, escribir_archivo…)
2. …
```

4. Pasos concretos y verificables. Incluye qué hacer si algo falla.
5. Confirma al usuario la ruta y que la skill ya está disponible (Arca la carga sola en la siguiente tarea).
