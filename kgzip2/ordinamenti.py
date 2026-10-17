#!/usr/bin/env python3
"""Le quattro varianti dell'ordinamento delle rotazioni sullo stesso programma.

    python3 kgzip2/ordinamenti.py verifica <casi> <n_max> [varianti]
    python3 kgzip2/ordinamenti.py tempi <variante> <tipo> <n> [<n> ...]

Tipi di dati: casuale, testo, periodico (periodo 6, come genera_bwt.py),
costante.

Varianti: bolle (bwt.kairos della tesi), bolle_ae (bolle con uscita anticipata
e passo accorciato), fusione (merge sort con uscita anticipata), raddoppio
(prefix doubling). Il programma: carica il blocco, `ordina` + `estrai`,
stampa, poi disfa tutto con `uncall`. Si misura il tempo della VM.
"""
import pathlib, random, sys

QUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))
from comune import kvm                          # noqa: E402
TESTO = kvm.HOME / 'README.md'                  # sorgente dei blocchi di tipo "testo"


def procedure(testo):
    """nome -> sorgente, tagliando prima di ogni riga `procedure`."""
    pezzi, nome, buf = {}, None, []
    for riga in testo.splitlines():
        if riga.startswith('procedure '):
            if nome:
                pezzi[nome] = '\n'.join(buf)
            nome, buf = riga.split()[1].split('(')[0], []
        if nome:
            buf.append(riga)
    if nome:
        pezzi[nome] = '\n'.join(buf)
    return pezzi


BZIP = procedure((QUI / 'kgzip2.kairos').read_text())
FUS = procedure((QUI / 'fusione.kairos').read_text())
ORIG = procedure((kvm.HOME / 'lossless' / 'bwt.kairos').read_text())
IDENT = BZIP['identita']
RAD = BZIP

# bubble sort con il confronto a uscita anticipata e il passo interno che si
# accorcia di uno a ogni giro (le ultime i posizioni sono gia' a posto)
ORDINA_BOLLE_AE = """procedure ordina(int offs[], int blocco[], stack scarto, int n)
    local int m = 0
        m += n
        m -= 1
        local int i = 0
        from i == 0 do
            local int lim = 0
                lim += m
                lim -= i
                local int j = 0
                from j == 0 do
                    call passo(offs, blocco, scarto, n, j)
                    j += 1
                loop until j == lim
                delocal int j = lim
                lim += i
                lim -= m
            delocal int lim = 0
            i += 1
        loop until i == m
        delocal int i = m
        m += 1
        m -= n
    delocal int m = 0"""

LIB = {
    'bolle': '\n'.join([IDENT, ORIG['car'], ORIG['maggiore'], ORIG['passo'], ORIG['ordina'],
                        ORIG['estrai'],
                        'procedure ordina_rot(int offs[], int blocco[], stack scarto, int n)\n'
                        '    call identita(offs, n)\n    call ordina(offs, blocco, scarto, n)']),
    'bolle_ae': '\n'.join([IDENT, ORIG['car'], FUS['maggiore'], ORIG['passo'], ORDINA_BOLLE_AE,
                           ORIG['estrai'],
                           'procedure ordina_rot(int offs[], int blocco[], stack scarto, int n)\n'
                           '    call identita(offs, n)\n    call ordina(offs, blocco, scarto, n)']),
    'fusione': '\n'.join([IDENT, BZIP['car'], FUS['maggiore'], FUS['fondi'], FUS['msort'],
                          FUS['ordina'], BZIP['estrai'],
                          'procedure ordina_rot(int offs[], int tmp[], int blocco[], stack scarto, int n)\n'
                          '    call identita(offs, n)\n    call ordina(offs, tmp, blocco, scarto, n)']),
    'raddoppio': '\n'.join([IDENT, BZIP['car'], BZIP['estrai'], BZIP['cumulata']] +
                           [RAD[k] for k in ('conta_chiavi', 'per_conteggio', 'ordina_coppie',
                                             'nuovi_ranghi', 'scarta', 'giro', 'ordina')]),
}
ARGS = {
    'bolle': 'offs, blocco, scarto, n', 'bolle_ae': 'offs, blocco, scarto, n',
    'fusione': 'offs, tmp, blocco, scarto, n',
    'raddoppio': 'offs, blocco, rk, rk2, tmp, ide, cnt, pos, scarto, n, nr',
}
CHIAMA = {v: ('ordina_rot' if v != 'raddoppio' else 'ordina') for v in LIB}


