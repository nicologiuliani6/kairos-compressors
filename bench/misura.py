#!/usr/bin/env python3
"""Confronto di kgzip2 e klzma con bzip2, xz e LZMA puro.

    python3 bench/misura.py [FILE...]      (predefinito: test/corpus/*)

Scrive bench/risultati.md e bench/risultati.json. Per ogni file e algoritmo:
dimensione compressa, uguaglianza con il modello Python, ritorno identico,
tempi di frontend e di VM in compressione e in decompressione.
"""
import bz2
import json
import lzma
import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from kgzip2 import driver as KG     # noqa: E402
from klzma import driver as KL      # noqa: E402

RAW = [{'id': lzma.FILTER_LZMA1, 'preset': 9 | lzma.PRESET_EXTREME}]
file = [pathlib.Path(f) for f in sys.argv[1:]] or sorted((RADICE / 'test' / 'corpus').iterdir())
risultati = []
for f in file:
    dati = f.read_bytes()
    r = {'file': f.name, 'byte': len(dati), 'bzip2': len(bz2.compress(dati, 9)),
         'xz': len(lzma.compress(dati, preset=9 | lzma.PRESET_EXTREME)),
         'lzma_raw': len(lzma.compress(dati, format=lzma.FORMAT_RAW, filters=RAW))}
    for nome, D in (('kgzip2', KG), ('klzma', KL)):
        out, (tf1, tv1) = D.comprimi(dati, timeout=3600)
        ric, (tf2, tv2) = D.decomprimi(out, timeout=3600)
        r[nome] = {'byte': len(out), 'modello': out == D.atteso(dati), 'ritorno': ric == dati,
                   'comprimi': [round(tf1, 2), round(tv1, 2)], 'uncall': [round(tf2, 2), round(tv2, 2)]}
    risultati.append(r)
    print(f"{f.name:16s} {len(dati):6d}  bzip2 {r['bzip2']:5d}  xz {r['xz']:5d}  lzma {r['lzma_raw']:5d}"
          f"  kgzip2 {r['kgzip2']['byte']:5d} ({r['kgzip2']['comprimi'][1]:5.1f} s)"
          f"  klzma {r['klzma']['byte']:5d} ({r['klzma']['comprimi'][1]:5.1f} s)", flush=True)

(RADICE / 'bench' / 'risultati.json').write_text(json.dumps(risultati, indent=1))
L = ['| file | byte | bzip2 -9 | xz -9e | LZMA | kgzip2 | klzma | kgzip2 s (c/u) | klzma s (c/u) | ok |',
     '|---|---|---|---|---|---|---|---|---|---|']
for r in risultati:
    ok = all(r[a]['modello'] and r[a]['ritorno'] for a in ('kgzip2', 'klzma'))
    L.append(f"| {r['file']} | {r['byte']} | {r['bzip2']} | {r['xz']} | {r['lzma_raw']} | {r['kgzip2']['byte']} "
             f"| {r['klzma']['byte']} | {r['kgzip2']['comprimi'][1]} / {r['kgzip2']['uncall'][1]} "
             f"| {r['klzma']['comprimi'][1]} / {r['klzma']['uncall'][1]} | {'sì' if ok else 'NO'} |")
(RADICE / 'bench' / 'risultati.md').write_text('\n'.join(L) + '\n')
print('\n'.join(L))
