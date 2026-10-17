#!/usr/bin/env python3
"""Suite di test della repo.

    python3 test/test_completo.py            # tutto (qualche minuto)
    python3 test/test_completo.py --rapido   # solo i casi piccoli

Per kgzip2 e klzma: l'uscita compressa coincide byte per byte con il modello
Python, la decompressione (uncall) ricostruisce l'originale, i file corrotti
o troncati vengono rifiutati prima della VM. Poi i comandi veri, in una
cartella temporanea, e la verifica degli ordinamenti delle rotazioni.
"""
import os
import pathlib
import random
import subprocess
import sys
import tempfile

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from comune import contenitore as C     # noqa: E402
from kgzip2 import driver as KG          # noqa: E402
from klzma import driver as KL           # noqa: E402

RAPIDO = '--rapido' in sys.argv
ESITI = {'ok': 0, 'errori': []}


def controlla(cond, cosa):
    if cond:
        ESITI['ok'] += 1
    else:
        ESITI['errori'].append(cosa)
        print(f'  ERRORE: {cosa}', flush=True)


def casi_limite():
    rnd = random.Random(7)
    return {
        'vuoto': b'', 'un_byte': b'q', 'due_byte': b'ab', 'banana': b'banana',
        'aaaa': b'aaaa', 'aaab': b'aaab', 'corse': b'x' * 3 + b'y' * 4 + b'z' * 5 + b'w' * 300 + b'q',
        'quasi_corse': bytes([7, 7, 7, 0, 7, 7, 7, 7, 9, 9, 9, 9, 9, 9, 9, 9, 9, 1]),
        'tutti_i_byte': bytes(range(256)),
        'periodico': (b'abcabc' * 60)[:333],
        'misto': bytes(rnd.choice([0, 0, 0, 1, 2, 255, 7]) for _ in range(500)),
        'casuale': bytes(rnd.randrange(256) for _ in range(300)),
        'due_blocchi': (b'Kairos reversibile ' * 600)[:10000],     # due blocchi da ~5 KB in par
    }


def prova_algoritmo(nome, D, dati, etichetta):
    out, _ = D.comprimi(dati, timeout=900)
    controlla(out == D.atteso(dati), f'{nome} {etichetta}: uscita diversa dal modello')
    ric, _ = D.decomprimi(out, timeout=900)
    controlla(ric == dati, f'{nome} {etichetta}: ritorno diverso dall\'originale')
    rnd = random.Random(len(dati))
    for _ in range(3):
        b = bytearray(out)
        p = rnd.randrange(len(b))
        b[p] ^= 1 << rnd.randrange(8)
        try:
            D.decomprimi(bytes(b), timeout=60)
            controlla(False, f'{nome} {etichetta}: file corrotto accettato')
        except C.FileNonValido:
            controlla(True, '')
    try:
        D.decomprimi(out[:len(out) // 2], timeout=60)
        controlla(False, f'{nome} {etichetta}: file troncato accettato')
    except C.FileNonValido:
        controlla(True, '')
    return len(out)


def prova_comandi(prog, est):
    py = sys.executable
    cmd = [py, str(RADICE / 'bin' / prog)]
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        f = d / 'prova.txt'
        dati = b'Una prova dei comandi veri, con qualche ripetizione: prova prova prova.\n' * 20
        f.write_bytes(dati)
        r = subprocess.run(cmd + [str(f)], capture_output=True)
        controlla(r.returncode == 0 and not f.exists() and (d / f'prova.txt{est}').exists(),
                  f'{prog}: compressione con rimozione dell\'ingresso')
        r = subprocess.run(cmd + ['-t', str(d / f'prova.txt{est}')], capture_output=True)
        controlla(r.returncode == 0, f'{prog}: -t su un file valido')
        r = subprocess.run(cmd + ['-d', str(d / f'prova.txt{est}')], capture_output=True)
        controlla(r.returncode == 0 and f.read_bytes() == dati and not (d / f'prova.txt{est}').exists(),
                  f'{prog}: decompressione')
        r = subprocess.run(cmd + ['-k', str(f)], capture_output=True)
        controlla(f.exists() and (d / f'prova.txt{est}').exists(), f'{prog}: -k tiene l\'ingresso')
        r = subprocess.run(cmd + ['-k', str(f)], capture_output=True)
        controlla(r.returncode != 0, f'{prog}: rifiuta di sovrascrivere senza -f')
        r = subprocess.run(cmd + ['-d', '-c', str(d / f'prova.txt{est}')], capture_output=True)
        controlla(r.stdout == dati, f'{prog}: -d -c su stdout')
        r = subprocess.run(cmd, input=dati, capture_output=True)
        r2 = subprocess.run(cmd + ['-d'], input=r.stdout, capture_output=True)
        controlla(r2.stdout == dati, f'{prog}: filtro stdin -> stdout')
        b = bytearray((d / f'prova.txt{est}').read_bytes())
        b[len(b) // 2] ^= 4
        (d / 'rotto.txt').with_suffix(est).write_bytes(b)
        r = subprocess.run(cmd + ['-t', str((d / 'rotto.txt').with_suffix(est))], capture_output=True)
        controlla(r.returncode != 0 and b'danneggiato' in r.stderr, f'{prog}: -t rifiuta un file corrotto')


if __name__ == '__main__':
    casi = casi_limite()
    if not RAPIDO:
        for f in sorted((RADICE / 'test' / 'corpus').iterdir()):
            casi[f.name] = f.read_bytes()
    for nome, D in (('kgzip2', KG), ('klzma', KL)):
        print(f'{nome}:', flush=True)
        for etichetta, dati in casi.items():
            n = prova_algoritmo(nome, D, dati, etichetta)
            print(f'  {etichetta:18s} {len(dati):6d} -> {n:6d} byte', flush=True)
    print('comandi:', flush=True)
    prova_comandi('kgzip2', '.kgz')
    prova_comandi('klzma', '.klz')
    print('ordinamenti delle rotazioni:', flush=True)
    r = subprocess.run([sys.executable, str(RADICE / 'kgzip2' / 'ordinamenti.py'), 'verifica',
                        '10' if RAPIDO else '30', '20'], capture_output=True, text=True)
    controlla(r.returncode == 0 and 'errori: 0' in r.stdout, 'ordinamenti: discordanza col riferimento')
    print(f'\n{ESITI["ok"]} controlli superati, {len(ESITI["errori"])} falliti')
    sys.exit(1 if ESITI['errori'] else 0)
