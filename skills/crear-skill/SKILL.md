---
name: crear-skill
description: Crear una skill nueva de Arca para una tarea que el usuario quiera repetir.
activar: crea una skill, nueva skill, enséñate, ensenate, guarda esto como proceso
---
1. Si no está claro, pregunta: qué tarea resuelve y con qué palabras la pediría el usuario.
2. Nombre corto en minúsculas con guiones, ej. reporte-semanal.
3. Escribe ~/.arca/skills/<nombre>/SKILL.md con escribir_archivo, exactamente así:
   ---
   name: <nombre>
   description: <qué hace, en una frase>
   activar: <palabras que diría el usuario, separadas por comas>
   ---
   1. Paso concreto usando herramientas de Arca…
   2. …
4. Pasos cortos y concretos. Confirma la ruta: ya queda activa para la próxima vez.
