#!/usr/bin/env python3
"""Memoria e tempo al crescere del file, in streaming.

    python3 bench/memoria.py [--solo ALG] [KiB...]   (predefinito 16 64 256)
    python3 bench/memoria.py --prima DIR KiB... (la versione non in streaming,
                                                 estratta in DIR, per confronto)

Scrive doc/dati/memoria.json. Per ogni algoritmo, dimensione e verso, in un
processo nuovo: compressione da file a file, poi decompressione confrontata
pezzo per pezzo con l'originale. Riporta il picco di memoria residente del
processo Python e quello della VM (il piu' grande dei processi figli), con i
byte e i secondi. L'ingresso sono i sorgenti di Kairos (C, Python, Markdown)
concatenati in ordine: testo vero, non ripetuto.
"""
import json
import os
import pathlib
import resource
import subprocess
import sys
import tempfile
import time

RADICE = pathlib.Path(__file__).resolve().parent.parent
USCITA = RADICE / 'doc' / 'dati' / 'memoria.json'


def corpus(n, dest):
    file = sorted(p for p in (RADICE / 'kairos').rglob('*')
                  if p.is_file() and p.suffix in ('.c', '.h', '.py', '.md') and '.git' not in p.parts)
    scritti = 0
    with open(dest, 'wb') as o:
        while scritti < n:
            for f in file:
                b = f.read_bytes()[:n - scritti]
                o.write(b)
                scritti += len(b)
                if scritti >= n:
                    break


def _picchi():
    s = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    c = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return round(s / 1024, 1), round(c / 1024, 1)          # MiB


def figlio(radice, alg, verso, ingresso, uscita):
    sys.path.insert(0, radice)
    if alg == 'kgzip2':
        from kgzip2 import driver as D
    else:
        from klzma import driver as D
    t0 = time.perf_counter()
    if not hasattr(D, 'comprimi_flusso'):                    # versione precedente: tutto in memoria
        dati = pathlib.Path(ingresso).read_bytes()
        out, _ = D.comprimi(dati, timeout=36000)
        pathlib.Path(uscita).write_bytes(out)
    elif verso == 'comprimi':
        with open(ingresso, 'rb') as i, open(uscita, 'wb') as o:
            D.comprimi_flusso(i, o, timeout=36000)
    else:
        from comune.cli import _Confronto
        with open(ingresso, 'rb') as i, open(uscita, 'rb') as orig:
            c = _Confronto(orig)
            D.decomprimi_flusso(i, c, timeout=36000)
            c.fine()
    dt = time.perf_counter() - t0
    py, vm = _picchi()
    print(json.dumps({'secondi': round(dt, 1), 'python_mib': py, 'vm_mib': vm}))


def misura(radice, alg, verso, ingresso, uscita):
    env = dict(os.environ, KAIROS_HOME=str(RADICE / 'kairos'))
    r = subprocess.run([sys.executable, __file__, '--figlio', radice, alg, verso, ingresso, uscita],
                       capture_output=True, text=True, env=env)
    if r.returncode:                    # la versione precedente puo' non farcela: si registra perche'
        if not radice.startswith(str(RADICE)):
            return {'errore': r.stderr.strip().splitlines()[-1][-300:]}
        raise SystemExit(r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    arg = sys.argv[1:]
    if arg[:1] == ['--figlio']:
        return figlio(*arg[1:])
    radice, versione, algoritmi = str(RADICE), 'streaming', ('klzma', 'kgzip2')
    if arg[:1] == ['--prima']:
        radice, versione, arg = arg[1], 'prima', arg[2:]
    if arg[:1] == ['--solo']:
        algoritmi, arg = (arg[1],), arg[2:]
    kib = [int(k) for k in arg] or [16, 64, 256]
    risultati = json.loads(USCITA.read_text()) if USCITA.exists() else []
    with tempfile.TemporaryDirectory() as d:
        for k in kib:
            src, z = f'{d}/in{k}', f'{d}/out{k}'
            pathlib.Path(z).unlink(missing_ok=True)
            corpus(k * 1024, src)
            for alg in algoritmi:
                versi = ('comprimi',) if versione == 'prima' else ('comprimi', 'decomprimi')
                for verso in versi:
                    m = misura(radice, alg, verso, src if verso == 'comprimi' else z,
                               z if verso == 'comprimi' else src)
                    r = {'versione': versione, 'algoritmo': alg, 'verso': verso, 'kib': k,
                         'byte_compressi': pathlib.Path(z).stat().st_size if 'errore' not in m else None, **m}
                    print(r, flush=True)
                    risultati = [x for x in risultati if any(x[c] != r[c] for c in
                                                             ('versione', 'algoritmo', 'verso', 'kib'))]
                    risultati.append(r)
                    USCITA.write_text(json.dumps(risultati, indent=1))


if __name__ == '__main__':
    main()
