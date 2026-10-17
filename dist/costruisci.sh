#!/usr/bin/env bash
# Costruisce gli eseguibili autonomi dist/bin/kgzip2 e dist/bin/klzma.
#
# Ogni eseguibile e' un file unico (PyInstaller --onefile) che contiene:
# l'interprete Python, il frontend di Kairos (lexer, parser, bytecode), PLY,
# la VM di Kairos (libvm.so, compilata per x86-64 generico) e la libreria
# Kairos dell'algoritmo. Sulla macchina di destinazione non serve altro.
#
#   KAIROS_HOME=/percorso/kairos dist/costruisci.sh     (predefinito: ./kairos)
set -euo pipefail
RADICE="$(cd "$(dirname "$0")/.." && pwd)"
KAIROS="${KAIROS_HOME:-$RADICE/kairos}"
LAVORO="$RADICE/dist/lavoro"
USCITA="$RADICE/dist/bin"
[ -f "$KAIROS/src/vm/Janus.c" ] || { echo "Kairos non trovato in $KAIROS (imposta KAIROS_HOME)"; exit 1; }
mkdir -p "$LAVORO/kairos/build" "$USCITA"

echo "== VM di Kairos, portabile (x86-64 generico)"
gcc -shared -fPIC -pthread -O3 -march=x86-64 -mtune=generic -flto -fomit-frame-pointer \
    -funroll-loops -DNDEBUG -Wno-stringop-truncation \
    -Wl,--version-script="$KAIROS/src/vm/libvm.map" -Wl,-O1 \
    -o "$LAVORO/kairos/build/libvm.so" "$KAIROS/src/vm/Janus.c" "$KAIROS/src/vm/Janus_dap.c" \
    -I"$KAIROS/src/vm"

echo "== ambiente Python"
[ -x "$RADICE/.venv/bin/python" ] || python3 -m venv "$RADICE/.venv"
"$RADICE/.venv/bin/pip" install -q ply pyinstaller

for prog in kgzip2 klzma; do
    echo "== $prog"
    "$RADICE/.venv/bin/pyinstaller" --onefile --noconfirm --log-level ERROR \
        --name "$prog" --distpath "$USCITA" \
        --workpath "$LAVORO/pyinstaller-$prog" --specpath "$LAVORO" \
        --paths "$RADICE" --paths "$KAIROS" \
        --collect-submodules src.frontend \
        --hidden-import ply.lex --hidden-import ply.yacc \
        --add-binary "$LAVORO/kairos/build/libvm.so:kairos/build" \
        --add-data "$RADICE/$prog/$prog.kairos:$prog" \
        "$RADICE/$prog/__main__.py"
done
ls -l "$USCITA"
