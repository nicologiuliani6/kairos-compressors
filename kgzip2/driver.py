"""kgzip2: involucro e contenitore.

Per ogni blocco la pipeline e' RLE iniziale -> BWT -> move-to-front -> RLE
degli zeri -> codice di Elias gamma, tutta nella procedura `comprimi` di
kgzip2.kairos. La compressione esegue `call comprimi`, la decompressione
`uncall comprimi`: lo stesso codice, nei due versi. I blocchi sono rami di un
`par`.

Il contenitore KGZ3:
    KGZ3, numero di blocchi,
    per blocco: modo (0 Kairos, 1 memorizzato), n, e se modo 0 i cinque
    contatori idx, n1, gettoni, elementi, bit;
    i bit di tutti i blocchi in modo 0, poi i byte dei blocchi memorizzati;
    CRC32 dei dati originali, CRC32 del file.
"""
import pathlib

from comune import contenitore as C
from comune import kvm

QUI = pathlib.Path(__file__).resolve().parent
LIBRERIA = (QUI / 'kgzip2.kairos').read_text()
MAGIA = b'KGZ3'
NA = 256
ARRAY = ('blocco', 'r', 'offs', 'out', 'tv', 'cam', 'ric', 'm', 'rk', 'rk2', 'ide')
ARRAY_NA = ('tab', 'freq', 'prima', 'visti')
ARRAY_NR = ('cnt', 'pos')
STACK = ('scarto', 'src', 'dst', 'bit', 'uscita')
CONT = ('idx', 'n1', 'ng', 'nel', 'nb')
BLOCCO = 8192
SEQUENZIALE = False


