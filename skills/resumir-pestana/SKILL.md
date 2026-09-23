---
name: resumir-pestana
description: Resumir la página que el usuario tiene abierta en Chrome (artículo, hilo, documento, video con transcripción). Usar cuando diga "resúmeme esto", "qué dice esta página", "lo que tengo abierto".
---

# Resumir la pestaña activa de Chrome

1. Usa `chrome_leer` para obtener el texto de la pestaña activa.
2. Si devuelve el aviso de "Permitir JavaScript de eventos de Apple", explícale al usuario cómo activarlo (Chrome > Ver > Opciones para desarrolladores > Permitir JavaScript de eventos de Apple) y, mientras, intenta `chrome_pestanas` + `leer_web` con la URL.
3. Entrega:
   - **En una línea:** de qué trata.
   - **Puntos clave:** 3–7 viñetas.
   - **Qué hacer con esto:** si aplica (fechas, acciones, decisiones).
4. Responde en el idioma del usuario aunque la página esté en otro.
