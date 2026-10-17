"""klzma: involucro e contenitore.

LZ77 con catene di hash e rep0, contesti alla LZMA, rANS binario: tutto nella
procedura `comprimi` di klzma.kairos. La compressione esegue `call comprimi`,
la decompressione `uncall comprimi`. Come in LZMA2 il file si divide in
blocchi; qui sono indipendenti (come in xz multithread) e sono rami di un
`par`. Un blocco che non si riduce si memorizza.

Il contenitore KLZ3:
    KLZ3, numero di blocchi, profondita' D della ricerca,
    per blocco: modo (0 Kairos, 1 memorizzato), n, e se modo 0 lo stato rANS
    finale x e il numero di bit;
    i bit dei blocchi in modo 0, poi i byte dei blocchi memorizzati;
    CRC32 dei dati originali, CRC32 del file.
"""
import pathlib

from comune import contenitore as C
from comune import kvm
from . import modello

QUI = pathlib.Path(__file__).resolve().parent
LIBRERIA = (QUI / 'klzma.kairos').read_text()
MAGIA = b'KLZ3'
NCNT = 2 * modello.NCTX
BLOCCO = 8192
D_PREDEFINITO = 32
SEQUENZIALE = False
OPZIONI = ('D',)
NOMI = 'b n D prev head ty ln ds st rp slotbase cnt pot2 scarto bitst x nb'.split()


