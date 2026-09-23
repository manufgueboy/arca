#!/bin/bash
# Instalador de Arca para macOS. Una sola línea en la Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/manufgueboy/arca/main/install.sh | bash
#
# Instala todo lo necesario sin preguntar nada técnico:
#   1. Python de Apple (si falta, abre el instalador oficial de Apple y espera).
#   2. Arca en ~/.arca/app y el comando `arca`.
#   3. Ollama (el motor gratuito para modelos locales).
#   4. La app "Arca" en Aplicaciones y la abre. El modelo se elige y descarga desde ahí, con un botón.
set -e

REPO="manufgueboy/arca"
APP_DIR="$HOME/.arca/app"
BIN="$HOME/.local/bin"
OLLAMA_ZIP="https://ollama.com/download/Ollama-darwin.zip"

negrita() { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok()      { printf "  \033[32m✓\033[0m %s\n" "$1"; }

if [ "$(uname)" != "Darwin" ]; then
  echo "Este instalador es para macOS. En Linux: clona el repo y usa bin/arca (necesitas Python 3.9+)."
  exit 1
fi

negrita "⛵ Instalando Arca"

# ── 1. Python (viene con las Command Line Tools de Apple) ─────────────────
if ! xcode-select -p >/dev/null 2>&1; then
  negrita "Hace falta un componente gratuito de Apple (Command Line Tools)."
  echo "  Se abrirá una ventana: dale a «Instalar» y acepta. Tarda unos minutos."
  echo "  No cierres esta ventana: sigo solo cuando termine."
  xcode-select --install >/dev/null 2>&1 || true
  for _ in $(seq 1 360); do
    xcode-select -p >/dev/null 2>&1 && break
    sleep 10
  done
fi
if ! /usr/bin/env python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  echo "No encontré Python 3.9 o más nuevo. Termina de instalar las Command Line Tools y vuelve a correr esta línea."
  exit 1
fi
ok "Python $(python3 -c 'import platform; print(platform.python_version())')"

# ── 2. Arca ───────────────────────────────────────────────────────────────
ORIGEN=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/arca/agent.py" ]; then
  ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # corriendo desde un repo clonado
fi
mkdir -p "$HOME/.arca" "$BIN"
if [ -n "$ORIGEN" ]; then
  RAIZ="$ORIGEN"
  ok "Usando Arca desde $ORIGEN"
else
  TMP="$(mktemp -d)"
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar xz -C "$TMP"
  rm -rf "$APP_DIR"
  mv "$TMP"/*/ "$APP_DIR"
  rm -rf "$TMP"
  RAIZ="$APP_DIR"
  ok "Arca descargada en $APP_DIR"
fi
chmod +x "$RAIZ/bin/arca"
ln -sf "$RAIZ/bin/arca" "$BIN/arca"
if ! grep -qs "$BIN" "$HOME/.zshrc"; then
  echo "export PATH=\"$BIN:\$PATH\"" >> "$HOME/.zshrc"
fi
ok "Comando arca"

# ── 3. Ollama (motor de modelos locales, gratis) ───────────────────────────
if [ -d /Applications/Ollama.app ] || [ -d "$HOME/Applications/Ollama.app" ] || command -v ollama >/dev/null 2>&1; then
  ok "Ollama ya estaba instalado"
else
  echo "  Descargando Ollama (motor gratuito para correr la IA en tu Mac)…"
  DEST_OLLAMA=/Applications
  [ -w /Applications ] || { DEST_OLLAMA="$HOME/Applications"; mkdir -p "$DEST_OLLAMA"; }
  curl -fL --progress-bar -o "$HOME/.arca/Ollama-darwin.zip" "$OLLAMA_ZIP"
  ditto -x -k "$HOME/.arca/Ollama-darwin.zip" "$DEST_OLLAMA"
  rm -f "$HOME/.arca/Ollama-darwin.zip"
  ok "Ollama instalado en $DEST_OLLAMA"
fi
open -g -a Ollama >/dev/null 2>&1 || true

# ── 4. App "Arca" (doble clic → se abre el chat en el navegador) ───────────
DEST_APP="${ARCA_APPS_DIR:-/Applications}"
[ -w "$DEST_APP" ] || { DEST_APP="$HOME/Applications"; mkdir -p "$DEST_APP"; }
rm -rf "$DEST_APP/Arca.app"
osacompile -o "$DEST_APP/Arca.app" -e "do shell script \"export PATH=/opt/homebrew/bin:/usr/local/bin:\$PATH; cd ~; nohup '$BIN/arca' web > '$HOME/.arca/web.log' 2>&1 &\"" >/dev/null 2>&1
if [ -f "$RAIZ/assets/Arca.icns" ]; then
  RES="$DEST_APP/Arca.app/Contents/Resources"
  cp "$RAIZ/assets/Arca.icns" "$RES/applet.icns"
  rm -f "$RES/Assets.car"                                   # macOS nuevo usa este ícono genérico si existe
  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$DEST_APP/Arca.app/Contents/Info.plist" >/dev/null 2>&1 || true
fi
/usr/libexec/PlistBuddy -c "Set :CFBundleName Arca" "$DEST_APP/Arca.app/Contents/Info.plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Arca controla apps de tu Mac (Chrome, Recordatorios, Mail…) solo cuando tú se lo pides.'" \
  "$DEST_APP/Arca.app/Contents/Info.plist" >/dev/null 2>&1 || true
codesign --force --deep -s - "$DEST_APP/Arca.app" >/dev/null 2>&1 || true   # firma local tras modificarla
touch "$DEST_APP/Arca.app"
ok "App Arca en $DEST_APP"

negrita "✅ ¡Listo! Abriendo Arca…"
echo "  La próxima vez ábrela desde Aplicaciones, Launchpad o Spotlight (⌘ + espacio y escribe «Arca»)."
echo "  Ya puedes cerrar esta ventana."
[ -n "${ARCA_NO_ABRIR:-}" ] || open "$DEST_APP/Arca.app"
