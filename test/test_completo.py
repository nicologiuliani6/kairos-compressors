#!/usr/bin/env python3
"""Suite di test della repo.

    python3 test/test_completo.py            # tutto (qualche minuto)
    python3 test/test_completo.py --rapido   # solo i casi piccoli

Per kgzip2 e klzma: l'uscita compressa coincide byte per byte con il modello
Python, la decompressione (uncall) ricostruisce l'originale, i file corrotti
o troncati vengono rifiutati prima della VM. Poi lo streaming (piu' frame,
gruppi diversi, flussi concatenati, dati in coda, ogni troncamento e ogni byte
alterato di un file), l'uncall senza CRC su file alterati (non deve mai girare
all'infinito), i comandi veri in una cartella temporanea e la verifica degli
ordinamenti delle rotazioni.
"""
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import time

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from comune import contenitore as C     # noqa: E402
from comune import kvm                  # noqa: E402
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
        'due_blocchi': (b'Kairos reversibile ' * 600)[:10000],     # 8192 + 1808 byte, in un par
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


def rifiuta(D, buf, cosa, **kw):
    try:
        D.decomprimi(buf, timeout=60, **kw)
        controlla(False, cosa)
    except C.FileNonValido:
        controlla(True, '')


def prova_flusso(nome, D):
    """Piu' frame in piu' esecuzioni della VM, con l'uscita indipendente dal gruppo."""
    dati = (b'Kairos va avanti e indietro, call e uncall. ' * 120)[:4500]
    a, _ = D.comprimi(dati, 1024, timeout=900, gruppo=2)
    controlla(a == D.atteso(dati, 1024), f'{nome} flusso: uscita diversa dal modello')
    b, _ = D.comprimi(dati, 1024, timeout=900, gruppo=1)
    controlla(a == b, f'{nome} flusso: l\'uscita dipende dal gruppo')
    for g in (1, 3, 8):
        ric, _ = D.decomprimi(a, timeout=900, gruppo=g)
        controlla(ric == dati, f'{nome} flusso: ritorno diverso con gruppo {g}')
    c, _ = D.comprimi(b'seconda parte', timeout=900)
    ric, _ = D.decomprimi(a + c + a, timeout=900, gruppo=4)
    controlla(ric == dati + b'seconda parte' + dati, f'{nome} flusso: flussi concatenati')
    for coda in (b'x', bytes(7), D.MAGIA[:2], D.MAGIA):
        rifiuta(D, a + coda, f'{nome} flusso: dati in coda accettati ({coda!r})')
    # 25 blocchi in una sola esecuzione della VM: i nomi per blocco non si sovrappongono
    # (senza separatore n1 del blocco 0 e n del blocco 10 sarebbero entrambi n10)
    molti = (b'Kairos: un programma, due versi. ' * 60)[:25 * 64]
    m, _ = D.comprimi(molti, 64, timeout=900, gruppo=25)
    controlla(m == D.atteso(molti, 64), f'{nome} flusso: 25 blocchi in un par, uscita diversa dal modello')
    controlla(D.decomprimi(m, timeout=900, gruppo=25)[0] == molti, f'{nome} flusso: 25 blocchi in un par, ritorno')
    # un file di soli frame memorizzati: ogni troncamento e ogni byte alterato
    # vanno rifiutati, e senza la VM la prova costa poco
    rnd = random.Random(11)
    casuale = bytes(rnd.randrange(256) for _ in range(250))
    z, _ = D.comprimi(casuale, 64, timeout=900)
    controlla(z == D.atteso(casuale, 64), f'{nome} memorizzati: uscita diversa dal modello')
    controlla(D.decomprimi(z)[0] == casuale, f'{nome} memorizzati: ritorno')
    tronchi = alterati = 0
    for L in range(len(z)):
        try:
            D.decomprimi(z[:L])
        except C.FileNonValido:
            tronchi += 1
    controlla(tronchi == len(z), f'{nome} memorizzati: {len(z) - tronchi} troncamenti accettati')
    for p in range(len(z)):
        bb = bytearray(z)
        bb[p] ^= 1 << rnd.randrange(8)
        try:
            D.decomprimi(bytes(bb))
        except C.FileNonValido:
            alterati += 1
    controlla(alterati == len(z), f'{nome} memorizzati: {len(z) - alterati} byte alterati accettati')
    return len(a), len(z)


