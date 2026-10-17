#!/usr/bin/env python3
"""Riempie corpo.tex con i numeri di bench/risultati.json e di doc/dati/."""
import json
import pathlib
import re
import sys

QUI = pathlib.Path(__file__).resolve().parent
RADICE = QUI.parent.parent
DATI = RADICE / 'doc' / 'dati'
sys.path.insert(0, str(QUI.parent))
from riempi_comune import memoria, ntest   # noqa: E402
tex = (QUI / 'preambolo.tex').read_text().split(r'\title{')[0] + (QUI / 'corpo.tex').read_text()
B = {r['file']: r for r in json.loads((RADICE / 'bench' / 'risultati.json').read_text())}
v = lambda s: re.sub(r'(?<=\d)\.(?=\d)', '{,}', s)   # virgola decimale, solo fra cifre
ORDINE = ['tesi8k.tex', 'janus8k.c', 'readme8k.md', 'doppio8k.tex', 'periodico8k.txt',
          'cerchio64.pgm', 'cerchio.pgm', 'zeri4k.bin', 'casuale4k.bin']
NOMI = {'tesi8k.tex': 'tesi (\\LaTeX)', 'janus8k.c': 'Janus.c', 'readme8k.md': 'README',
        'doppio8k.tex': 'testo ripetuto 2 volte', 'periodico8k.txt': 'periodico',
        'cerchio64.pgm': 'immagine 64$\\times$64', 'cerchio.pgm': 'immagine 16$\\times$16',
        'zeri4k.bin': 'zeri', 'casuale4k.bin': 'casuale'}

# --- corpus -----------------------------------------------------------------------
T = [r'\begin{table}[t]', r'\centering\footnotesize', r'\setlength{\tabcolsep}{4.2pt}',
     r'\begin{tabular}{@{}lrrrrrrrrr@{}}', r'\toprule',
     r'file & byte & bzip2 & xz -9e & LZMA & kgzip2 & klzma & \% & comprimi & \kw{uncall} \\', r'\midrule']
d = {}
for f in ORDINE:
    r = B[f]
    assert r['klzma']['modello'] and r['klzma']['ritorno']
    k = r['klzma']['byte']
    d[f] = dict(n=r['byte'], bz=r['bzip2'], xz=r['xz'], raw=r['lzma_raw'], k=k, kg=r['kgzip2']['byte'])
    mig = min(r['bzip2'], r['xz'], r['lzma_raw'], r['kgzip2']['byte'], k)
    kk = rf'\textbf{{{k}}}' if k == mig else str(k)
    T.append(f"{NOMI[f]} & {r['byte']} & {r['bzip2']} & {r['xz']} & {r['lzma_raw']} & {r['kgzip2']['byte']} & {kk} & "
             + v(f"{100 * k / r['byte']:.1f} & {r['klzma']['comprimi'][1]:.1f} & {r['klzma']['uncall'][1]:.1f}") + r' \\')
T += [r'\bottomrule', r'\end{tabular}',
      r'\caption{Byte dopo la compressione, blocchi da 8 KiB, $D = 32$. LZMA è il codificatore di 7-Zip '
      r'senza intestazione (\kw{xz --format=raw}), xz aggiunge la propria; kgzip2 e klzma includono la propria (firma, tipo e lunghezza del frame) e 8 byte '
      r'di CRC. In grassetto il più piccolo. Tempi della VM in secondi; il blocco casuale è memorizzato e non '
      r'passa per la VM in decompressione. Ritorno identico e uscita uguale al modello in tutte le righe.}',
      r'\label{tab:corpus}', r'\end{table}']
