#!/usr/bin/env python3
"""Suite di test della repo.

    python3 test/test_completo.py            # tutto (qualche minuto)
    python3 test/test_completo.py --rapido   # solo i casi piccoli

Per kgzip2 e klzma: l'uscita compressa coincide byte per byte con il modello
Python, la decompressione (uncall) ricostruisce l'originale, i file corrotti
o troncati vengono rifiutati prima della VM. Poi lo streaming (piu' frame,
gruppi diversi, flussi concatenati, dati in coda, ogni troncamento e ogni byte
alterato di un file), l'uncall senza CRC su file alterati (non deve mai girare
all'infinito). Poi i binari nativi (dist/bin): stesso bytecode del driver
Python, stessi byte del modello su tutti i casi, e le opzioni di bzip2 e xz in
una cartella temporanea. Infine la verifica degli ordinamenti delle rotazioni.
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


BIN = RADICE / 'dist' / 'bin'
PARAM = {'kgzip2': dict(dim=64 * 1024, extra=()), 'klzma': dict(dim=64 * 1024, extra=(32,))}


def esegui(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, **kw)


def atteso_bin(nome, D, dati, dim=None, extra=None):
    p = PARAM[nome]
    return D.atteso(dati, dim or p['dim'], *(extra if extra is not None else p['extra']))


def normalizza(righe):
    """Bytecode senza la colonna delle righe sorgente e senza il segnaposto."""
    return [r.split(None, 1)[1].strip() for r in righe if r.strip() and 'segnaposto_dati' not in r]


def prova_bytecode(nome, D, d):
    """Il main che genera il binario coincide con quello del driver Python."""
    from comune import contenitore as CC, kvm
    B = 4096 if nome == 'kgzip2' else 1024              # kgzip2 -1: 4 KiB; klzma: a scelta
    dati = (b'Kairos, avanti e indietro. ' * 400)[:2 * B]
    f = d / 'bc.txt'
    f.write_bytes(dati)
    dump = d / 'bc.dump'
    opz = ['-1'] if nome == 'kgzip2' else ['--block-size=1KiB']
    for k in ((1, 2) if len(os.sched_getaffinity(0)) >= 2 else (1,)):
        sorg = dati[:B * k]
        f.write_bytes(sorg)
        z = esegui([BIN / nome, *opz, '-T', str(k)] if nome == 'klzma' else [BIN / nome, *opz, '-c', f],
                   input=sorg if nome == 'klzma' else None, env=dict(os.environ, KC_BYTECODE=str(dump)))
        compresso = z.stdout
        c = dump.read_text().splitlines()
        blocchi = [sorg[q:q + B] for q in range(0, len(sorg), B)]
        if nome == 'kgzip2':
            py = kvm.con_dati(kvm.compila(D.programma([len(b) for b in blocchi], 'call')), D._dati_byte(blocchi))
        else:
            istr = [f'PUSHEQ b_{i}[{q}] {v}' for i, b in enumerate(blocchi) for q, v in enumerate(b) if v]
            py = kvm.con_dati(kvm.compila(D.programma([len(b) for b in blocchi], 32, 'call')), istr)
        controlla(normalizza(c) == normalizza(py), f'{nome}: bytecode di compressione diverso dal driver ({k} blocchi)')
        esegui([BIN / nome, '-d', '-c'], input=compresso, env=dict(os.environ, KC_BYTECODE=str(dump)))
        c = dump.read_text().splitlines()
        import io
        lt = CC.Lettore(io.BytesIO(compresso), D.MAGIA, len(D.PARAMETRI), D.NCONT)
        lt.inizia()
        frame = []
        while True:
            fr = lt.frame()
            frame.append((fr.n, fr.conti, fr.carico))
            if fr.ultimo:
                break
        if nome == 'kgzip2':
            py = kvm.con_dati(kvm.compila(D.programma([x[0] for x in frame], 'uncall')), D._dati_bit(frame))
        else:
            istr = []
            for i, (n, (x, nb), bits) in enumerate(frame):
                for b in bits:
                    if b:
                        istr.append(f'PUSHEQ t_{i} 1')
                    istr.append(f'PUSH t_{i} bitst_{i}')
                istr += [f'PUSHEQ x_{i} {x}', f'PUSHEQ nb_{i} {len(bits)}']
            py = kvm.con_dati(kvm.compila(D.programma([x[0] for x in frame], 32, 'uncall')), istr)
        controlla(normalizza(c) == normalizza(py), f'{nome}: bytecode di decompressione diverso dal driver ({k} blocchi)')


def prova_binario(nome, D, dati, etichetta):
    """Il binario produce gli stessi byte del modello e il ritorno e' esatto."""
    z = esegui([BIN / nome, '-c'], input=dati)
    controlla(z.returncode == 0 and z.stdout == atteso_bin(nome, D, dati),
              f'{nome} {etichetta}: il binario non coincide con il modello')
    r = esegui([BIN / nome, '-d', '-c'], input=z.stdout)
    controlla(r.returncode == 0 and r.stdout == dati, f'{nome} {etichetta}: ritorno del binario diverso')
    return len(z.stdout)


