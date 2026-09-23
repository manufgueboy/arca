#!/usr/bin/env bash
# Instalador de Arca para macOS.  Uso:  ./install.sh
set -e
cd "$(dirname "$0")"

echo "⛵ Instalando Arca…"

if ! command -v python3 >/dev/null; then
  echo "Necesitas Python 3. Instálalo con: xcode-select --install   (o brew install python)"
  exit 1
fi

# 1) Arca como comando `arca` (sin dependencias externas)
if command -v pipx >/dev/null; then
  pipx install --force --editable .
else
  python3 -m pip install --user --editable . 2>/dev/null || python3 -m pip install --user --break-system-packages --editable .
  BIN="$(python3 -m site --user-base)/bin"
  case ":$PATH:" in *":$BIN:"*) ;; *)
    echo "export PATH=\"$BIN:\$PATH\"" >> ~/.zshrc
    echo "→ Agregué $BIN a tu PATH en ~/.zshrc (abre una terminal nueva)."
  esac
fi

# 2) Ollama para modelos locales (opcional)
if ! command -v ollama >/dev/null; then
  read -r -p "¿Instalar Ollama para correr modelos locales gratis? [S/n] " r
  if [[ ! "$r" =~ ^[nN] ]]; then
    if command -v brew >/dev/null; then brew install ollama; else
      echo "Descárgalo de https://ollama.com/download y vuelve a correr este script."; fi
  fi
fi

if command -v ollama >/dev/null; then
  (pgrep -x ollama >/dev/null || (ollama serve >/dev/null 2>&1 &)) ; sleep 2
  if [ -z "$(ollama list 2>/dev/null | tail -n +2)" ]; then
    read -r -p "¿Descargar un modelo local (qwen3:8b, ~5 GB, bueno con herramientas)? [S/n] " r
    [[ "$r" =~ ^[nN] ]] || ollama pull qwen3:8b
  fi
fi

echo
echo "✅ Listo. Abre una terminal nueva y escribe:  arca"
echo "   Revisa todo con:  arca doctor"
