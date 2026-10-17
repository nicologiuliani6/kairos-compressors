#!/usr/bin/env python3
"""Costo per stadio di `comprimi` (kgzip2) su un blocco: programmi troncati.

    python3 kgzip2/profilo.py FILE

Il programma k esegue i primi k stadi della pipeline e poi li disfa
(`uncall`), quindi il tempo e' andata e ritorno; la differenza fra programmi
consecutivi e' il costo di uno stadio.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from comune import kvm               # noqa: E402
from kgzip2 import driver            # noqa: E402

STADI = [
    ('RLE iniziale', '''    call impila(blocco, src, n)
    local int nsrc = 0
        nsrc += n
        call rle1(src, dst, nsrc, n1)
    delocal int nsrc = 0
    call togli_sentinella(src)
    call disimpila(dst, r, n1)'''),
    ('BWT: ordinamento', '    call ordina(offs, r, rk, rk2, tv, ide, cnt, pos, scarto, n1, nr)'),
    ('BWT: estrazione, inversa, pulizia', '''    call estrai(offs, r, out, n1, idx)
    uncall ordina(offs, r, rk, rk2, tv, ide, cnt, pos, scarto, n1, nr)
    uncall bwt_inversa(out, tv, cam, ric, r, freq, prima, visti, idx, n1, na)'''),
    ('move-to-front', '    call mtf(out, m, tab, n1, na)'),
    ('RLE degli zeri', '''    call impila(m, src, n1)
    local int nsrc = 0
        nsrc += n1
        call rle0(src, dst, nsrc, ng, nel)
    delocal int nsrc = 0
    call togli_sentinella(src)'''),
    ('Elias gamma', '    call codifica(dst, bit, nel, nb)'),
]
FIRMA = ('int blocco[], int r[], int offs[], int out[], int tv[], int cam[], int ric[], '
         'int m[], int rk[], int rk2[], int ide[], int tab[], int freq[], int prima[], '
         'int visti[], int cnt[], int pos[], stack scarto, stack src, stack dst, stack bit, '
         'int idx, int n1, int ng, int nel, int nb, int n, int na, int nr')


def tempo(k, blocco):
    src = driver.programma([len(blocco)], 'call')
    corpo = '\n'.join(c for _, c in STADI[:k]) or '    skip'
    src = src.replace('procedure main()', f'procedure parziale({FIRMA})\n{corpo}\n\nprocedure main()', 1)
    a = src.index('    call comprimi(')
    b = src.index('\n', a)
    args = src[a + len('    call comprimi('):b - 1]
    src = src[:a] + f'    call parziale({args})\n    uncall parziale({args})\n    {kvm.SEGNAPOSTO} -= 0' + src[b:]
    istr = [f'PUSHEQ blocco0[{j}] {v}' for j, v in enumerate(blocco) if v]
    righe = kvm.con_dati(kvm.compila(src), istr)
    for j, r in enumerate(righe):
        if r.split(None, 1)[1].strip() == f'MINEQ {kvm.SEGNAPOSTO} 0':
            righe[j:j + 1] = [r.split()[0] + '  ' + x.replace('PUSHEQ', 'MINEQ') for x in istr]
            break
    return kvm.esegui(righe, timeout=3600)[1]


if __name__ == '__main__':
    blocco = pathlib.Path(sys.argv[1]).read_bytes()[:driver.BLOCCO]
    print(f'blocco di {len(blocco)} byte')
    prima = 0.0
    for k in range(len(STADI) + 1):
        t = tempo(k, blocco)
        nome = STADI[k - 1][0] if k else '(carico e scarico)'
        print(f'  {nome:36s} {t - prima:6.2f} s   (cumulato {t:6.2f} s)', flush=True)
        prima = t
