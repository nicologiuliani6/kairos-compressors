#!/usr/bin/env python3
"""Fase di build dei binari nativi: traduce le librerie Kairos in bytecode.

    python3 nativo/genera.py         -> nativo/gen/kgzip2_lib.h, nativo/gen/klzma_lib.h

Il frontend di Kairos (Python) serve solo qui. Si traduce un programma con un
blocco, si tengono le procedure della libreria (fra START e il main) e le si
scrive come stringa C; il main lo genera il binario a ogni gruppo di blocchi.
L'ordine delle procedure e' quello dei driver (comune/libreria.py).
"""
import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from comune import kvm                  # noqa: E402
from kgzip2 import driver as KG         # noqa: E402
from klzma import driver as KL          # noqa: E402
from klzma import modello as ML         # noqa: E402

GEN = RADICE / 'nativo' / 'gen'


def libreria(sorgente):
    righe = kvm.compila(sorgente)
    assert righe[0].split()[1] == 'START', righe[0]
    fine = next(i for i, r in enumerate(righe) if r.split()[1:] == ['PROC', 'main'])
    return righe[1:fine]


def stringa_c(nome, righe):
    out = [f'static const char {nome}[] =']
    for r in righe:
        out.append('    "' + r.replace('\\', '\\\\').replace('"', '\\"') + '\\n"')
    out[-1] += ';'
    return '\n'.join(out) + '\n'


def scrivi(file, testo):
    GEN.mkdir(exist_ok=True)
    p = GEN / file
    if not p.exists() or p.read_text() != testo:
        p.write_text(testo)


kg = libreria(KG.programma([2], 'call'))
scrivi('kgzip2_lib.h', '/* generato da nativo/genera.py: non modificare */\n' + stringa_c('KGZIP2_LIBRERIA', kg))

kl = libreria(KL.programma([2], KL.D_PREDEFINITO, 'call'))
slot = ', '.join(str(ML.base_slot(s)) if s else '0' for s in range(64))
scrivi('klzma_lib.h', '/* generato da nativo/genera.py: non modificare */\n'
       f'#define KLZMA_HSIZE {ML.HSIZE}\n#define KLZMA_NCNT {KL.NCNT}\n'
       f'static const long long KLZMA_SLOTBASE[64] = {{ {slot} }};\n' + stringa_c('KLZMA_LIBRERIA', kl))
print(f'kgzip2: {len(kg)} righe di bytecode, klzma: {len(kl)}')