def prova_comandi(nome, D):
    est = '.kgz' if nome == 'kgzip2' else '.klz'
    corrotto = 2 if nome == 'kgzip2' else 1          # codici d'uscita di bzip2 e di xz
    cmd = [BIN / nome]
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        prova_bytecode(nome, D, d)
        f = d / 'prova.txt'
        dati = b'Una prova dei comandi veri, con qualche ripetizione: prova prova prova.\n' * 20
        f.write_bytes(dati)
        z = d / f'prova.txt{est}'
        r = esegui(cmd + [f])
        controlla(r.returncode == 0 and not f.exists() and z.exists(), f'{nome}: compressione con rimozione dell\'ingresso')
        controlla(z.read_bytes() == atteso_bin(nome, D, dati), f'{nome}: file compresso diverso dal modello')
        r = esegui(cmd + ['-t', z])
        controlla(r.returncode == 0 and not r.stderr, f'{nome}: -t su un file valido')
        r = esegui(cmd + ['-tv', z])
        controlla(r.returncode == 0 and b'ok' in r.stderr, f'{nome}: -tv dice ok')
        r = esegui(cmd + ['-d', z])
        controlla(r.returncode == 0 and f.read_bytes() == dati and not z.exists(), f'{nome}: decompressione')
        r = esegui(cmd + ['-k', f])
        controlla(r.returncode == 0 and f.exists() and z.exists(), f'{nome}: -k tiene l\'ingresso')
        r = esegui(cmd + ['-k', f])
        controlla(r.returncode == 1 and b'esiste' in r.stderr, f'{nome}: rifiuta di sovrascrivere senza -f')
        r = esegui(cmd + ['-kf', f])
        controlla(r.returncode == 0, f'{nome}: -f sovrascrive')
        r = esegui(cmd + ['-dc', z])
        controlla(r.stdout == dati and z.exists(), f'{nome}: -dc su stdout tiene l\'ingresso')
        r = esegui(cmd, input=dati)
        filtro = r.stdout
        r2 = esegui(cmd + ['-d'], input=filtro)
        controlla(r.returncode == 0 and r2.stdout == dati, f'{nome}: filtro stdin -> stdout')
        r = esegui(cmd + ['-c', '-'], input=dati)
        controlla(r.stdout == filtro, f'{nome}: - vale stdin')
        vuoto = d / 'vuoto'
        vuoto.write_bytes(b'')
        r = esegui(cmd + ['-k', vuoto])
        controlla(r.returncode == 0 and esegui(cmd + ['-dc', d / f'vuoto{est}']).stdout == b'', f'{nome}: file vuoto')
        b = bytearray(z.read_bytes())
        b[len(b) // 2] ^= 4
        rotto = d / f'rotto{est}'
        rotto.write_bytes(b)
        r = esegui(cmd + ['-t', rotto])
        controlla(r.returncode == corrotto and b'danneggiato' in r.stderr, f'{nome}: -t rifiuta un file corrotto (codice {corrotto})')
        tronco = d / f'tronco{est}'
        tronco.write_bytes(bytes(b[:len(b) // 2]))
        r = esegui(cmd + ['-t', tronco])
        controlla(r.returncode == corrotto and b'troncato' in r.stderr, f'{nome}: -t rifiuta un file troncato')
        r = esegui(cmd + ['-d', rotto])
        controlla(r.returncode == corrotto and not (d / 'rotto').exists() and rotto.exists(),
                  f'{nome}: un file corrotto non lascia uscite parziali')
        r = esegui(cmd + ['-k', z])
        controlla(r.returncode != 0 and not (d / f'prova.txt{est}{est}').exists(), f'{nome}: non ricomprime un {est}')
        senza = d / 'senza_suffisso'
        senza.write_bytes(z.read_bytes())
        r = esegui(cmd + ['-dk', senza])
        if nome == 'kgzip2':
            controlla(r.returncode == 0 and (d / 'senza_suffisso.out').read_bytes() == dati,
                      'kgzip2: suffisso sconosciuto, uscita in .out come bzip2')
        else:
            controlla(r.returncode == 2 and not (d / 'senza_suffisso.out').exists(),
                      'klzma: suffisso sconosciuto, salto con avviso come xz')
        r = esegui(cmd + [d])
        controlla(r.returncode != 0, f'{nome}: una cartella non si comprime')
        r = esegui(cmd + [d / 'non_esiste'])
        controlla(r.returncode == 1, f'{nome}: file inesistente, codice 1')
        r = esegui(cmd + ['--bogus'])
        controlla(r.returncode == 1, f'{nome}: opzione sconosciuta, codice 1')
        for o in ('-h', '--help', '-V', '--version'):
            r = esegui(cmd + [o])
            controlla(r.returncode == 0 and r.stdout, f'{nome}: {o}')
        # streaming: piu' blocchi da una pipe, uscita indipendente dal numero di blocchi in parallelo
        lungo = (b'Una riga di prova per lo streaming, con un numero: %d\n' % 7) * 60
        if nome == 'kgzip2':
            lungo = lungo * 3                                  # tre blocchi da 4 KiB con -1
            r1 = esegui(cmd + ['-1', '-s'], input=lungo)
            r3 = esegui(cmd + ['-1'], input=lungo)
            att = D.atteso(lungo, 4096)
        else:
            r1 = esegui(cmd + ['-T1', '--block-size=1KiB'], input=lungo)
            r3 = esegui(cmd + ['-T', '3', '--block-size', '1KiB'], input=lungo)
            att = D.atteso(lungo, 1024, 32)
        controlla(r1.returncode == 0 and r1.stdout == r3.stdout == att,
                  f'{nome}: pipe a piu\' blocchi, uguale al modello in sequenza e in parallelo')
        r = esegui(cmd + ['-d'], input=r1.stdout + filtro)
        controlla(r.returncode == 0 and r.stdout == lungo + dati, f'{nome}: flussi concatenati da una pipe')
        r = esegui(cmd + ['-d'], input=filtro + b'x')
        controlla(r.returncode == corrotto, f'{nome}: dati estranei in coda rifiutati')
        if nome == 'kgzip2':
            # il blocco piu' grande (-9, 64 KiB) con una corsa lunga quanto il blocco: la
            # lunghezza sta ancora nei due byte dell'RLE iniziale
            zeri = bytes(65536 + 7)
            r = esegui(cmd + ['-c'], input=zeri)
            controlla(r.returncode == 0 and r.stdout == D.atteso(zeri, 65536)
                      and esegui(cmd + ['-dc'], input=r.stdout).stdout == zeri,
                      'kgzip2: blocchi da 64 KiB con una corsa lunga quanto il blocco')
        if nome == 'klzma':
            for p, (kib, Dp) in ((0, (8, 4)), (9, (256, 128))):
                r = esegui(cmd + [f'-{p}'], input=lungo)
                controlla(r.stdout == D.atteso(lungo, kib * 1024, Dp), f'klzma: preset -{p} uguale al modello')
            r = esegui(cmd + ['-e'], input=lungo)
            controlla(r.stdout == D.atteso(lungo, 64 * 1024, 64), 'klzma: -e raddoppia la profondita\'')
            r = esegui(cmd + ['-l', z])
            controlla(r.returncode == 0 and b'CRC32' in r.stdout and str(len(dati)).encode() in r.stdout, 'klzma: -l')
            r = esegui(cmd + ['-S', '.xyz', '-k', f])
            controlla(r.returncode == 0 and (d / 'prova.txt.xyz').exists(), 'klzma: -S cambia il suffisso')
        controlla(not [p for p in d.iterdir() if '.tmp' in p.name], f'{nome}: nessun file temporaneo rimasto')


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
    print('binari:', flush=True)
    for nome, D in (('kgzip2', KG), ('klzma', KL)):
        for etichetta, dati in casi.items():
            n = prova_binario(nome, D, dati, etichetta)
        print(f'  {nome}: {len(casi)} casi uguali al modello, ritorno esatto', flush=True)
    print('comandi:', flush=True)
    prova_comandi('kgzip2', KG)
    prova_comandi('klzma', KL)
    print('ordinamenti delle rotazioni:', flush=True)
    r = subprocess.run([sys.executable, str(RADICE / 'kgzip2' / 'ordinamenti.py'), 'verifica',
                        '10' if RAPIDO else '30', '20'], capture_output=True, text=True)
    controlla(r.returncode == 0 and 'errori: 0' in r.stdout, 'ordinamenti: discordanza col riferimento')
    print(f'\n{ESITI["ok"]} controlli superati, {len(ESITI["errori"])} falliti')
    sys.exit(1 if ESITI['errori'] else 0)
