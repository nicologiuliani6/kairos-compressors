#!/usr/bin/env python3
"""Confronto di kgzip2 e klzma con bzip2, xz e LZMA puro, con i binari nativi.

    python3 bench/misura.py [FILE...]      (predefinito: test/corpus/*)

Scrive bench/risultati.md e bench/risultati.json. Per ogni file e algoritmo:
dimensione compressa con le opzioni predefinite (kgzip2 -9, klzma -6),
uguaglianza con il modello Python, ritorno identico, secondi del comando in
compressione e in decompressione (dall'avvio alla fine del processo).
"""
import bz2
import json
import lzma
import pathlib
import subprocess
import sys
import time

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from kgzip2 import driver as KG     # noqa: E402
from klzma import driver as KL      # noqa: E402

BIN = RADICE / 'dist' / 'bin'
ATTESO = {'kgzip2': lambda d: KG.atteso(d, 64 * 1024), 'klzma': lambda d: KL.atteso(d, 64 * 1024, 32)}
RAW = [{'id': lzma.FILTER_LZMA1, 'preset': 9 | lzma.PRESET_EXTREME}]


def cronometra(cmd, dati):
    t0 = time.perf_counter()
    r = subprocess.run(cmd, input=dati, capture_output=True, check=True)
    return r.stdout, round(time.perf_counter() - t0, 2)


file = [pathlib.Path(f) for f in sys.argv[1:]] or sorted((RADICE / 'test' / 'corpus').iterdir())
risultati = []
for f in file:
    dati = f.read_bytes()
    r = {'file': f.name, 'byte': len(dati), 'bzip2': len(bz2.compress(dati, 9)),
         'xz': len(lzma.compress(dati, preset=9 | lzma.PRESET_EXTREME)),
         'lzma_raw': len(lzma.compress(dati, format=lzma.FORMAT_RAW, filters=RAW))}
    for nome in ('kgzip2', 'klzma'):
        z, tc = cronometra([str(BIN / nome), '-c'], dati)
        o, tu = cronometra([str(BIN / nome), '-dc'], z)
        r[nome] = {'byte': len(z), 'modello': z == ATTESO[nome](dati), 'ritorno': o == dati,
                   'comprimi': [0.0, tc], 'uncall': [0.0, tu]}
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