rel = lambda a, b: v(f'{100 * (a - b) / b:.1f}')
commento = (
    rf"Sul testo klzma è alla pari con LZMA puro, che non ha né intestazione né CRC: {d['tesi8k.tex']['k']} contro "
    rf"{d['tesi8k.tex']['raw']} byte sulla tesi, {d['janus8k.c']['k']} contro {d['janus8k.c']['raw']} su Janus.c, "
    rf"{d['readme8k.md']['k']} contro {d['readme8k.md']['raw']} sul README; batte xz su tutti e tre "
    rf"({d['tesi8k.tex']['xz']}, {d['janus8k.c']['xz']}, {d['readme8k.md']['xz']}). Rispetto a kgzip2 il guadagno è "
    rf"netto: kgzip2 produce il {rel(d['tesi8k.tex']['kg'], d['tesi8k.tex']['k'])}\% di byte in più sulla tesi e il "
    rf"{rel(d['doppio8k.tex']['kg'], d['doppio8k.tex']['k'])}\% in più sul testo ripetuto."
    "\n\n"
    rf"Dove il dizionario conta klzma fa meglio di tutti: il testo ripetuto scende a {d['doppio8k.tex']['k']} byte "
    rf"(LZMA {d['doppio8k.tex']['raw']}, xz {d['doppio8k.tex']['xz']}, bzip2 {d['doppio8k.tex']['bz']}), il file "
    rf"periodico a {d['periodico8k.txt']['k']} (LZMA {d['periodico8k.txt']['raw']}). Il merito è dei conteggi: su "
    r"dati stazionari un modello che non dimentica converge più in fretta dello scorrimento di LZMA. Sui byte "
    rf"casuali il blocco memorizzato tiene il file a {d['casuale4k.bin']['k']} byte, meno di xz "
    rf"({d['casuale4k.bin']['xz']}) e di bzip2 ({d['casuale4k.bin']['bz']}). Sui file minuscoli pesano gli 8 byte di "
    rf"CRC (immagine 16$\times$16: {d['cerchio.pgm']['k']} contro {d['cerchio.pgm']['raw']}). bzip2 resta il "
    r"migliore sul testo normale da 8 KiB, dove la BWT ha un vantaggio sui blocchi piccoli.")

# --- varianti (modello) --------------------------------------------------------------
righe = (DATI / 'esperimenti_klzma.txt').read_text().splitlines()
intest = righe[0].split()
V = [r'\begin{table}[t]', r'\centering\footnotesize', r'\begin{tabular}{@{}l' + 'r' * len(intest) + '@{}}',
     r'\toprule', 'variante & ' + ' & '.join(x.replace('_', r'\_') for x in intest) + r' \\', r'\midrule']
for r in righe[1:]:
    parti = r.split()
    if len(parti) > len(intest) and all(x.isdigit() for x in parti[-len(intest):]):
        nome = ' '.join(parti[:-len(intest)]).replace('>', '$>$').replace('..', '--')
        V.append(nome + ' & ' + ' & '.join(parti[-len(intest):]) + r' \\')
V += [r'\bottomrule', r'\end{tabular}',
      r'\caption{Varianti misurate sul modello Python, con lo stesso rANS e gli stessi conteggi: i numeri '
      r'sono i byte che produrrebbe la versione Kairos (intestazione stimata). La lazy con $b_2 > \ell$ è '
      r'quella adottata. Lo stimatore KT è $p_0 = (n_0 + 1/2)/(n + 1)$ invece di $(n_0+1)/(n+2)$.}',
      r'\label{tab:varianti}', r'\end{table}']
varianti = (r"\paragraph{Che cosa conviene di LZMA.} Prima di portare in Kairos un pezzo di LZMA, lo si è misurato "
            r"sul modello. Solo la parse lazy paga davvero (Tabella~\ref{tab:varianti}): dall'1{,}7 al 2{,}2\% sul testo. "
            r"Le distanze rep1--rep3 e il letterale ``matched'' aggiungono contesti che su 8 KiB restano poco "
            r"allenati, e il risultato peggiora leggermente; lo stimatore KT aiuta sui dati regolari e peggiora "
            r"sul testo." "\n\n" + '\n'.join(V))


# --- profilo --------------------------------------------------------------------------
def profilo(path):
    out = []
    for r in path.read_text().splitlines()[1:]:
        m = re.match(r'\s+(.+?)\s+(-?[\d.]+) s\s+\(cumulato\s+([\d.]+) s\)', r)
        if m:
            out.append((m.group(1), float(m.group(2))))
    return out

nuovo, vecchio = profilo(DATI / 'profilo_klzma.txt'), profilo(DATI / 'profilo_klzma_v1.txt')
tot = sum(s for _, s in nuovo)
P = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrrr@{}}', r'\toprule',
     r'stadio & prima & ora & quota \\', r'\midrule']
for (nome, s), (_, s0) in zip(nuovo, vecchio):
    if abs(s) < 0.05 and abs(s0) < 0.05:
        continue
    P.append(f'{nome} & {s0:.2f} & {s:.2f} & {100 * max(s, 0) / tot:.0f}\\%'.replace('.', '{,}') + r' \\')
