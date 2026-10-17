#!/usr/bin/env python3
"""Costo per stadio di klzma su un blocco (andata e ritorno di ogni prefisso).

    python3 bench/profilo_klzma.py FILE
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from comune import kvm
from klzma import driver

STADI = [
    ('catene di hash', '    call catene(b, prev, head, n)'),
    ('parse (con lazy)', '    call analizza(b, prev, n, D, ty, ln, ds, st, rp, ntok, scarto)'),
    ('catene disfatte', '    uncall catene(b, prev, head, n)'),
    ('istogramma del modello', '    call conta_modello(b, n, ty, ln, ds, st, ntok, slotbase, cnt, pot2)'),
    ('codifica (rANS)', '    x += 65536\n    call codifica(b, n, ty, ln, ds, st, rp, ntok, slotbase, cnt, pot2, bitst, x, nb)'),
]
FIRMA = ('int b[], int n, int D, int prev[], int head[], int ty[], int ln[], int ds[], int st[], '
         'int rp[], int slotbase[], int cnt[], int pot2[], stack scarto, stack bitst, '
         'int x, int nb, int ntok')

dati = pathlib.Path(sys.argv[1]).read_bytes()[:driver.BLOCCO]
prima = 0.0
print(f'blocco di {len(dati)} byte')
for k in range(1, len(STADI) + 1):
    src = driver.programma([len(dati)], driver.D_PREDEFINITO, 'call')
    corpo = '\n'.join(c for _, c in STADI[:k])
    src = src.replace('procedure main()', f'procedure parziale({FIRMA})\n{corpo}\n\nprocedure main()\n    int ntok', 1)
    chiamata = 'call comprimi(' + ', '.join(f'{a}0' for a in driver.NOMI) + ')'
    arg = ', '.join(f'{a}0' for a in driver.NOMI) + ', ntok'
    src = src.replace('    ' + chiamata, f'    call parziale({arg})\n    uncall parziale({arg})')
    istr = [f'PUSHEQ b0[{j}] {v}' for j, v in enumerate(dati) if v]
    # dopo l'uncall il blocco e' di nuovo pieno: lo si svuota con le stesse istruzioni
    righe = kvm.compila(src.replace('    show(x0)', f'    {kvm.SEGNAPOSTO} -= 0\n    show(x0)'))
    righe = kvm.con_dati(righe, istr)
    for j, r in enumerate(righe):
        if r.split(None, 1)[1].strip() == f'MINEQ {kvm.SEGNAPOSTO} 0':
            righe[j:j + 1] = [r.split()[0] + '  ' + x.replace('PUSHEQ', 'MINEQ') for x in istr]
            break
    _, t = kvm.esegui(righe, timeout=3600)
    print(f'  {STADI[k - 1][0]:26s} {t - prima:6.2f} s   (cumulato {t:6.2f} s)', flush=True)
    prima = t
