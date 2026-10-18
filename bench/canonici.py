#!/usr/bin/env python3
"""kgzip2 e klzma contro bzip2 e xz, sullo stesso testo.

    python3 bench/canonici.py [KiB]      (predefinito 256)   -> doc/dati/canonici.json

Sui sorgenti di Kairos concatenati (senza ripetizioni fino a 476 KiB). bzip2 e
xz si misurano qui (migliore di 5 esecuzioni, picco di memoria del processo);
per kgzip2 e klzma tempi e memoria vengono da doc/dati/memoria.json (righe
'nativo', make memoria) e i byte dei preset da doc/dati/preset.json, cosi' lo
script dura pochi secondi invece di sei minuti.
"""
import json
import pathlib
import resource
import shutil
import subprocess
import sys
import tempfile

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / 'bench'))
import memoria                      # noqa: E402

DATI = RADICE / 'doc' / 'dati'

MISURA = """
import resource, subprocess, sys, time
cmd, ing = sys.argv[1].split(), sys.argv[2]
migliore, n = None, 0
for _ in range(5):
    t = time.perf_counter()
    with open(ing, 'rb') as i:
        r = subprocess.run(cmd, stdin=i, stdout=subprocess.PIPE, check=True)
    dt = time.perf_counter() - t
    migliore = dt if migliore is None else min(migliore, dt)
    n = len(r.stdout)
print(n, migliore, resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024)
"""


def misura(cmd, ing):
    """(byte in uscita, secondi, MiB) in un processo a parte: ru_maxrss dei figli e' il massimo."""
    out = subprocess.run([sys.executable, '-c', MISURA, cmd, str(ing)], capture_output=True, text=True, check=True)
    n, s, m = out.stdout.split()
    return int(n), float(s), float(m)


def versione(cmd):
    r = subprocess.run([cmd, '--version'], capture_output=True, text=True)
    return (r.stdout or r.stderr).splitlines()[0].strip()


kib = int(sys.argv[1]) if len(sys.argv) > 1 else 256
n = kib * 1024
risultati = {'kib': kib, 'versioni': {c: versione(c) for c in ('bzip2', 'xz')}, 'righe': []}
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    sorg = d / 'corpus'
    memoria.corpus(n, sorg)
    for nome, cmd, dec, est in (('bzip2 -9', 'bzip2 -9 -c', 'bzip2 -dc', 'bz2'),
                                ('xz -6', 'xz -6 -c', 'xz -dc', 'xz'),
                                ('xz -9e', 'xz -9e -c', 'xz -dc', 'xz9')):
        byte, sc, mc = misura(cmd, sorg)
        z = d / f'z.{est}'
        with open(sorg, 'rb') as i, open(z, 'wb') as o:
            subprocess.run(cmd.split(), stdin=i, stdout=o, check=True)
        _, sd, md = misura(dec, z)
        risultati['righe'].append(dict(nome=nome, byte=byte, comprimi=sc, decomprimi=sd, mib=max(mc, md)))

M = json.loads((DATI / 'memoria.json').read_text())
P = json.loads((DATI / 'preset.json').read_text())
assert P['kib'] == kib, 'preset.json misura un altro ingresso: rilancia bench/preset.py'
for alg, opz, byte in (('kgzip2', '-9', P['kgzip2']['9']['byte']), ('klzma', '-6', P['klzma']['6']['byte'])):
    r = {x['verso']: x for x in M if x['versione'] == 'nativo' and x['algoritmo'] == alg and x['kib'] == kib}
    assert r['comprimi']['byte_compressi'] == byte, f'{alg}: memoria.json e preset.json non coincidono'
    risultati['righe'].append(dict(nome=f'{alg} {opz}', byte=byte, comprimi=r['comprimi']['secondi'],
                                   decomprimi=r['decomprimi']['secondi'],
                                   mib=max(r['comprimi']['mib'], r['decomprimi']['mib'])))
risultati['righe'].append(dict(nome='klzma -9e', byte=P['klzma']['9e']['byte']))
risultati['binari'] = {c: (shutil.which(c) and pathlib.Path(shutil.which(c)).stat().st_size) for c in ('bzip2', 'xz')}
risultati['binari'].update({c: (RADICE / 'dist' / 'bin' / c).stat().st_size
                            for c in ('kgzip2', 'klzma') if (RADICE / 'dist' / 'bin' / c).exists()})
(DATI / 'canonici.json').write_text(json.dumps(risultati, indent=1))

print(f"{kib} KiB di sorgenti di Kairos; {risultati['versioni']['bzip2']}; {risultati['versioni']['xz']}")
print('| | byte | % | comprimi (s) | decomprimi (s) | MiB |')
print('|---|---|---|---|---|---|')
for r in risultati['righe']:
    t = (f"{r['comprimi']:.3f} | {r['decomprimi']:.3f} | {r['mib']:.0f}" if 'comprimi' in r else ' | | ')
    print(f"| {r['nome']} | {r['byte']} | {100 * r['byte'] / n:.1f} | {t} |")
