<p align="center"><img src="assets/Arca.png" width="120" alt="Arca"></p>

<h1 align="center">Arca</h1>

<p align="center"><b>Un asistente de IA que usa tu Mac por ti.</b><br>
Gratis, privado y sin suscripciones: corre en tu propia Mac.</p>

---

Le pides cosas en español y las hace:

- *"Recuérdame mañana a las 9 pagar la luz"* → crea el recordatorio.
- *"Organiza mi carpeta de Descargas"* → ordena todo en carpetas por tipo.
- *"Escribe un correo a mi jefe pidiendo el viernes libre"* → te deja el borrador listo en Mail.
- *"Resúmeme la página que tengo abierta"* → lee tu pestaña de Chrome y te la resume.
- *"¿Va a llover hoy?"*, *"¿Quién fue Frida Kahlo?"*, *"¿Cuánto espacio libre tengo?"*

Antes de cambiar algo en tu Mac, **te pide permiso** con un botón.

## Instalar (2 minutos)

1. Abre la app **Terminal** (⌘ + espacio, escribe *Terminal* y Enter).
2. Copia y pega esta línea, y presiona Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/manufgueboy/arca/main/install.sh | bash
```

3. Listo. Se abre **Arca** en tu navegador. Ahí eliges el "cerebro" con un botón: Arca ve cuánta memoria tiene tu Mac, te recomienda el modelo adecuado y lo descarga solo.

Después, ábrela como cualquier app: **Aplicaciones → Arca**, o ⌘ + espacio y escribe *Arca*.

> Si aparece una ventana de Apple pidiendo instalar "herramientas de línea de comandos", dale **Instalar**. Es gratis y oficial. El instalador espera y sigue solo.

## ¿Qué modelo uso?

Arca lo elige por ti según tu Mac:

| Tu Mac tiene | Modelo | Descarga |
|---|---|---|
| 8 GB de memoria | Arca Ligero (`qwen3.5:4b`) | 3.4 GB |
| 16 GB | Arca Equilibrado (`qwen3.5:9b`) | 6.6 GB |
| 32 GB | Arca Pro (`qwen3.5:27b`) | 17 GB |
| 48 GB o más | Arca Max (`qwen3.5:35b`) | 24 GB |

¿Ves cuánta memoria tienes?  → menú  → *Acerca de esta Mac*.

**Si tu Mac es lenta o tiene poco espacio**, usa un modelo gratis en la nube: en Arca toca el nombre del modelo (arriba a la derecha) → *En la nube* → Groq u OpenRouter → "Conseguir mi llave" → pégala. Ojo: en ese modo tus mensajes se envían a ese servicio.

## Chrome

Para que Arca pueda **leer páginas, dar clic y llenar formularios** en tu Chrome, activa esto una sola vez:

**Chrome → menú Ver → Opciones para desarrolladores → Permitir JavaScript de eventos de Apple**

La primera vez que Arca use una app (Chrome, Recordatorios, Mail…), macOS te preguntará si le das permiso: dale **Aceptar**.

## Privacidad

- Con un modelo local, **nada sale de tu Mac**, salvo cuando le pides buscar en internet.
- Con un modelo de nube, tus mensajes y lo que Arca lea para responderte se mandan a ese proveedor.
- Arca no tiene telemetría ni cuentas. Tu configuración vive en `~/.arca/`.

## Preguntas frecuentes

**¿Cuesta algo?** No. Arca y los modelos locales son gratis. Algunos modelos de nube son de pago, pero no los necesitas.

**¿Funciona sin internet?** Sí, con un modelo local. Solo buscar en la web, el clima y Wikipedia necesitan internet.

**¿Puede borrar mis cosas?** Antes de cualquier acción que cambie algo te muestra qué va a hacer y espera tu permiso. Puedes detenerlo en cualquier momento con **Detener**.

**¿Cómo lo actualizo?** Vuelve a pegar la línea de instalación.

**¿Cómo lo desinstalo?** Borra la app *Arca* de Aplicaciones y la carpeta `~/.arca`. Ollama se desinstala aparte, como cualquier app.

---

## Para los que sí usan la terminal

```bash
arca                      # chat en la terminal
arca "organiza mis descargas"
arca web                  # la app en el navegador
arca descargar            # baja el modelo recomendado para tu Mac
arca usar groq            # cambiar de proveedor (ollama, lmstudio, openrouter, groq, gemini, openai, anthropic)
arca login openrouter     # guardar una API key
arca modelos --gratis     # modelos gratis del proveedor
arca skills               # skills instaladas
arca doctor               # revisa que todo esté bien
```

Dentro del chat: `/modelos`, `/modelo <id>`, `/proveedor <nombre>`, `/auto`, `/nuevo`, `/salir`. `Ctrl-C` detiene una tarea.

### Cómo hace que un modelo chico funcione

Un modelo de 4B no es muy listo, así que Arca le facilita el trabajo:

- **Ejecuta más, piensa menos.** Tiene herramientas que hacen el trabajo en código: `crear_recordatorio`, `crear_evento`, `borrador_correo`, `organizar_carpeta`, `wikipedia`, `clima`, `info_mac`. El modelo solo llena los datos, sin escribir AppleScript de memoria. En modelos chicos se apaga el modo "pensar" y se baja la temperatura.
- **Datos reales en vez de memoria.** Cada pedido lleva la versión de macOS, la RAM, el disco, la fecha, la hora y los próximos 7 días. Los datos actuales se sacan de internet o Wikipedia.
- **Contexto amplio.** Usa la API nativa de Ollama con ventana de contexto según tu RAM. Por la vía estándar el modelo "olvida" la tarea.
- **Menos opciones.** El modelo chico solo ve las herramientas relevantes al pedido, y la skill que aplica se le carga sola.
- **Correcciones.** Si responde sin actuar cuando debía, se le exige una vez. Si repite la misma llamada, se le frena. Si escribe mal una llamada, se le devuelve el error para que la corrija.

El "modo compacto" se activa solo en modelos de 10B o menos. Puedes forzarlo con `"modo": "compacto"` o `"completo"` en `~/.arca/config.json`. Para medir un modelo: `python3 tests/eval.py --modelo qwen3.5:4b`.

### Skills

Una skill es una carpeta con un `SKILL.md` (mismo formato que las skills de Claude, más un campo opcional `activar`):

```markdown
---
name: reporte-semanal
description: Armar el reporte semanal.
activar: reporte semanal, reporte de la semana
---
1. Lee los archivos de ~/Documents/notas de esta semana…
2. …
```

- Si el pedido contiene alguna frase de `activar`, la skill se carga sola.
- **Skills ejecutables:** si la carpeta trae un `tool.json`, la skill se vuelve una herramienta. El modelo solo llena los parámetros y Arca corre tu script (recibe los parámetros como JSON por stdin). Ejemplo: [`skills/clima`](skills/clima).
- Las tuyas van en `~/.arca/skills/`. Crea una con `arca skill-nueva <nombre>` o pídele a Arca *"crea una skill para…"*.

Incluidas: `agenda`, `correo`, `organizar`, `investigar`, `resumir-pestana`, `clima`, `crear-skill`.

### Herramientas

| Herramienta | Qué hace | Pide permiso |
|---|---|---|
| `leer_archivo`, `listar_carpeta` | Leer archivos y carpetas | No |
| `escribir_archivo`, `terminal` | Crear archivos, ejecutar comandos | Sí |
| `organizar_carpeta` | Ordenar por tipo (nunca borra) | Sí, al mover |
| `crear_recordatorio`, `crear_evento` | Recordatorios y Calendario | No |
| `borrador_correo` | Borrador en Mail (no lo envía) | No |
| `applescript`, `abrir` | Controlar la Mac y sus apps | Sí |
| `info_mac`, `notificar` | Estado de la Mac, notificaciones | No |
| `chrome_abrir`, `chrome_clic`, `chrome_escribir`, `chrome_js` | Manejar Chrome | Sí |
| `chrome_leer`, `chrome_pestanas` | Leer Chrome | No |
| `buscar_web`, `leer_web`, `wikipedia` | Internet | No |

Agregar una herramienta es escribir una función en `arca/tools.py` con el decorador `@tool`.

### Desarrollo

```bash
git clone https://github.com/manufgueboy/arca.git && cd arca
./install.sh                          # instala desde tu copia
python3 -m unittest discover tests    # pruebas (no necesitan modelo)
python3 tests/eval.py --modelo X      # evaluación con un modelo real
```

Sin dependencias: solo la biblioteca estándar de Python 3.9+. Licencia MIT.