def dividi(dati, dim):
    k = max(1, -(-len(dati) // dim))
    base, resto = divmod(len(dati), k)
    out, p = [], 0
    for i in range(k):
        l = base + (i < resto)
        out.append(bytes(dati[p:p + l]))
        p += l
    return out


def _arr(i, n):
    return [(f'b{i}', n), (f'prev{i}', n), (f'head{i}', modello.HSIZE), (f'ty{i}', n),
            (f'ln{i}', n), (f'ds{i}', n), (f'st{i}', n), (f'rp{i}', n), (f'slotbase{i}', 64),
            (f'cnt{i}', NCNT), (f'pot2{i}', 32)]


def programma(lunghezze, D, verso):
    R = range(len(lunghezze))
    L = [LIBRERIA, 'procedure main()', f'    int {kvm.SEGNAPOSTO}']
    for i in R:
        L += [f'    stack scarto{i}  stack bitst{i}  stack uscita{i}',
              f'    int x{i}  int nb{i}  int n{i}  int D{i}',
              f'    n{i} += {lunghezze[i]}', f'    D{i} += {D}']
    costanti = []
    for i in R:
        L += [f'    local int {a}[{k}] = 0' for a, k in _arr(i, lunghezze[i])]
        costanti += [f'    pot2{i}[{k}] += {1 << k}' for k in range(32)]
        costanti += [f'    slotbase{i}[{s}] += {modello.base_slot(s)}' for s in range(1, 64)]
    L += costanti
    if verso == 'uncall':
        L += [f'    local int t{i} = 0' for i in R]
    L.append(f'    {kvm.SEGNAPOSTO} += 0')
    if verso == 'uncall':
        L += [f'    delocal int t{i} = 0' for i in reversed(R)]
    rami = [f'    {verso} comprimi(' + ', '.join(f'{a}{i}' for a in NOMI) + ')' for i in R]
    if len(rami) == 1 or SEQUENZIALE:
        L += rami
    else:
        L += ['    par', '\n    and\n'.join('    ' + r for r in rami), '    rap']
    for i in R:
        if verso == 'call':
            L += [f'    show(x{i})', f'    show(nb{i})', f'    show(bitst{i})']
        else:
            L += [f'    call scarica(b{i}, uscita{i}, n{i})', f'    show(uscita{i})']
    L += [c.replace('+=', '-=') for c in reversed(costanti)]
    for i in reversed(R):
        L += [f'    delocal int {a}[{k}] = 0' for a, k in reversed(_arr(i, lunghezze[i]))]
    return '\n'.join(L) + '\n'


def impacchetta(blocchi, D, originale):
    """blocchi: [(dati, x, bits)]; x None = da memorizzare."""
    corpo = bytearray(MAGIA) + C.varint(len(blocchi)) + C.varint(D)
    tutti, grezzi = [], bytearray()
    for dati, x, bits in blocchi:
        testa = C.varint(x) + C.varint(len(bits)) if x is not None else b''
        if x is None or (len(bits) + 7) // 8 + len(testa) >= len(dati):
            corpo += C.varint(1) + C.varint(len(dati))
            grezzi += dati
        else:
            corpo += C.varint(0) + C.varint(len(dati)) + testa
            tutti += bits
    corpo += C.impacchetta_bit(tutti) + grezzi
    return C.chiudi(corpo, originale)


def comprimi(dati, dim_blocco=BLOCCO, timeout=None, D=D_PREDEFINITO):
    blocchi = dividi(dati, dim_blocco)
    kai = [b for b in blocchi if b]
    res, tf, tv = {}, 0.0, 0.0
    if kai:
        istr = [f'PUSHEQ b{i}[{k}] {v}' for i, b in enumerate(kai) for k, v in enumerate(b) if v]
        val, tf, tv = kvm.frontend_e_vm(programma([len(b) for b in kai], D, 'call'), istr, timeout)
        for i, b in enumerate(kai):
            assert val[f'nb{i}'] == len(val[f'bitst{i}'])
            res[id(b)] = (val[f'x{i}'], val[f'bitst{i}'])
    righe = [(b,) + res[id(b)] if id(b) in res else (b, None, None) for b in blocchi]
    return impacchetta(righe, D, dati), (tf, tv)


def spacchetta(buf):
    corpo, crc = C.apri(buf, MAGIA)
    nbl, p = C.leggi_varint(corpo, 0)
    D, p = C.leggi_varint(corpo, p)
    teste = []
    for _ in range(nbl):
        modo, p = C.leggi_varint(corpo, p)
        n, p = C.leggi_varint(corpo, p)
        x = nb = 0
        if modo == 0:
            x, p = C.leggi_varint(corpo, p)
            nb, p = C.leggi_varint(corpo, p)
        elif modo != 1:
            raise C.FileNonValido('modo di blocco sconosciuto')
        teste.append((modo, n, x, nb))
    nbit = sum(t[3] for t in teste)
    lb = (nbit + 7) // 8
    bits = C.spacchetta_bit(corpo[p:p + lb], nbit)
    grezzi = corpo[p + lb:]
    blocchi, q, g = [], 0, 0
    for modo, n, x, nb in teste:
        if modo == 0:
            blocchi.append((0, n, x, bits[q:q + nb]))
            q += nb
        else:
            blocchi.append((1, n, None, grezzi[g:g + n]))
            g += n
    if g != len(grezzi):
        raise C.FileNonValido('lunghezza dei blocchi memorizzati incoerente')
    return D, blocchi, crc


def decomprimi(buf, timeout=None):
    D, blocchi, crc = spacchetta(buf)
    kai = [(n, x, bits) for modo, n, x, bits in blocchi if modo == 0]
    usc, tf, tv = [], 0.0, 0.0
    if kai:
        istr = []
        for i, (n, x, bits) in enumerate(kai):
            for b in bits:
                if b:
                    istr.append(f'PUSHEQ t{i} 1')
                istr.append(f'PUSH t{i} bitst{i}')
            istr += [f'PUSHEQ x{i} {x}', f'PUSHEQ nb{i} {len(bits)}']
        val, tf, tv = kvm.frontend_e_vm(programma([k[0] for k in kai], D, 'uncall'), istr, timeout)
        usc = [bytes(val[f'uscita{i}']) for i in range(len(kai))]
    out, j = bytearray(), 0
    for modo, n, x, dati in blocchi:
        if modo == 0:
            out += usc[j]
            j += 1
        else:
            out += dati
    out = bytes(out)
    C.verifica(out, crc)
    return out, (tf, tv)


def atteso(dati, dim_blocco=BLOCCO, D=D_PREDEFINITO):
    righe = []
    for b in dividi(dati, dim_blocco):
        if b:
            bits, x, _ = modello.comprimi(list(b), D)
            righe.append((b, x, bits))
        else:
            righe.append((b, None, None))
    return impacchetta(righe, D, dati)
