#!/usr/bin/env python3
"""Modello Python della pipeline di kgzip2.kairos, bit per bit.

    python3 modello.py FILE [dim ...]
"""
import bz2, math, sys
from collections import Counter



def rle1(s):
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        L = j - i
        if L >= 4:
            out += [(L - 4) % 256, (L - 4) // 256, s[i], s[i], s[i], s[i]]; i = j
        else:
            out.append(s[i]); i += 1
    return out


def bwt_ingenua(s):
    n = len(s)
    rot = sorted(range(n), key=lambda o: s[o:] + s[:o])
    return [s[(o - 1) % n] for o in rot], rot.index(0)


def bwt(s):
    """Come bwt_ingenua (rotazioni ordinate, quelle identiche in ordine di
    indice), ma per raddoppio dei prefissi: O(n log^2 n) invece di confrontare
    rotazioni intere, cosi' il modello regge anche blocchi da 64 KiB."""
    n = len(s)
    if n == 0:
        return [], 0
    rango, h = list(s), 1
    sa = list(range(n))
    while True:
        chiave = [(rango[i], rango[(i + h) % n]) for i in range(n)]
        sa = sorted(range(n), key=chiave.__getitem__)       # stabile: a parita' l'indice
        nuovo, r = [0] * n, 0
        for j in range(1, n):
            r += chiave[sa[j]] != chiave[sa[j - 1]]
            nuovo[sa[j]] = r
        rango = nuovo
        if r == n - 1 or 2 * h >= n:
            break
        h *= 2
    return [s[(o - 1) % n] for o in sa], sa.index(0)


def mtf(s):
    tab = list(range(256)); m = []
    for c in s:
        p = tab.index(c); m.append(p); tab.insert(0, tab.pop(p))
    return m


def rle0(m):
    """Elementi di dst dal fondo alla cima."""
    dst, i, ng = [], 0, 0
    while i < len(m):
        if m[i] == 0:
            j = i
            while j < len(m) and m[j] == 0:
                j += 1
            dst += [j - i, 0]; i = j
        else:
            dst.append(m[i]); i += 1
        ng += 1
    return dst, ng


def gamma_bits(dst):
    """Come `codifica`: si consuma dst dalla cima; per x = e + 1 si spingono i
    bit bassi (dal meno significativo), un 1, L zeri."""
    bit = []
    for e in reversed(dst):
        x = e + 1; L = x.bit_length() - 1
        bit += [(x >> k) & 1 for k in range(L)] + [1] + [0] * L
    return bit


def blocco(s):
    r = rle1(list(s))
    out, idx = bwt(r)
    m = mtf(out)
    dst, ng = rle0(m)
    b = gamma_bits(dst)
    return (len(s), idx, len(r), ng, len(dst), len(b), b), m, dst


def h0(xs):
    c = Counter(xs); n = len(xs)
    return -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0


if __name__ == '__main__':
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from kgzip2.driver import dividi, atteso
    dati = open(sys.argv[1], 'rb').read()
    print(f'{sys.argv[1]}: {len(dati)} byte, bzip2 -9: {len(bz2.compress(dati, 9))}, '
          f'H0 dei byte {h0(dati):.2f} bit/byte')
    for dim in map(int, sys.argv[2:] or [1024, 2048, 4096, 8192]):
        gett = []
        for b in dividi(dati, dim):
            if len(b) >= 2:
                gett += blocco(b)[2]
        k = atteso(dati, dim)
        ideale = h0(gett) * len(gett) / 8
        print(f'  blocco {dim:5d}: {len(k):6d} byte ({100 * len(k) / len(dati):5.1f}%), '
              f'codice ideale d\'ordine 0 ~{ideale:6.0f} byte')