def prova_asserzioni(nome, D):
    """Senza il CRC un file alterato arriva all'uncall: la VM non deve mai girare
    all'infinito. O si ferma su un proprio controllo, o termina (e allora il CRC
    dei dati, che resta, si accorge dell'errore)."""
    blocco = (RADICE / 'test' / 'corpus' / 'tesi8k.tex').read_bytes()[:512]
    (r,), _, _ = D.comprimi_gruppo([blocco], timeout=600)
    conti, bits = r
    t0 = time.perf_counter()
    D.decomprimi_gruppo([(len(blocco), conti, bits)], timeout=600)
    limite = max(10 * (time.perf_counter() - t0), 5.0)
    rnd = random.Random(3)
    fermati = 0
    for _ in range(20):
        b = list(bits)
        b[rnd.randrange(len(b))] ^= 1
        try:
            out, _, _ = D.decomprimi_gruppo([(len(blocco), conti, b)], timeout=limite)
            controlla(True, '')
        except kvm.ErroreKairos as e:
            controlla('non ha terminato' not in str(e), f'{nome}: un file alterato fa girare l\'uncall all\'infinito')
            fermati += 1
    return fermati


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
        filtro = r.stdout
        r2 = subprocess.run(cmd + ['-d'], input=filtro, capture_output=True)
        controlla(r2.stdout == dati, f'{prog}: filtro stdin -> stdout')
        b = bytearray((d / f'prova.txt{est}').read_bytes())
        b[len(b) // 2] ^= 4
        (d / 'rotto.txt').with_suffix(est).write_bytes(b)
        r = subprocess.run(cmd + ['-t', str((d / 'rotto.txt').with_suffix(est))], capture_output=True)
        controlla(r.returncode != 0 and b'danneggiato' in r.stderr, f'{prog}: -t rifiuta un file corrotto')
        (d / 'mezzo.txt').with_suffix(est).write_bytes(b[:len(b) // 2])
        r = subprocess.run(cmd + ['-t', str((d / 'mezzo.txt').with_suffix(est))], capture_output=True)
        controlla(r.returncode != 0 and b'troncato' in r.stderr, f'{prog}: -t rifiuta un file troncato')
        # streaming vero: piu' blocchi da una pipe, gruppi diversi, flussi concatenati
        D = KG if prog == 'kgzip2' else KL
        lungo = (b'Una riga di prova per lo streaming, con un numero: %d\n' % 7) * 60
        r1 = subprocess.run(cmd + ['-1', '-T', '1'], input=lungo, capture_output=True)
        r3 = subprocess.run(cmd + ['-1', '-T', '3', '-v'], input=lungo, capture_output=True)
        controlla(r1.returncode == 0 and r1.stdout == r3.stdout == D.atteso(lungo, 1024),
                  f'{prog}: pipe a piu\' blocchi, uguale al modello con -T 1 e -T 3')
        controlla(b'blocchi' in r3.stderr, f'{prog}: -v riporta i blocchi')
        r = subprocess.run(cmd + ['-d', '-T', '2'], input=r1.stdout + filtro, capture_output=True)
        controlla(r.returncode == 0 and r.stdout == lungo + dati, f'{prog}: flussi concatenati da una pipe')
        g = d / 'grande.txt'
        g.write_bytes(lungo)
        r = subprocess.run(cmd + ['-1', '-v', str(g)], capture_output=True)
        controlla(r.returncode == 0 and not g.exists() and b'verificato' in r.stderr
                  and (d / f'grande.txt{est}').read_bytes() == r1.stdout,
                  f'{prog}: file a piu\' blocchi, verificato prima di rimuovere l\'ingresso')
        controlla(not list(d.glob('*.tmp')), f'{prog}: nessun file temporaneo rimasto')
        # --salta-crc: il file alterato arriva all'uncall, e lo ferma la VM o il CRC dei dati
        r = subprocess.run(cmd + ['-t', '--salta-crc', str((d / 'rotto.txt').with_suffix(est))],
                           capture_output=True)
        controlla(r.returncode != 0 and (b'VM' in r.stderr or b'CRC dei dati' in r.stderr),
                  f'{prog}: --salta-crc, il file alterato non viene accettato')


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
        n1, n2 = prova_flusso(nome, D)
        print(f'  {"streaming":18s} 5 frame -> {n1} byte, memorizzati -> {n2} byte', flush=True)
        f = prova_asserzioni(nome, D)
        print(f'  {"senza CRC":18s} 20 bit invertiti: {f} fermati dalla VM, nessuno senza fine', flush=True)
    print('comandi:', flush=True)
    prova_comandi('kgzip2', '.kgz')
    prova_comandi('klzma', '.klz')
    print('ordinamenti delle rotazioni:', flush=True)
    r = subprocess.run([sys.executable, str(RADICE / 'kgzip2' / 'ordinamenti.py'), 'verifica',
                        '10' if RAPIDO else '30', '20'], capture_output=True, text=True)
    controlla(r.returncode == 0 and 'errori: 0' in r.stdout, 'ordinamenti: discordanza col riferimento')
    print(f'\n{ESITI["ok"]} controlli superati, {len(ESITI["errori"])} falliti')
    sys.exit(1 if ESITI['errori'] else 0)
