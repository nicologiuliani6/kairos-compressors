#!/usr/bin/env python3
"""Che cosa fa l'uncall su un file alterato, se il CRC non lo ferma prima.

    python3 bench/manomissione.py [PROVE]       -> doc/dati/manomissione.json

Per ogni algoritmo si comprime un blocco di 1 KiB della tesi, poi lo si altera
e si esegue direttamente `uncall comprimi`, saltando il controllo del CRC:
    - un bit invertito in un punto a caso dei bit compressi;
    - un contatore del frame (kgzip2: idx, n1, gettoni, elementi, bit;
      klzma: stato rANS x, bit) cambiato di +1 o -1;
    - per kgzip2 anche due bit adiacenti scambiati.
Esiti: `asserzione` (la VM si ferma da sola: un'asserzione d'uscita, un
`delocal`, un controllo di uno stack), `non termina` (oltre dieci volte il tempo
normale), `uscita sbagliata` (termina con dati diversi, senza errori), `uscita
giusta` (l'alterazione non cambia il risultato).
"""
import json
import multiprocessing
import pathlib
import random
import re
import sys
import time
from collections import Counter

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from comune import kvm               # noqa: E402
from kgzip2 import driver as KG      # noqa: E402
from klzma import driver as KL       # noqa: E402

ALG = {'kgzip2': KG, 'klzma': KL}
BLOCCO = (RADICE / 'test' / 'corpus' / 'tesi8k.tex').read_bytes()[:1024]


# Che cosa ha fermato la VM. I primi quattro sono controlli che esistono solo
# perche' il programma e' reversibile: l'inverso deve disfare esattamente il
# calcolo, e se il file non e' quello che il compressore avrebbe prodotto un
# ausiliario non torna a zero, un'asserzione d'uscita contraddice il ramo, o una
# pop trova la destinazione occupata. Gli ultimi due sono controlli di sicurezza
# che avrebbe anche un decodificatore ordinario scritto con cura.
MOTIVI = [('DELOCAL', 'delocal'), ('inverse IF', 'asserzione d\'uscita'), ('FROM', 'asserzione di ciclo'),
          ('Pop-Err2', 'pop su destinazione non nulla'), ('Idx-Err', 'indice fuori dai limiti'),
          ('Pop-Err', 'pop da stack vuoto')]
REVERSIBILITA = {'delocal', 'asserzione d\'uscita', 'asserzione di ciclo', 'pop su destinazione non nulla'}


def motivo(msg):
    for chiave, nome in MOTIVI:
        if chiave in msg:
            return nome
    return msg.split('[VM]')[-1].strip()[:80]


def prova(arg):
    alg, tipo, conti, bits, limite = arg
    D = ALG[alg]
    t0 = time.perf_counter()
    try:
        out, _, _ = D.decomprimi_gruppo([(len(BLOCCO), tuple(conti), bits)], timeout=limite)
        esito = 'uscita giusta' if out[0] == BLOCCO else 'uscita sbagliata'
        dett = ''
    except kvm.ErroreKairos as e:
        if 'non ha terminato' in str(e):
            esito, dett = 'non termina', ''
        else:
            esito, dett = 'asserzione', motivo(str(e))
    except Exception as e:                         # uscita illeggibile, per esempio
        esito, dett = 'asserzione', type(e).__name__
    return alg, tipo, esito, dett, round(time.perf_counter() - t0, 2)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rnd = random.Random(2026)
    lavori, base = [], {}
    for alg, D in ALG.items():
        (r,), _, _ = D.comprimi_gruppo([BLOCCO], timeout=600)
        conti, bits = r
        t0 = time.perf_counter()
        out, _, _ = D.decomprimi_gruppo([(len(BLOCCO), conti, bits)], timeout=600)
        normale = time.perf_counter() - t0
        assert out[0] == BLOCCO
        limite = max(10 * normale, 5.0)
        base[alg] = {'conti': list(conti), 'bit': len(bits), 'secondi_uncall': round(normale, 2),
                     'limite': round(limite, 1)}
        for _ in range(n):
            b = list(bits)
            b[rnd.randrange(len(b))] ^= 1
            lavori.append((alg, 'bit invertito', list(conti), b, limite))
        for _ in range(n // 4):
            b = list(bits)
            p = rnd.randrange(len(b) - 1)
            if b[p] == b[p + 1]:
                b[p] ^= 1
                b[p + 1] ^= 1
            else:
                b[p], b[p + 1] = b[p + 1], b[p]
            lavori.append((alg, 'due bit alterati', list(conti), b, limite))
        for k in range(len(conti) - 1):            # l'ultimo e' il numero di bit: cambia anche i bit
            for d in (+1, -1):
                c = list(conti)
                c[k] += d
                lavori.append((alg, f'contatore {k} {d:+d}', c, list(bits), limite))
        for d in (+1, -1):                          # un bit in piu' o in meno in fondo
            b = list(bits) + [0] if d > 0 else list(bits)[:-1]
            c = list(conti)
            c[-1] += d
            lavori.append((alg, f'numero di bit {d:+d}', c, b, limite))
    with multiprocessing.Pool(2) as pool:
        ris = []
        for i, r in enumerate(pool.imap_unordered(prova, lavori), 1):
            ris.append(r)
            if i % 25 == 0:
                print(f'{i}/{len(lavori)}', flush=True)
    riass = {}
    for alg in ALG:
        mine = [r for r in ris if r[0] == alg]
        riass[alg] = {
            'base': base[alg],
            'totale': dict(Counter(r[2] for r in mine)),
            'per_tipo': {t: dict(Counter(r[2] for r in mine if (r[1].split()[0] == t))) for t in
                         ('bit', 'due', 'contatore', 'numero')},
            'motivi': dict(Counter(r[3] for r in mine if r[2] == 'asserzione').most_common()),
            'prove': [{'tipo': r[1], 'esito': r[2], 'motivo': r[3], 'secondi': r[4]} for r in mine],
        }
        riass[alg]['reversibilita'] = sum(1 for r in mine if r[2] == 'asserzione' and r[3] in REVERSIBILITA)
        print(alg, riass[alg]['totale'], riass[alg]['motivi'], 'dalla reversibilita:', riass[alg]['reversibilita'])
    uscita = sys.argv[2] if len(sys.argv) > 2 else 'manomissione.json'
    (RADICE / 'doc' / 'dati' / uscita).write_text(json.dumps(riass, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