def dividi(dati, dim):
    """Blocchi di lunghezza quasi uguale, al piu' dim."""
    k = max(1, -(-len(dati) // dim))
    base, resto = divmod(len(dati), k)
    out, p = [], 0
    for i in range(k):
        l = base + (i < resto)
        out.append(bytes(dati[p:p + l]))
        p += l
    return out


def dim(a, n):
    """Dopo l'RLE iniziale il blocco e' lungo n1 <= 3n/2 + 6."""
    return n if a == 'blocco' else n + n // 2 + 6


def nr(n):
    return max(dim('r', n), NA)


def _args(i):
    return ', '.join([f'{a}{i}' for a in ARRAY] + [f'{a}{i}' for a in ARRAY_NA + ARRAY_NR] +
                     [f'{s}{i}' for s in STACK if s != 'uscita'] +
                     [f'{c}{i}' for c in CONT] + [f'n{i}', 'na', f'nr{i}'])


def programma(lunghezze, verso):
    """Il programma senza dati: i dati entrano al posto di `segnaposto_dati`."""
    R = range(len(lunghezze))
    L = [LIBRERIA, 'procedure main()', '    int na', f'    na += {NA}', f'    int {kvm.SEGNAPOSTO}']
    for i in R:
        L.append('    ' + '  '.join(f'stack {s}{i}' for s in STACK))
        L.append('    ' + '  '.join(f'int {c}{i}' for c in CONT + ('n',)))
        L.append(f'    n{i} += {lunghezze[i]}')
        L.append(f'    int nr{i}  nr{i} += {nr(lunghezze[i])}')
    for i in R:
        L += [f'    local int {a}{i}[{dim(a, lunghezze[i])}] = 0' for a in ARRAY]
        L += [f'    local int {a}{i}[{NA}] = 0' for a in ARRAY_NA]
        L += [f'    local int {a}{i}[{nr(lunghezze[i])}] = 0' for a in ARRAY_NR]
    if verso == 'uncall':
        L += [f'    local int t{i} = 0' for i in R]
    L.append(f'    {kvm.SEGNAPOSTO} += 0')
    if verso == 'uncall':
        L += [f'    delocal int t{i} = 0' for i in reversed(R)]
    rami = [f'    {verso} comprimi({_args(i)})' for i in R]
    if len(rami) == 1 or SEQUENZIALE:
        L += rami
    else:
        L += ['    par', '\n    and\n'.join('    ' + r for r in rami), '    rap']
    for i in R:
        if verso == 'call':
            L += [f'    show({c}{i})' for c in CONT] + [f'    show(bit{i})']
        else:
            L += [f'    call scarica(blocco{i}, uscita{i}, n{i})', f'    show(uscita{i})']
    for i in reversed(R):
        L += [f'    delocal int {a}{i}[{nr(lunghezze[i])}] = 0' for a in reversed(ARRAY_NR)]
        L += [f'    delocal int {a}{i}[{NA}] = 0' for a in reversed(ARRAY_NA)]
        L += [f'    delocal int {a}{i}[{dim(a, lunghezze[i])}] = 0' for a in reversed(ARRAY)]
    return '\n'.join(L) + '\n'


def _dati_byte(blocchi):
    return [f'PUSHEQ blocco{i}[{k}] {v}' for i, b in enumerate(blocchi) for k, v in enumerate(b) if v]


def _dati_bit(blocchi):
    istr = []
    for i, (n, conti, bits) in enumerate(blocchi):
        for b in bits:                       # dal fondo alla cima, come li stampa show
            if b:
                istr.append(f'PUSHEQ t{i} 1')
            istr.append(f'PUSH t{i} bit{i}')
        istr += [f'PUSHEQ {c}{i} {v}' for c, v in zip(CONT, conti) if v]
    return istr


def impacchetta(blocchi, originale):
    """blocchi: [(dati, conti o None, bits)]; conti None = da memorizzare."""
    corpo = bytearray(MAGIA) + C.varint(len(blocchi))
    tutti, grezzi = [], bytearray()
    for dati, conti, bits in blocchi:
        testa = b''.join(C.varint(v) for v in conti) if conti else b''
        if conti is None or (len(bits) + 7) // 8 + len(testa) >= len(dati):
            corpo += C.varint(1) + C.varint(len(dati))
            grezzi += dati
        else:
            corpo += C.varint(0) + C.varint(len(dati)) + testa
            tutti += bits
    corpo += C.impacchetta_bit(tutti) + grezzi
    return C.chiudi(corpo, originale)


def comprimi(dati, dim_blocco=BLOCCO, timeout=None):
    """Restituisce (file compresso, tempi): tempi = (frontend, VM)."""
    blocchi = dividi(dati, dim_blocco)
    kai = [b for b in blocchi if len(b) >= 2]          # un blocco di 1 byte si memorizza
    res, tf, tv = {}, 0.0, 0.0
    if kai:
        val, tf, tv = kvm.frontend_e_vm(programma([len(b) for b in kai], 'call'),
                                        _dati_byte(kai), timeout)
        for i, b in enumerate(kai):
            conti = tuple(val[f'{c}{i}'] for c in CONT)
            assert conti[-1] == len(val[f'bit{i}'])
            res[id(b)] = (conti, val[f'bit{i}'])
    righe = [(b,) + res[id(b)] if id(b) in res else (b, None, None) for b in blocchi]
    return impacchetta(righe, dati), (tf, tv)


def spacchetta(buf):
    corpo, crc = C.apri(buf, MAGIA)
    nbl, p = C.leggi_varint(corpo, 0)
    teste = []
    for _ in range(nbl):
        modo, p = C.leggi_varint(corpo, p)
        n, p = C.leggi_varint(corpo, p)
        conti = None
        if modo == 0:
            conti = []
            for _ in CONT:
                v, p = C.leggi_varint(corpo, p)
                conti.append(v)
        elif modo != 1:
            raise C.FileNonValido('modo di blocco sconosciuto')
        teste.append((modo, n, conti))
    nbit = sum(c[-1] for m, n, c in teste if m == 0)
    lb = (nbit + 7) // 8
    bits = C.spacchetta_bit(corpo[p:p + lb], nbit)
    grezzi = corpo[p + lb:]
    blocchi, q, g = [], 0, 0
    for modo, n, conti in teste:
        if modo == 0:
            blocchi.append((0, n, conti, bits[q:q + conti[-1]]))
            q += conti[-1]
        else:
            blocchi.append((1, n, None, grezzi[g:g + n]))
            g += n
    if g != len(grezzi):
        raise C.FileNonValido('lunghezza dei blocchi memorizzati incoerente')
    return blocchi, crc


def decomprimi(buf, timeout=None):
    blocchi, crc = spacchetta(buf)
    kai = [(n, conti, bits) for modo, n, conti, bits in blocchi if modo == 0]
    usc, tf, tv = [], 0.0, 0.0
    if kai:
        val, tf, tv = kvm.frontend_e_vm(programma([k[0] for k in kai], 'uncall'),
                                        _dati_bit(kai), timeout)
        usc = [bytes(val[f'uscita{i}']) for i in range(len(kai))]
    out, j = bytearray(), 0
    for modo, n, conti, dati in blocchi:
        if modo == 0:
            out += usc[j]
            j += 1
        else:
            out += dati
    out = bytes(out)
    C.verifica(out, crc)
    return out, (tf, tv)


def atteso(dati, dim_blocco=BLOCCO):
    """Lo stesso file prodotto dal modello Python (per i test)."""
    from . import modello
    righe = []
    for b in dividi(dati, dim_blocco):
        if len(b) >= 2:
            n, idx, n1, ng, nel, nb, bits = modello.blocco(b)[0]
            righe.append((b, (idx, n1, ng, nel, nb), bits))
        else:
            righe.append((b, None, None))
    return impacchetta(righe, dati)
