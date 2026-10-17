#!/usr/bin/env python3
"""Blocchi come rami di un par contro blocchi in sequenza (tempi della sola VM).

    python3 bench/concorrenza.py        -> doc/dati/concorrenza.json
"""
import json
import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from kgzip2 import driver as KG     # noqa: E402
from klzma import driver as KL      # noqa: E402

casi = [('kgzip2', KG, RADICE / 'test/corpus/tesi8k.tex', 4096),
        ('kgzip2', KG, RADICE / 'test/corpus/tesi8k.tex', 2048),
        ('klzma', KL, RADICE / 'bench/dati/tesi20k.tex', 8192),
        ('klzma', KL, RADICE / 'bench/dati/tesi20k.tex', 20000)]
out = []
for nome, D, f, dim in casi:
    dati = f.read_bytes()
    r = {'algoritmo': nome, 'file': f.name, 'byte': len(dati), 'blocco': dim,
         'blocchi': len(D.dividi(dati, dim))}
    for modo in ('par', 'seq'):
        if r['blocchi'] == 1 and modo == 'seq':
            continue
        D.SEQUENZIALE = modo == 'seq'
        z, (tf1, tv1) = D.comprimi(dati, dim, timeout=3600)
        ric, (tf2, tv2) = D.decomprimi(z, timeout=3600)
        assert ric == dati
        r[modo] = {'byte': len(z), 'comprimi': round(tv1, 2), 'uncall': round(tv2, 2)}
    D.SEQUENZIALE = False
    out.append(r)
    print(r, flush=True)
(RADICE / 'doc' / 'dati' / 'concorrenza.json').write_text(json.dumps(out, indent=1))
