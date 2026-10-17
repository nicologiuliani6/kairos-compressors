#!/usr/bin/env python3
"""Modello Python di klzma, bit per bit, con un decodificatore indipendente.

    python3 modello.py FILE [profondita' ...]

Stessa parse, stessi contesti, stesso rANS della libreria Kairos: l'uscita di
klzma.kairos deve coincidere con `comprimi()` di questo file.
"""
import lzma, bz2, math, sys

M = 1 << 12          # precisione delle probabilita'
L = 1 << 16          # stato rANS in [L, 2L)
HSIZE = 4096
MAXLEN = 273
LIT, REP_, MAT = 0, 2, 1

# contesti: un solo vettore, sezioni consecutive
IS_MATCH = 0                     # 12 stati x 4 posizioni
IS_REP = IS_MATCH + 48           # 12 stati
LITC = IS_REP + 12               # 8 contesti x 256 nodi
LEN_M = LITC + 8 * 256           # codificatore delle lunghezze dei match
LEN_R = LEN_M + 322              # ... e delle ripetizioni
# dentro un codificatore di lunghezza: choice, choice2, low[4][8], mid[4][8], high[256]
SLOT = LEN_R + 322               # 4 stati di lunghezza x 64 nodi
SPEC = SLOT + 256                # 12 slot x 16 nodi (slot 4..11)
ALIGN = SPEC + 12 * 16           # 16 nodi
NCTX = ALIGN + 16


def h3(b, i):
    return (b[i] * 1031 + b[i + 1] * 31 + b[i + 2]) % HSIZE


def lung(b, i, j):
    n = len(b); k = 0
    while k < MAXLEN and i + k < n and b[i + k] == b[j + k]:
        k += 1
    return k


def stato_dopo(s, t):
    if t == LIT:
        return 0 if s < 4 else (s - 3 if s < 10 else s - 6)
    if t == MAT:
        return 7 if s < 7 else 10
    return 8 if s < 7 else 11


def parse(b, D):
    n = len(b)
    prev = [0] * n; head = [0] * HSIZE
    for i in range(n - 2):
        h = h3(b, i); prev[i] = head[h]; head[h] = i + 1
    tok, i, rep0, s = [], 0, 0, 0
    while i < n:
        best = bd = 0
        c, d = prev[i], 0
        while c > 0 and d < D:
            j = c - 1; Lm = lung(b, i, j)
            if Lm > best:
                best, bd = Lm, i - j
            c = prev[j]; d += 1
        Lr = lung(b, i, i - rep0) if rep0 > 0 else 0
        usa_rep = Lr >= 2 and Lr + 1 >= best
        pigro = False
        if best >= 3 and i + 1 < n and not usa_rep:
            b2, c2, d2 = 0, prev[i + 1], 0          # lazy: il miglior match in i + 1
            while c2 > 0 and d2 < D:
                j = c2 - 1; Lm = lung(b, i + 1, j)
                if Lm > b2:
                    b2 = Lm
                c2 = prev[j]; d2 += 1
            pigro = b2 > best
        if pigro:
            t, ln, ds = LIT, 1, 0
        elif usa_rep:
            t, ln, ds = REP_, Lr, rep0
        elif best >= 3:
            t, ln, ds = MAT, best, bd
        else:
            t, ln, ds = LIT, 1, 0
        tok.append((t, ln, ds, s, rep0, i))
        if t == MAT:
            rep0 = ds
        s = stato_dopo(s, t)
        i += ln
    return tok


def slot_di(d0):
    if d0 < 4:
        return d0
    Lg = d0.bit_length() - 1
    return 2 * Lg + ((d0 >> (Lg - 1)) & 1)


def base_slot(s):
    return s if s < 4 else (2 | (s & 1)) << ((s >> 1) - 1)


def albero(v, nb, base):
    """bit di un albero normale, nell'ordine del decodificatore (MSB prima)."""
    out, m = [], 1
    for k in range(nb - 1, -1, -1):
        bit = (v >> k) & 1; out.append((base + m, bit)); m = 2 * m + bit
    return out


def albero_inv(v, nb, base):
    """albero inverso (LSB prima), come gli slot bassi e l'align di LZMA."""
    out, m = [], 1
    for k in range(nb):
        bit = (v >> k) & 1; out.append((base + m, bit)); m = 2 * m + bit
    return out


def lunghezza(l, base, ps):
    out = []
    if l < 8:
        out.append((base, 0)); out += albero(l, 3, base + 2 + ps * 8)
    else:
        out.append((base, 1))
        if l < 16:
            out.append((base + 1, 0)); out += albero(l - 8, 3, base + 34 + ps * 8)
        else:
            out.append((base + 1, 1)); out += albero(l - 16, 8, base + 66)
    return out


def decisioni(b, t, ln, ds, s, p):
    """(contesto, bit) di un gettone nell'ordine del decodificatore; contesto
    None = bit a probabilita' fissa 1/2."""
    ps = p % 4
    out = [(IS_MATCH + s * 4 + ps, int(t != LIT))]
    if t == LIT:
        prevb = b[p - 1] if p > 0 else 0
        return out + albero(b[p], 8, LITC + (prevb >> 5) * 256)
    out.append((IS_REP + s, int(t == REP_)))
    if t == REP_:
        return out + lunghezza(ln - 2, LEN_R, ps)
    out += lunghezza(ln - 2, LEN_M, ps)
    d0 = ds - 1; sl = slot_di(d0)
    out += albero(sl, 6, SLOT + min(ln - 2, 3) * 64)
    if sl >= 4:
        nb = (sl >> 1) - 1; rem = d0 - base_slot(sl)
        if nb <= 4:
            out += albero_inv(rem, nb, SPEC + sl * 16)
        else:
            for k in range(nb - 1, 3, -1):
                out.append((None, (rem >> k) & 1))
            out += albero_inv(rem & 15, 4, ALIGN)
    return out


