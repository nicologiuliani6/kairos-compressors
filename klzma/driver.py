"""klzma: il programma Kairos di un gruppo di blocchi.

LZ77 con catene di hash e rep0, contesti alla LZMA, rANS binario: tutto nella
procedura `comprimi` di klzma.kairos. La compressione esegue `call comprimi`,
la decompressione `uncall comprimi`. Come in LZMA2 il file si divide in
blocchi; qui sono indipendenti (come in xz multithread) e quelli di un gruppo
sono rami di un `par`. Un blocco che non si riduce si memorizza.

Il formato a frame e lo streaming sono comuni (comune/contenitore.py,
comune/flusso.py): KLZ4, un parametro (la profondita' D della ricerca), e per
ogni frame in modo 0 lo stato rANS finale x e il numero di bit.
"""
import pathlib
import sys

from comune import flusso
from comune import kvm
from . import modello

QUI = pathlib.Path(__file__).resolve().parent
LIBRERIA = (QUI / 'klzma.kairos').read_text()
MAGIA = b'KLZ4'
PARAMETRI = ('D',)
NCONT = 2
NCNT = 2 * modello.NCTX
BLOCCO = 8192
D_PREDEFINITO = 32
SEQUENZIALE = False
OPZIONI = ('D',)
NOMI = 'b n D prev head ty ln ds st rp slotbase cnt pot2 scarto bitst x nb'.split()


dividi = flusso.dividi


def _arr(i, n):
    return [(f'b_{i}', n), (f'prev_{i}', n), (f'head_{i}', modello.HSIZE), (f'ty_{i}', n),
            (f'ln_{i}', n), (f'ds_{i}', n), (f'st_{i}', n), (f'rp_{i}', n), (f'slotbase_{i}', 64),
            (f'cnt_{i}', NCNT), (f'pot2_{i}', 32)]


def programma(lunghezze, D, verso):
    R = range(len(lunghezze))
    L = [LIBRERIA, 'procedure main()', f'    int {kvm.SEGNAPOSTO}']
    for i in R:
        L += [f'    stack scarto_{i}  stack bitst_{i}  stack uscita_{i}',
              f'    int x_{i}  int nb_{i}  int n_{i}  int D_{i}',
              f'    n_{i} += {lunghezze[i]}', f'    D_{i} += {D}']
    costanti = []
    for i in R:
        L += [f'    local int {a}[{k}] = 0' for a, k in _arr(i, lunghezze[i])]
        costanti += [f'    pot2_{i}[{k}] += {1 << k}' for k in range(32)]
        costanti += [f'    slotbase_{i}[{s}] += {modello.base_slot(s)}' for s in range(1, 64)]
    L += costanti
    if verso == 'uncall':
        L += [f'    local int t_{i} = 0' for i in R]
    L.append(f'    {kvm.SEGNAPOSTO} += 0')
    if verso == 'uncall':
        L += [f'    delocal int t_{i} = 0' for i in reversed(R)]
    rami = [f'    {verso} comprimi(' + ', '.join(f'{a}_{i}' for a in NOMI) + ')' for i in R]
    if len(rami) == 1 or SEQUENZIALE:
        L += rami
    else:
        L += ['    par', '\n    and\n'.join('    ' + r for r in rami), '    rap']
    for i in R:
        if verso == 'call':
            L += [f'    show(x_{i})', f'    show(nb_{i})', f'    show(bitst_{i})']
        else:
            L += [f'    call scarica(b_{i}, uscita_{i}, n_{i})', f'    show(uscita_{i})']
    L += [c.replace('+=', '-=') for c in reversed(costanti)]
    for i in reversed(R):
        L += [f'    delocal int {a}[{k}] = 0' for a, k in reversed(_arr(i, lunghezze[i]))]
    return '\n'.join(L) + '\n'


def comprimi_gruppo(blocchi, timeout=None, D=D_PREDEFINITO):
    """Un'esecuzione della VM per tutto il gruppo (un blocco vuoto si memorizza)."""
    kai = [i for i, b in enumerate(blocchi) if b]
    ris, tf, tv = [None] * len(blocchi), 0.0, 0.0
    if kai:
        istr = [f'PUSHEQ b_{j}[{k}] {v}' for j, i in enumerate(kai) for k, v in enumerate(blocchi[i]) if v]
        val, tf, tv = kvm.frontend_e_vm(programma([len(blocchi[i]) for i in kai], D, 'call'), istr, timeout)
        for j, i in enumerate(kai):
            assert val[f'nb_{j}'] == len(val[f'bitst_{j}'])
            ris[i] = ((val[f'x_{j}'], val[f'nb_{j}']), val[f'bitst_{j}'])
    return ris, tf, tv


def decomprimi_gruppo(frame, timeout=None, D=D_PREDEFINITO):
    """frame: [(n, (x, nb), bits)], tutti in modo 0."""
    istr = []
    for i, (n, (x, nb), bits) in enumerate(frame):
        for b in bits:
            if b:
                istr.append(f'PUSHEQ t_{i} 1')
            istr.append(f'PUSH t_{i} bitst_{i}')
        istr += [f'PUSHEQ x_{i} {x}', f'PUSHEQ nb_{i} {len(bits)}']
    val, tf, tv = kvm.frontend_e_vm(programma([f[0] for f in frame], D, 'uncall'), istr, timeout)
    return [bytes(val[f'uscita_{i}']) for i in range(len(frame))], tf, tv


def blocco_modello(b, D=D_PREDEFINITO):
    if not b:
        return None
    bits, x, _ = modello.comprimi(list(b), D)
    return (x, len(bits)), bits


_QUESTO = sys.modules[__name__]


def comprimi_flusso(ingresso, uscita, dim_blocco=BLOCCO, gruppo=None, timeout=None,
                    avanzamento=None, D=D_PREDEFINITO):
    return flusso.comprimi(_QUESTO, ingresso, uscita, dim_blocco, gruppo, timeout, (D,), avanzamento)


def decomprimi_flusso(ingresso, uscita, gruppo=None, timeout=None, avanzamento=None):
    return flusso.decomprimi(_QUESTO, ingresso, uscita, gruppo, timeout, avanzamento)


def comprimi(dati, dim_blocco=BLOCCO, timeout=None, gruppo=None, D=D_PREDEFINITO):
    """In memoria: (file compresso, (secondi di frontend, secondi di VM))."""
    return flusso.comprimi_dati(_QUESTO, dati, dim_blocco, gruppo, timeout, (D,))


def decomprimi(buf, timeout=None, gruppo=None):
    return flusso.decomprimi_dati(_QUESTO, buf, gruppo, timeout)


def atteso(dati, dim_blocco=BLOCCO, D=D_PREDEFINITO):
    return flusso.atteso(_QUESTO, dati, dim_blocco, (D,))