def programma(v, s):
    n = len(s); nr = max(n, 256)
    L = [LIB[v], 'procedure main()', '    stack scarto', f'    local int n = {n}',
         f'    local int nr = {nr}']
    arr = [('blocco', n), ('offs', n), ('out', n), ('tmp', n), ('rk', n), ('rk2', n),
           ('ide', n), ('cnt', nr), ('pos', nr)]
    L += [f'    local int {a}[{k}] = 0' for a, k in arr]
    L += [f'    blocco[{k}] += {x}' for k, x in enumerate(s) if x]
    L += [f'    call {CHIAMA[v]}({ARGS[v]})', '    local int idx = 0',
          '        call estrai(offs, blocco, out, n, idx)',
          '        show(offs)', '        show(out)', '        show(idx)',
          '        uncall estrai(offs, blocco, out, n, idx)', '    delocal int idx = 0',
          f'    uncall {CHIAMA[v]}({ARGS[v]})', '    show(scarto)']
    L += [f'    blocco[{k}] -= {x}' for k, x in reversed(list(enumerate(s))) if x]
    L += [f'    delocal int {a}[{k}] = 0' for a, k in reversed(arr)]
    L += ['    delocal int nr = ' + str(nr), f'    delocal int n = {n}']
    return '\n'.join(L) + '\n'


def esegui(src, tag=None):
    """(valori, secondi di VM, scarto vuoto)."""
    vals, t = kvm.esegui(kvm.compila(src), timeout=3600)
    return vals, t, vals.get('scarto') == [], ''


def riferimento(s):
    n = len(s)
    rot = sorted(range(n), key=lambda o: s[o:] + s[:o])
    return rot, [s[(o - 1) % n] for o in rot], rot.index(0)


def dati(tipo, n, rnd):
    if tipo == 'casuale':
        return [rnd.randrange(256) for _ in range(n)]
    if tipo == 'testo':
        t = TESTO.read_bytes()
        o = rnd.randrange(len(t) - n)
        return list(t[o:o + n])
    if tipo == 'periodico':                         # come genera_bwt.py: periodo 6
        base = [2, 1, 3, 1, 3, 1]
        return [base[k % 6] for k in range(n)]
    if tipo == 'costante':
        return [7] * n
    raise SystemExit(tipo)


if __name__ == '__main__':
    if sys.argv[1] == 'verifica':
        casi, nmax = int(sys.argv[2]), int(sys.argv[3])
        rnd = random.Random(4); err = 0
        varianti = sys.argv[4].split(',') if len(sys.argv) > 4 else list(LIB)
        for c in range(casi):
            n = rnd.randint(2, nmax)
            tipo = ['casuale', 'testo', 'periodico', 'costante', 'piccolo'][c % 5]
            s = ([rnd.randint(0, 2) for _ in range(n)] if tipo == 'piccolo'
                 else dati(tipo, n, rnd))
            att = riferimento(s)
            for v in varianti:
                vals, t, ok, raw = esegui(programma(v, s), f'v_{v}')
                giusto = ok and (vals.get('offs'), vals.get('out'), vals.get('idx')) == att
                if not giusto:
                    err += 1
                    print(f'ERR {v} n={n} {tipo} s={s}\n  atteso {att}\n  avuto {vals}\n  {raw[-600:]}')
            print(f'caso {c}: n={n} {tipo} ok', flush=True)
        print(f'errori: {err}')
    else:
        v, tipo = sys.argv[2], sys.argv[3]
        for n in map(int, sys.argv[4:]):
            ts = []
            for rip in range(3):
                s = dati(tipo, n, random.Random(n * 7 + rip))
                vals, t, ok, raw = esegui(programma(v, s), f't_{v}')
                assert ok and (vals['offs'], vals['out'], vals['idx']) == riferimento(s), raw[-500:]
                ts.append(t)
            print(f'{v} {tipo} n={n} vm_min={min(ts):.3f}', flush=True)