def p0_di(n0, n1):
    return 1 + ((n0 + 1) * (M - 2)) // (n0 + n1 + 2)


def comprimi(b, D=32):
    tok = parse(b, D)
    dec = [decisioni(b, t, ln, ds, s, p) for t, ln, ds, s, _r, p in tok]
    cnt = [[0, 0] for _ in range(NCTX)]
    for ds_ in dec:
        for c, bit in ds_:
            if c is not None:
                cnt[c][bit] += 1
    x, bits = L, []
    for ds_ in reversed(dec):
        for c, bit in reversed(ds_):
            if c is None:
                p0 = M // 2
            else:
                cnt[c][bit] -= 1
                p0 = p0_di(*cnt[c])
            f = p0 if bit == 0 else M - p0
            cu = 0 if bit == 0 else p0
            while x >= 32 * f:
                bits.append(x & 1); x >>= 1
            x = (x // f) * M + cu + (x % f)
    assert all(c == [0, 0] for c in cnt)
    return bits, x, tok


def decomprimi(bits, x, n):
    """Decodificatore in avanti scritto a parte: serve solo come controllo."""
    bits = list(bits); cnt = [[0, 0] for _ in range(NCTX)]
    out = []

    def bit(c):
        nonlocal x
        p0 = M // 2 if c is None else p0_di(*cnt[c])
        sl = x % M; b_ = int(sl >= p0)
        f = p0 if b_ == 0 else M - p0; cu = 0 if b_ == 0 else p0
        x = f * (x // M) + sl - cu
        while x < L:
            x = 2 * x + bits.pop()
        if c is not None:
            cnt[c][b_] += 1
        return b_

    def alb(nb, base):
        m = 1
        for _ in range(nb):
            m = 2 * m + bit(base + m)
        return m - (1 << nb)

    def alb_inv(nb, base):
        m, v = 1, 0
        for k in range(nb):
            bt = bit(base + m); m = 2 * m + bt; v |= bt << k
        return v

    def lun(base, ps):
        if not bit(base):
            return alb(3, base + 2 + ps * 8)
        if not bit(base + 1):
            return 8 + alb(3, base + 34 + ps * 8)
        return 16 + alb(8, base + 66)

    s = rep0 = 0
    while len(out) < n:
        p = len(out); ps = p % 4
        if not bit(IS_MATCH + s * 4 + ps):
            prevb = out[-1] if out else 0
            out.append(alb(8, LITC + (prevb >> 5) * 256)); s = stato_dopo(s, LIT); continue
        if bit(IS_REP + s):
            ln = lun(LEN_R, ps) + 2; ds = rep0; s = stato_dopo(s, REP_)
        else:
            ln = lun(LEN_M, ps) + 2
            sl = alb(6, SLOT + min(ln - 2, 3) * 64)
            if sl < 4:
                d0 = sl
            else:
                nb = (sl >> 1) - 1
                if nb <= 4:
                    rem = alb_inv(nb, SPEC + sl * 16)
                else:
                    rem = 0
                    for k in range(nb - 1, 3, -1):
                        rem |= bit(None) << k
                    rem |= alb_inv(4, ALIGN)
                d0 = base_slot(sl) + rem
            ds = d0 + 1; rep0 = ds; s = stato_dopo(s, MAT)
        for _ in range(ln):
            out.append(out[-ds])
    assert x == L and not bits
    return bytes(out)


def contenitore(n, x, bits, D=32):
    """KLZ1: n, D, x e il numero di bit in varint, poi i bit impacchettati."""
    def varint(v):
        o = bytearray()
        while True:
            c = v & 0x7F; v >>= 7; o.append(c | (0x80 if v else 0))
            if not v:
                return bytes(o)
    o = bytearray(b'KLZ1') + varint(n) + varint(D) + varint(x) + varint(len(bits))
    bb = bits + [0] * (-len(bits) % 8)
    o += bytes(int(''.join(map(str, bb[k:k + 8])), 2) for k in range(0, len(bb), 8))
    return bytes(o)


if __name__ == '__main__':
    dati = open(sys.argv[1], 'rb').read()
    print(f'{sys.argv[1]}: {len(dati)} byte | bzip2 -9 {len(bz2.compress(dati, 9))} | '
          f'xz -9e {len(lzma.compress(dati, preset=9 | lzma.PRESET_EXTREME))} | '
          f'lzma raw {len(lzma.compress(dati, format=lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA1, "preset": 9}]))}')
    for D in map(int, sys.argv[2:] or ['8', '32', '128']):
        bits, x, tok = comprimi(list(dati), D)
        assert decomprimi(bits, x, len(dati)) == dati
        k = contenitore(len(dati), x, bits, D)
        nl = sum(t[0] == LIT for t in tok); nm = sum(t[0] == MAT for t in tok); nr = len(tok) - nl - nm
        print(f'  D={D:4d}: klzma {len(k)} byte ({100 * len(k) / len(dati):.1f}%)  '
              f'gettoni {len(tok)}: {nl} letterali, {nm} match, {nr} rep0')
