"""kgzip2: il programma Kairos di un gruppo di blocchi.

Per ogni blocco la pipeline e' RLE iniziale -> BWT -> move-to-front -> RLE
degli zeri -> codice di Elias gamma, tutta nella procedura `comprimi` di
kgzip2.kairos. La compressione esegue `call comprimi`, la decompressione
`uncall comprimi`: lo stesso codice, nei due versi. I blocchi di un gruppo sono
rami di un `par`.

Il formato a frame e lo streaming sono comuni (comune/contenitore.py,
comune/flusso.py): KGZ4, nessun parametro, e per ogni frame in modo 0 i cinque
contatori idx, n1, gettoni, elementi, bit.
"""
import pathlib
import sys

from comune import flusso
from comune import kvm

QUI = pathlib.Path(__file__).resolve().parent
LIBRERIA = (QUI / 'kgzip2.kairos').read_text()
MAGIA = b'KGZ4'
PARAMETRI = ()
NA = 256
ARRAY = ('blocco', 'r', 'offs', 'out', 'tv', 'cam', 'ric', 'm', 'rk', 'rk2', 'ide')
ARRAY_NA = ('tab', 'freq', 'prima', 'visti')
ARRAY_NR = ('cnt', 'pos')
STACK = ('scarto', 'src', 'dst', 'bit', 'uscita')
CONT = ('idx', 'n1', 'ng', 'nel', 'nb')
NCONT = len(CONT)
BLOCCO = 8192
SEQUENZIALE = False


dividi = flusso.dividi


def dim(a, n):
    """Dopo l'RLE iniziale il blocco e' lungo n1 <= 3n/2 + 6."""
    return n if a == 'blocco' else n + n // 2 + 6


def nr(n):
    return max(dim('r', n), NA)


def _args(i):
    return ', '.join([f'{a}_{i}' for a in ARRAY] + [f'{a}_{i}' for a in ARRAY_NA + ARRAY_NR] +
                     [f'{s}_{i}' for s in STACK if s != 'uscita'] +
                     [f'{c}_{i}' for c in CONT] + [f'n_{i}', 'na', f'nr_{i}'])


def programma(lunghezze, verso):
    """Il programma senza dati: i dati entrano al posto di `segnaposto_dati`."""
    R = range(len(lunghezze))
    L = [LIBRERIA, 'procedure main()', '    int na', f'    na += {NA}', f'    int {kvm.SEGNAPOSTO}']
    for i in R:
        L.append('    ' + '  '.join(f'stack {s}_{i}' for s in STACK))
        L.append('    ' + '  '.join(f'int {c}_{i}' for c in CONT + ('n',)))
        L.append(f'    n_{i} += {lunghezze[i]}')
        L.append(f'    int nr_{i}  nr_{i} += {nr(lunghezze[i])}')
    for i in R:
        L += [f'    local int {a}_{i}[{dim(a, lunghezze[i])}] = 0' for a in ARRAY]
        L += [f'    local int {a}_{i}[{NA}] = 0' for a in ARRAY_NA]
        L += [f'    local int {a}_{i}[{nr(lunghezze[i])}] = 0' for a in ARRAY_NR]
    if verso == 'uncall':
        L += [f'    local int t_{i} = 0' for i in R]
    L.append(f'    {kvm.SEGNAPOSTO} += 0')
    if verso == 'uncall':
        L += [f'    delocal int t_{i} = 0' for i in reversed(R)]
    rami = [f'    {verso} comprimi({_args(i)})' for i in R]
    if len(rami) == 1 or SEQUENZIALE:
        L += rami
    else:
        L += ['    par', '\n    and\n'.join('    ' + r for r in rami), '    rap']
    for i in R:
        if verso == 'call':
            L += [f'    show({c}_{i})' for c in CONT] + [f'    show(bit_{i})']
        else:
            L += [f'    call scarica(blocco_{i}, uscita_{i}, n_{i})', f'    show(uscita_{i})']
    for i in reversed(R):
        L += [f'    delocal int {a}_{i}[{nr(lunghezze[i])}] = 0' for a in reversed(ARRAY_NR)]
        L += [f'    delocal int {a}_{i}[{NA}] = 0' for a in reversed(ARRAY_NA)]
        L += [f'    delocal int {a}_{i}[{dim(a, lunghezze[i])}] = 0' for a in reversed(ARRAY)]
    return '\n'.join(L) + '\n'


def _dati_byte(blocchi):
    return [f'PUSHEQ blocco_{i}[{k}] {v}' for i, b in enumerate(blocchi) for k, v in enumerate(b) if v]


def _dati_bit(blocchi):
    istr = []
    for i, (n, conti, bits) in enumerate(blocchi):
        for b in bits:                       # dal fondo alla cima, come li stampa show
            if b:
                istr.append(f'PUSHEQ t_{i} 1')
            istr.append(f'PUSH t_{i} bit_{i}')
        istr += [f'PUSHEQ {c}_{i} {v}' for c, v in zip(CONT, conti) if v]
    return istr


def comprimi_gruppo(blocchi, timeout=None):
    """Un'esecuzione della VM per tutto il gruppo. Un blocco di meno di 2 byte
    non va alla VM e si memorizza."""
    kai = [i for i, b in enumerate(blocchi) if len(b) >= 2]
    ris, tf, tv = [None] * len(blocchi), 0.0, 0.0
    if kai:
        val, tf, tv = kvm.frontend_e_vm(programma([len(blocchi[i]) for i in kai], 'call'),
                                        _dati_byte([blocchi[i] for i in kai]), timeout)
        for j, i in enumerate(kai):
            conti = tuple(val[f'{c}_{j}'] for c in CONT)
            assert conti[-1] == len(val[f'bit_{j}'])
            ris[i] = (conti, val[f'bit_{j}'])
    return ris, tf, tv


def decomprimi_gruppo(frame, timeout=None):
    """frame: [(n, conti, bits)], tutti in modo 0."""
    val, tf, tv = kvm.frontend_e_vm(programma([f[0] for f in frame], 'uncall'),
                                    _dati_bit(frame), timeout)
    return [bytes(val[f'uscita_{i}']) for i in range(len(frame))], tf, tv


def blocco_modello(b):
    from . import modello
    if len(b) < 2:
        return None
    n, idx, n1, ng, nel, nb, bits = modello.blocco(b)[0]
    return (idx, n1, ng, nel, nb), bits


_QUESTO = sys.modules[__name__]


def comprimi_flusso(ingresso, uscita, dim_blocco=BLOCCO, gruppo=None, timeout=None, avanzamento=None):
    return flusso.comprimi(_QUESTO, ingresso, uscita, dim_blocco, gruppo, timeout, (), avanzamento)


def decomprimi_flusso(ingresso, uscita, gruppo=None, timeout=None, avanzamento=None, salta_crc=False):
    return flusso.decomprimi(_QUESTO, ingresso, uscita, gruppo, timeout, avanzamento, salta_crc)


def comprimi(dati, dim_blocco=BLOCCO, timeout=None, gruppo=None):
    """In memoria: (file compresso, (secondi di frontend, secondi di VM))."""
    return flusso.comprimi_dati(_QUESTO, dati, dim_blocco, gruppo, timeout)


def decomprimi(buf, timeout=None, gruppo=None, salta_crc=False):
    return flusso.decomprimi_dati(_QUESTO, buf, gruppo, timeout, salta_crc)


def atteso(dati, dim_blocco=BLOCCO):
    """Lo stesso file prodotto dal modello Python (per i test)."""
    return flusso.atteso(_QUESTO, dati, dim_blocco)
