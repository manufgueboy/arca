# ⛵ Arca

**Un agente de IA que usa tu Mac por ti.** Controla tus apps, Chrome, archivos y terminal con el modelo que tú quieras: local y gratis (Ollama, LM Studio), gratis en la nube (OpenRouter, Groq, Gemini) o de pago (OpenAI, Claude). Aprende tareas nuevas con **skills**.

- 🔒 **Privado por default**: con Ollama todo corre en tu Mac, sin internet y sin cuentas.
- 🧠 **Cualquier modelo**: cambias de proveedor con un comando. Si un modelo no soporta herramientas, Arca igual lo hace funcionar como agente.
- 🖥️ **Usa tu Mac de verdad**: AppleScript (Mail, Notas, Calendario, Recordatorios, Finder, Música…), `open`, notificaciones, terminal.
- 🌐 **Maneja tu Chrome**: abre páginas, lee, da clic y llena formularios con tus sesiones ya iniciadas.
- 🧩 **Skills**: carpetas con un `SKILL.md` (mismo formato que las skills de Claude). Agrega las tuyas o pídele a Arca que las cree.
- ✋ **Tú mandas**: pide permiso antes de cualquier acción que cambie algo. `Ctrl-C` interrumpe en cualquier momento.
- 📦 **Cero dependencias**: solo Python, que ya viene con tu Mac.

```
› organiza mis descargas por tipo de archivo
  ⚙ usar_skill(nombre=organizar-carpeta)
  ⚙ listar_carpeta(ruta=~/Downloads)
  ⚙ terminal(comando=mkdir -p ~/Downloads/{Imágenes,Documentos,Instaladores} && mv -n …)
    ¿Permitir? [s]í / [n]o / [t]odo esta sesión: s

Listo: moví 48 imágenes, 23 PDFs y 11 instaladores a sus carpetas.
```

## Instalación

```bash
git clone https://github.com/manufgueboy/arca.git
cd arca
./install.sh
```

El instalador pone el comando `arca` y, si quieres, instala [Ollama](https://ollama.com) y descarga un modelo local (`qwen3:8b`, ~5 GB).

Luego:

```bash
arca doctor     # revisa que todo esté bien
arca            # abre el chat
```

## Elegir modelo

```bash
arca proveedores                 # lista de proveedores
arca usar ollama qwen3:8b        # local
arca modelos                     # modelos del proveedor actual
```

| Proveedor | Costo | Qué necesitas |
|---|---|---|
| `ollama` | Gratis, local | `brew install ollama` y `ollama pull qwen3:8b` |
| `lmstudio` | Gratis, local | [LM Studio](https://lmstudio.ai) con el servidor encendido |
| `openrouter` | Modelos `:free` gratis | Key en [openrouter.ai/keys](https://openrouter.ai/keys) |
| `groq` | Plan gratis | Key en [console.groq.com](https://console.groq.com/keys) |
| `gemini` | Plan gratis | Key en [aistudio.google.com](https://aistudio.google.com/apikey) |
| `openai` | De pago | Key de OpenAI |
| `anthropic` | De pago | Key de Anthropic |

Para los de nube:

```bash
arca login openrouter            # pega tu key (se guarda en ~/.arca/config.json, solo tu usuario la lee)
arca modelos --gratis            # ve los modelos gratis
arca usar openrouter             # Arca elige uno gratis con herramientas
```

También puedes usar un proveedor solo una vez: `arca -p groq "resume este PDF: ~/Desktop/contrato.pdf"`.

**¿Qué modelo local?** Según tu RAM: 8 GB → `qwen3:4b` · 16 GB → `qwen3:8b` o `gemma3:12b` · 32 GB+ → `qwen3:30b`. Los modelos con buen soporte de herramientas (tool calling) funcionan mejor como agentes.

## Uso

```bash
arca                                   # chat
arca "pon en mi calendario dentista el jueves a las 5"
arca -y "..."                          # sin pedir permiso (cuidado)
```

Dentro del chat: `/modelos`, `/modelo <id>`, `/proveedor <nombre>`, `/skills`, `/auto`, `/nuevo`, `/salir`.

### Chrome

Arca usa tu Chrome real. Para que pueda **leer, dar clic y escribir** en páginas, activa una vez:

**Chrome → Ver → Opciones para desarrolladores → Permitir JavaScript de eventos de Apple**

La primera vez macOS te pedirá permiso para que la Terminal controle Chrome y otras apps: acepta (se puede revisar en Configuración del Sistema → Privacidad y seguridad → Automatización).

## Skills

Una skill es una carpeta con un `SKILL.md`:

```markdown
---
name: reporte-semanal
description: Armar el reporte semanal. Usar cuando digan "reporte de la semana".
---

# Reporte semanal
1. Lee ~/Documents/notas/*.md de esta semana…
2. …
```

- Las del repo están en `skills/`. Las tuyas van en `~/.arca/skills/`.
- `arca skill-nueva <nombre>` crea una plantilla, o dile a Arca *"crea una skill para…"*.
- Son compatibles con las skills de Claude: copia la carpeta a `~/.arca/skills/` y listo.

Incluidas: `investigar`, `resumir-pestana`, `organizar-carpeta`, `borrador-correo`, `recordatorios`, `crear-skill`.

## Herramientas del agente

| Herramienta | Qué hace | Pide permiso |
|---|---|---|
| `leer_archivo`, `listar_carpeta` | Leer archivos y carpetas | No |
| `escribir_archivo` | Crear o editar archivos | Sí |
| `terminal` | Ejecutar comandos | Sí |
| `applescript` | Controlar la Mac y sus apps | Sí |
| `abrir` | Abrir apps, archivos o URLs | Sí |
| `notificar` | Notificación del sistema | No |
| `chrome_abrir`, `chrome_clic`, `chrome_escribir`, `chrome_js` | Manejar Chrome | Sí |
| `chrome_leer`, `chrome_pestanas` | Leer Chrome | No |
| `buscar_web`, `leer_web` | Buscar y leer internet | No |
| `usar_skill` | Cargar una skill | No |

Agregar una herramienta es escribir una función en `arca/tools.py` con el decorador `@tool`.

## Privacidad

Con `ollama` o `lmstudio`, nada sale de tu Mac (salvo que el agente use `buscar_web`/`leer_web`). Con un proveedor en la nube, tus mensajes y lo que lean las herramientas se mandan a ese proveedor. Arca no tiene telemetría.

## Desarrollo

```bash
python3 -m unittest discover tests     # pruebas (no necesitan modelo)
python3 -m arca                        # correr sin instalar
```

Licencia MIT.
