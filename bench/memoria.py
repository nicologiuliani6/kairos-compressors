#!/usr/bin/env python3
"""Memoria e tempo dei binari al crescere del file.

    python3 bench/memoria.py [--solo ALG] [KiB...]   (predefinito 16 64 256)

Aggiunge a doc/dati/memoria.json le righe `nativo`: per ogni algoritmo e
dimensione, compressione da file a file e decompressione, con le opzioni
predefinite (blocchi da 64 KiB, un blocco per core in ogni esecuzione della VM).
Riporta il picco di memoria residente di tutto il comando (il binario e i
processi della VM), i byte e i secondi. Le righe `prima` (tutto il file in un
solo programma) e `streaming` (driver Python a gruppi, blocchi da 8 KiB) sono le
misure delle versioni precedenti. L'ingresso sono i sorgenti di Kairos
concatenati: testo vero, non ripetuto.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

RADICE = pathlib.Path(__file__).resolve().parent.parent
USCITA = RADICE / 'doc' / 'dati' / 'memoria.json'
BIN = RADICE / 'dist' / 'bin'


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


MISURA = """
import resource, subprocess, sys, time
t = time.perf_counter()
with open(sys.argv[2], 'rb') as i, open(sys.argv[3], 'wb') as o:
    r = subprocess.run(sys.argv[1].split(), stdin=i, stdout=o)
dt = time.perf_counter() - t
print(r.returncode, round(dt, 1), round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1))
"""


def misura(cmd, ingresso, uscita):
    r = subprocess.run([sys.executable, '-c', MISURA, cmd, ingresso, uscita], capture_output=True, text=True)
    codice, secondi, mib = r.stdout.split()
    if codice != '0':
        raise SystemExit(f'{cmd}: uscita {codice}')
    return float(secondi), float(mib)


def main():
    arg = sys.argv[1:]
    algoritmi = ('klzma', 'kgzip2')
    if arg[:1] == ['--solo']:
        algoritmi, arg = (arg[1],), arg[2:]
    kib = [int(k) for k in arg] or [16, 64, 256]
    risultati = json.loads(USCITA.read_text()) if USCITA.exists() else []
    with tempfile.TemporaryDirectory() as d:
        for k in kib:
            src, z, o = f'{d}/in{k}', f'{d}/out{k}', f'{d}/ritorno{k}'
            corpus(k * 1024, src)
            for alg in algoritmi:
                for verso in ('comprimi', 'decomprimi'):
                    if verso == 'comprimi':
                        s, m = misura(f'{BIN / alg} -c', src, z)
                    else:
                        s, m = misura(f'{BIN / alg} -dc', z, o)
                        assert pathlib.Path(o).read_bytes() == pathlib.Path(src).read_bytes()
                    r = {'versione': 'nativo', 'algoritmo': alg, 'verso': verso, 'kib': k,
                         'byte_compressi': pathlib.Path(z).stat().st_size, 'secondi': s, 'mib': m}
                    print(r, flush=True)
                    risultati = [x for x in risultati if any(x[c] != r[c] for c in
                                                             ('versione', 'algoritmo', 'verso', 'kib'))]
                    risultati.append(r)
                    USCITA.write_text(json.dumps(risultati, indent=1))


if __name__ == '__main__':
    main()
