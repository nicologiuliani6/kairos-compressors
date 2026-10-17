#!/usr/bin/env python3
"""Varianti di klzma sul modello Python: quanto rende ciascun miglioramento.

    python3 bench/esperimenti_klzma.py FILE...

Ogni variante e' misurata con lo stesso rANS e lo stesso modello a conteggi:
i numeri sono i bit esatti che produrrebbe la versione Kairos.
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from klzma import modello as M

LIT, MAT, REP = 0, 1, 2


def parse(b, D=32, lazy=0, nrep=1):
    n = len(b)
    prev = [0] * n; head = [0] * M.HSIZE
    for i in range(n - 2):
        h = M.h3(b, i); prev[i] = head[h]; head[h] = i + 1

    def migliore(i):
        best = bd = 0; c, d = prev[i], 0
        while c > 0 and d < D:
            j = c - 1; L = M.lung(b, i, j)
            if L > best:
                best, bd = L, i - j
            c = prev[j]; d += 1
        return best, bd

    tok, i, reps, s = [], 0, [0, 0, 0, 0], 0
    while i < n:
        best, bd = migliore(i)
        # ripetizioni: la piu' lunga fra rep0..rep(nrep-1)
        rl, ri = 0, -1
        for k in range(nrep):
            if reps[k] > 0:
                L = M.lung(b, i, i - reps[k])
                if L > rl:
                    rl, ri = L, k
        if lazy and best >= 3 and i + 1 < n:
            b2, _ = migliore(i + 1)
            if b2 > best + lazy - 1 and not (rl >= 2 and rl + 1 >= best):
                tok.append((LIT, 1, 0, s, list(reps), i, 0)); s = M.stato_dopo(s, LIT); i += 1
                continue
        if rl >= 2 and rl + 1 >= best:
            t, ln, ds, k = REP, rl, reps[ri], ri
        elif best >= 3:
            t, ln, ds, k = MAT, best, bd, 0
        else:
            t, ln, ds, k = LIT, 1, 0, 0
        tok.append((t, ln, ds, s, list(reps), i, k))
        if t == MAT:
            reps = [ds] + reps[:3]
        elif t == REP and k > 0:
            reps = [reps[k]] + reps[:k] + reps[k + 1:]
        s = M.stato_dopo(s, t)
        i += ln
    return tok


# contesti aggiuntivi in coda a quelli di klzma
EXTRA = M.NCTX
IS_REP0, IS_REP1, IS_REP2 = EXTRA, EXTRA + 12, EXTRA + 24
MLIT = EXTRA + 36                  # letterali "matched": 8 x 768
NCTX = MLIT + 8 * 768


def lett_matched(v, mb, base):
    """Il letterale di LZMA dopo un match: finche' i bit coincidono con quelli
    del byte alla distanza rep0, il contesto include il bit atteso."""
    out, sym, uguali = [], 1, True
    for k in range(7, -1, -1):
        bit = (v >> k) & 1
        if uguali:
            mbit = (mb >> k) & 1
            out.append((base + 256 + mbit * 256 + sym, bit))
            if bit != mbit:
                uguali = False
        else:
            out.append((base + sym, bit))
        sym = 2 * sym + bit
    return out


def decisioni(b, tok, matched=False, lc=3, nrep=1):
    tutte = []
    for t, ln, ds, s, reps, p, k in tok:
        ps = p % 4
        out = [(M.IS_MATCH + s * 4 + ps, int(t != LIT))]
        if t == LIT:
            prevb = b[p - 1] if p > 0 else 0
            ctx = prevb >> (8 - lc) if lc else 0
            if matched and s >= 7 and reps[0] > 0:
                out += lett_matched(b[p], b[p - reps[0]], MLIT + ctx * 768)
            else:
                out += M.albero(b[p], 8, M.LITC + ctx * 256)
        else:
            out.append((M.IS_REP + s, int(t == REP)))
            if t == REP:
                if nrep > 1:
                    out.append((IS_REP0 + s, int(k > 0)))
                    if k > 0:
                        out.append((IS_REP1 + s, int(k > 1)))
                        if k > 1:
                            out.append((IS_REP2 + s, int(k > 2)))
                out += M.lunghezza(ln - 2, M.LEN_R, ps)
            else:
                out += M.lunghezza(ln - 2, M.LEN_M, ps)
                d0 = ds - 1; sl = M.slot_di(d0)
                out += M.albero(sl, 6, M.SLOT + min(ln - 2, 3) * 64)
                if sl >= 4:
                    nb = (sl >> 1) - 1; rem = d0 - M.base_slot(sl)
                    if nb <= 4:
                        out += M.albero_inv(rem, nb, M.SPEC + sl * 16)
                    else:
                        for kk in range(nb - 1, 3, -1):
                            out.append((None, (rem >> kk) & 1))
                        out += M.albero_inv(rem & 15, 4, M.ALIGN)
        tutte.append(out)
    return tutte


def bit_codificati(dec, a2=2):
    """Lunghezza esatta in bit dell'uscita rANS; a2 = 2a dello stimatore
    p0 = (n0 + a) / (n + 2a)."""
    cnt = [[0, 0] for _ in range(NCTX)]
    for d in dec:
        for c, bit in d:
            if c is not None:
                cnt[c][bit] += 1
    x, nbit = M.L, 0
    for d in reversed(dec):
        for c, bit in reversed(d):
            if c is None:
                p0 = M.M // 2
            else:
                cnt[c][bit] -= 1
                n0, n1 = cnt[c]
                p0 = 1 + ((2 * n0 + a2) * (M.M - 2)) // (2 * (n0 + n1) + 2 * a2)
            f = p0 if bit == 0 else M.M - p0
            cu = 0 if bit == 0 else p0
            while x >= 32 * f:
                nbit += 1; x >>= 1
            x = (x // f) * M.M + cu + (x % f)
    return nbit


VARIANTI = [
    ('golosa (prima versione)', dict()),
    ('+ lazy, b2 > best (scelta)', dict(lazy=1)),
    ('+ lazy, b2 > best + 1', dict(lazy=2)),
    ('+ stimatore KT (a = 1/2)', dict(a2=1)),
    ('+ letterale matched', dict(matched=True)),
    ('+ rep0..rep3', dict(nrep=4)),
    ('lazy + tutto il resto', dict(lazy=1, a2=1, matched=True, nrep=4)),
]


def misura(b, lazy=0, a2=2, matched=False, nrep=1, D=32):
    tok = parse(b, D, lazy, nrep)
    return (bit_codificati(decisioni(b, tok, matched, 3, nrep), a2) + 7) // 8 + 9 + 13


if __name__ == '__main__':
    import lzma
    RAW = [{'id': lzma.FILTER_LZMA1, 'preset': 9 | lzma.PRESET_EXTREME}]
    file = sys.argv[1:]
    tot = {v[0]: 0 for v in VARIANTI}
    print(f'{"":28s}' + ''.join(f'{pathlib.Path(f).name[:11]:>12s}' for f in file))
    righe = {v[0]: [] for v in VARIANTI}
    for f in file:
        b = list(open(f, 'rb').read())
        for nome, kw in VARIANTI:
            righe[nome].append(misura(b, **kw))
    for nome, _ in VARIANTI:
        print(f'{nome:28s}' + ''.join(f'{x:12d}' for x in righe[nome]))
    print(f'{"LZMA (7-Zip, raw)":28s}' + ''.join(
        f'{len(lzma.compress(open(f, "rb").read(), format=lzma.FORMAT_RAW, filters=RAW)):12d}' for f in file))