P += [r'\midrule', f'totale & {sum(s for _, s in vecchio):.2f} & {tot:.2f} & 100\\%'.replace('.', '{,}') + r' \\',
      r'\bottomrule', r'\end{tabular}',
      r"\caption{Costo per stadio su un blocco di 8 KiB della tesi, andata e ritorno di ogni stadio (secondi "
      r"di VM). ``prima'': istogramma calcolato rieseguendo la codifica in un modo di conteggio e disfacendola; "
      r"``ora'': conteggio in sola lettura, e codifica senza i modi.}",
      r'\label{tab:profilo}', r'\end{table}']
isto_v, isto_n = [s for n, s in vecchio if n.startswith('istogramma')][0], [s for n, s in nuovo if n.startswith('istogramma')][0]
profilo_txt = (r'\paragraph{Dove va il tempo.} La Tabella~\ref{tab:profilo} misura ogni stadio con programmi '
               r'troncati. Dopo le due ottimizzazioni la codifica rANS è la parte più cara: ogni bit è una '
               r"divisione, un aggiornamento del modello e, all'indietro, la stessa cosa al contrario."
               '\n\n' + '\n'.join(P))
isto = v(f'costava {isto_v:.1f} s su 8 KiB (andata e ritorno), questa ne costa {isto_n:.1f}')

# --- blocchi e par -----------------------------------------------------------------------
C = [r for r in json.loads((DATI / 'concorrenza.json').read_text()) if r['algoritmo'] == 'klzma']
tre = [r for r in C if r['blocchi'] == 3][0]
uno = [r for r in C if r['blocchi'] == 1][0]
blocchi = v(
    rf"\paragraph{{Più blocchi e \kw{{par}}.}} 20 KB della tesi in tre blocchi da 8 KiB, rami di un \kw{{par}}: "
    rf"{tre['par']['byte']} byte, compressione in {tre['par']['comprimi']:.1f} s di VM contro "
    rf"{tre['seq']['comprimi']:.1f} s in sequenza ({tre['seq']['comprimi'] / tre['par']['comprimi']:.2f}$\times$), "
    rf"decompressione in {tre['par']['uncall']:.1f} s contro {tre['seq']['uncall']:.1f} s "
    rf"({tre['seq']['uncall'] / tre['par']['uncall']:.2f}$\times$), su 2 core. Lo stesso file come blocco unico: "
    rf"{uno['par']['byte']} byte (bzip2 7154, xz 7528), in {uno['par']['comprimi']:.1f} s e {uno['par']['uncall']:.1f} s. "
    r"Con blocchi indipendenti ogni blocco riparte da un dizionario vuoto: è il prezzo del parallelismo, lo "
    r"stesso che paga xz in modalità multithread.")

abs_ = (rf"Su file da 8 KB klzma è alla pari con LZMA puro sul testo ({d['tesi8k.tex']['k']} contro "
        rf"{d['tesi8k.tex']['raw']} byte sulla tesi, CRC compreso), comprime molto meglio di kgzip2 "
        rf"({d['tesi8k.tex']['kg']}) e fa meglio dello stesso LZMA sui dati ripetitivi ({d['doppio8k.tex']['k']} "
        rf"contro {d['doppio8k.tex']['raw']} byte sul testo ripetuto). Il ritorno è identico byte per byte su "
        r"tutti i file, e l'eseguibile \kw{klzma} è un file unico che funziona senza Kairos installato e "
        r"lavora in streaming, con la memoria costante qualunque sia la dimensione del file.")
for k_, val in {'@@TAB@@': '\n'.join(T), '@@COMMENTO@@': commento, '@@BLOCCHI@@': blocchi, '@@ABS@@': abs_,
                '@@VARIANTI@@': varianti, '@@PROFILO@@': profilo_txt, '@@ISTO@@': isto,
                '@@MEMORIA@@': r'\paragraph{Streaming e memoria.} ' + memoria('klzma'), '@@NTEST@@': ntest()}.items():
    assert k_ in tex, k_
    tex = tex.replace(k_, val)
assert r"e resta a pochi punti da LZMA puro sul testo, dove la differenza viene dalla parse golosa e dai contesti mancanti più che dalla reversibilità." in tex
tex = tex.replace(r"e resta a pochi punti da LZMA puro sul testo, dove la differenza viene dalla parse golosa e dai contesti mancanti più che dalla reversibilità.",
                  r"ed è alla pari con LZMA puro sul testo: la reversibilità, alla fine, non costa rapporto di compressione.")
assert '@@' not in tex and '—' not in tex
(QUI / 'klzma_pieno.tex').write_text(tex)
print('ok')
