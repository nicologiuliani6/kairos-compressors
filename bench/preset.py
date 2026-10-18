#!/usr/bin/env python3
"""Byte prodotti da ogni preset di klzma e da ogni livello di kgzip2.

    python3 bench/preset.py [KiB]      (predefinito 256)   -> doc/dati/preset.json

Sui sorgenti di Kairos concatenati (testo vero), con i modelli Python, che
producono gli stessi byte dei binari. Accanto, bzip2 -9, xz -9e e LZMA puro.
"""
import bz2
import json
import lzma
import pathlib
import sys
import tempfile

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / 'bench'))
import memoria                      # noqa: E402
from kgzip2 import driver as KG     # noqa: E402
from klzma import driver as KL      # noqa: E402

KLZMA = {0: (8, 4), 1: (8, 8), 2: (16, 8), 3: (16, 16), 4: (32, 16), 5: (32, 32), 6: (64, 32),
         7: (64, 64), 8: (128, 64), 9: (256, 128)}
KGZIP2 = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 40, 8: 48, 9: 64}

kib = int(sys.argv[1]) if len(sys.argv) > 1 else 256
with tempfile.NamedTemporaryFile() as f:
    memoria.corpus(kib * 1024, f.name)
    dati = pathlib.Path(f.name).read_bytes()
raw = [{'id': lzma.FILTER_LZMA1, 'preset': 9 | lzma.PRESET_EXTREME}]
out = {'kib': kib, 'bzip2': len(bz2.compress(dati, 9)),
       'xz': len(lzma.compress(dati, preset=9 | lzma.PRESET_EXTREME)),
       'lzma_raw': len(lzma.compress(dati, format=lzma.FORMAT_RAW, filters=raw)), 'klzma': {}, 'kgzip2': {}}
for p, (b, D) in KLZMA.items():
    out['klzma'][str(p)] = {'blocco_kib': b, 'D': D, 'byte': len(KL.atteso(dati, b * 1024, D))}
    print('klzma', p, out['klzma'][str(p)], flush=True)
for p in (6, 9):
    b, D = KLZMA[p]
    out['klzma'][f'{p}e'] = {'blocco_kib': b, 'D': min(2 * D, 256), 'byte': len(KL.atteso(dati, b * 1024, min(2 * D, 256)))}
    print('klzma', f'{p}e', out['klzma'][f'{p}e'], flush=True)
for p, b in KGZIP2.items():
    out['kgzip2'][str(p)] = {'blocco_kib': b, 'byte': len(KG.atteso(dati, b * 1024))}
    print('kgzip2', p, out['kgzip2'][str(p)], flush=True)
(RADICE / 'doc' / 'dati' / 'preset.json').write_text(json.dumps(out, indent=1))
