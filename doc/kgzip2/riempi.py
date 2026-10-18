#!/usr/bin/env python3
"""Riempie kgzip2.tex con i numeri dei log."""
import json, math, re, sys, pathlib, bz2
QUI = pathlib.Path(__file__).resolve().parent
RADICE = QUI.parent.parent
DATI = RADICE / 'doc' / 'dati'
sys.path.insert(0, str(RADICE))
from kgzip2 import modello, driver as kgzip
sys.path.insert(0, str(QUI.parent))
from riempi_comune import efficienza, livelli, manomissione, memoria, ntest
BENCH = {r['file']: r for r in json.loads((RADICE / 'bench' / 'risultati.json').read_text())}

tex = (QUI / 'kgzip2.tex').read_text()


def leggi(path, tipo_sost=None):
    d = {}
    for v, t, n, s in re.findall(r'^(\w+) (\w+) n=(\d+) vm_min=([\d.]+)', path.read_text(), re.M):
        d[(v, t, int(n))] = float(s)
    return d

S = leggi(DATI / 'serie_sort.log')
T = leggi(DATI / 'serie_testo_repo.log')
R = leggi(DATI / 'serie_raddoppio_finale.log')
D = {}
for (v, t, n), s in S.items():
    if v in ('bolle', 'bolle_ae', 'fusione') and t != 'testo':
        D[(v, t, n)] = s
for k, s in T.items():
    D[k] = s
for k, s in R.items():
    D[k] = s

VAR = ['bolle', 'bolle_ae', 'fusione', 'raddoppio']
NOMI = {'bolle': 'bolle', 'bolle_ae': 'bolle+u.a.', 'fusione': 'fusione', 'raddoppio': 'raddoppio'}


def cella(v, t, n):
    s = D.get((v, t, n))
    if s is None:
        return '--'
    return f'{s:.2f}'.replace('.', '{,}') if s < 100 else f'{s:.0f}'


def tabella(tipi, ns, etichetta, didascalia):
    col = 'r' + ('|' + 'rrrr') * len(tipi)
    L = [r'\begin{table}[t]', r'\centering\footnotesize', r'\setlength{\tabcolsep}{4pt}',
         r'\begin{tabular}{@{}' + col.replace('|', r'@{\hspace{8pt}}') + r'@{}}', r'\toprule']
    L.append(' & ' + ' & '.join(r'\multicolumn{4}{c}{' + t + '}' for t in tipi) + r' \\')
    L.append(''.join(rf'\cmidrule(lr){{{2 + 4 * i}-{5 + 4 * i}}}' for i in range(len(tipi))))
    L.append('$n$ & ' + ' & '.join(NOMI[v] for _ in tipi for v in VAR) + r' \\')
    L.append(r'\midrule')
    for n in ns:
        L.append(f'{n} & ' + ' & '.join(cella(v, t, n) for t in tipi for v in VAR) + r' \\')
    L += [r'\bottomrule', r'\end{tabular}', rf'\caption{{{didascalia}}}', rf'\label{{{etichetta}}}',
          r'\end{table}']
    return '\n'.join(L)


NS = [16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192]
tab_sort = tabella(['periodico', 'costante'], NS, 'tab:sort1',
                   r'Tempo (s) di ordinamento in avanti e all\'indietro, dati ripetitivi. '
                   r'``--\'\' = non misurato (oltre i 30 s per esecuzione, o oltre le dimensioni utili).') + '\n\n' + \
    tabella(['casuale', 'testo'], NS, 'tab:sort2',
            r'Tempo (s) di ordinamento in avanti e all\'indietro, dati casuali e testo.')


def pendenza(v, t, minimo=None):
    pts = sorted((n, s) for (vv, tt, n), s in D.items() if vv == v and tt == t and s >= 0.05)
    if minimo:
        pts = [p for p in pts if p[0] >= minimo]
    pts = pts[-4:]
    if len(pts) < 2:
        return None
    xs = [math.log(n) for n, _ in pts]; ys = [math.log(s) for _, s in pts]
    mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def grafico(t, titolo):
    stili = {'bolle': 'mark=square*, black', 'bolle_ae': 'mark=triangle*, black!60',
             'fusione': 'mark=o, blue!70!black', 'raddoppio': 'mark=*, red!70!black'}
    L = [r'\begin{tikzpicture}', r'\begin{loglogaxis}[width=7.4cm, height=6.2cm, '
         rf'title={{{titolo}}}, xlabel={{$n$}}, ylabel={{secondi}}, log basis x=2, '
         r'xmin=12, xmax=11000, ymin=0.008, ymax=60, grid=major, grid style={black!12}, '
         r'legend style={font=\footnotesize, at={(0.98,0.02)}, anchor=south east}, '
         r'tick label style={font=\footnotesize}, label style={font=\small}]']
    for v in VAR:
        pts = sorted((n, s) for (vv, tt, n), s in D.items() if vv == v and tt == t and n >= 16)
        if not pts:
            continue
        L.append(rf'\addplot[{stili[v]}, thick, mark size=1.6pt] coordinates {{' +
                 ' '.join(f'({n},{max(s, 0.01)})' for n, s in pts) + '};')
        L.append(rf'\addlegendentry{{{NOMI[v]}}}')
    L += [r'\end{loglogaxis}', r'\end{tikzpicture}']
    return '\n'.join(L)


plot = (r'\begin{figure}[t]' '\n' r'\centering' '\n' + grafico('periodico', 'periodico (periodo 6)') +
        '\n\\hfill\n' + grafico('casuale', 'casuale') + '\n' +
        r'\caption{Tempo di ordinamento (andata e ritorno) in scala log-log. Una legge di potenza '
        r'appare come una retta e la pendenza ne è l\'esponente.}' '\n' r'\label{fig:sort}' '\n' r'\end{figure}')

pb = pendenza('bolle', 'periodico', 16); pba = pendenza('bolle_ae', 'periodico')
pf = pendenza('fusione', 'periodico'); pr = pendenza('raddoppio', 'periodico', 512)
pfc = pendenza('fusione', 'casuale', 512); prc = pendenza('raddoppio', 'casuale', 512)
prt = pendenza('raddoppio', 'testo', 512); pft = pendenza('fusione', 'testo', 512)
f = lambda x: f'{x:.2f}'.replace('.', '{,}')
g = lambda s: (f'{s:.2f}' if s < 10 else f'{s:.1f}').replace('.', '{,}')
commento_sort = (
    rf"Sui dati periodici le pendenze fra gli ultimi punti misurati sono {f(pb)} per il bubble sort "
    rf"(il cubo atteso, come nel capitolo 4), {f(pba)} con l'uscita anticipata (che non aiuta: i prefissi "
    rf"comuni sono lunghi quanto il blocco), {f(pf)} per il merge sort ($n^2\log n$) e {f(pr)} per il "
    rf"raddoppio ($n\log n$). A $n = 64$ il bubble sort impiega {g(D[('bolle','periodico',64)])} s e il raddoppio "
    rf"{g(D[('raddoppio','periodico',64)])} s; il merge sort a $n = 256$ ne impiega {g(D[('fusione','periodico',256)])}, "
    rf"il raddoppio {g(D[('raddoppio','periodico',256)])}. Il raddoppio ordina un blocco periodico di 8192 byte in "
    rf"{g(D[('raddoppio','periodico',8192)])} s, ed è l'unico che ci arriva."
    "\n\n"
    rf"Sui dati poco ripetitivi l'uscita anticipata basta già a rendere il confronto quasi costante, e il merge "
    rf"sort cresce con pendenza {f(pfc)} sui casuali e {f(pft)} sul testo. Il raddoppio resta comunque il più "
    rf"veloce (pendenza {f(prc)} sui casuali, {f(prt)} sul testo), perché si ferma appena i ranghi sono "
    rf"distinti: a $n = 4096$ casuale {g(D[('raddoppio','casuale',4096)])} s contro {g(D[('fusione','casuale',4096)])}, "
    rf"sul testo {g(D[('raddoppio','testo',4096)])} s contro {g(D[('fusione','testo',4096)])}. "
    r"Ha un costo fisso per giro legato alle $n_r \ge 256$ chiavi del counting sort, che pesa sui blocchi piccoli.")

# --- corpus --------------------------------------------------------------
ORDINE = ['tesi8k.tex', 'janus8k.c', 'readme8k.md', 'doppio8k.tex', 'periodico8k.txt',
          'cerchio64.pgm', 'cerchio.pgm', 'zeri4k.bin', 'casuale4k.bin']
righe = [BENCH[f] for f in ORDINE]
NOMIF = {'tesi8k.tex': 'tesi (\\LaTeX)', 'janus8k.c': 'Janus.c', 'readme8k.md': 'README',
         'doppio8k.tex': 'testo ripetuto 2 volte', 'periodico8k.txt': 'periodico',
         'cerchio64.pgm': 'immagine 64$\\times$64', 'cerchio.pgm': 'immagine 16$\\times$16',
         'zeri4k.bin': 'zeri', 'casuale4k.bin': 'casuale'}
corp = [r'\begin{table}[t]', r'\centering\footnotesize', r'\setlength{\tabcolsep}{4.5pt}',
        r'\begin{tabular}{@{}lrrrrrrrr@{}}', r'\toprule',
        r'file & byte & bzip2 -9 & kgzip2 & \% & bit/byte & ordine 0 & comprimi & \kw{uncall} \\',
        r'\midrule']
rapporti = {}
inv = []
tutti_ok = True
for r in righe:
    nome, n, bz, kg = r['file'], r['byte'], r['bzip2'], r['kgzip2']['byte']
    t1, t2 = r['kgzip2']['comprimi'][1], r['kgzip2']['uncall'][1]
    dati = (RADICE / 'test' / 'corpus' / nome).read_bytes()
    bl = [modello.blocco(b) for b in kgzip.dividi(dati, 8192) if len(b) >= 2]
    gett = [e for x in bl for e in x[2]]
    ideale = modello.h0(gett) * len(gett) / 8
    tutti_ok &= r['kgzip2']['modello'] and r['kgzip2']['ritorno']
    rapporti[nome] = (kg / n, int(bz) / n)
    if t1 > 1:
        inv.append(t2 / t1)
    num = (f'{n} & {bz} & {kg} & {100 * kg / n:.1f} & {8 * kg / n:.2f} & '
           f'{100 * ideale / n:.1f} & {t1:.1f} & {t2:.1f}').replace('.', '{,}')
    corp.append(f'{NOMIF[nome]} & ' + num + r' \\')
corp += [r'\bottomrule', r'\end{tabular}',
         r'\caption{Opzioni predefinite (\kw{-9}): ogni file è un blocco solo. ``\%\'\' è la dimensione compressa rispetto all\'originale; '
         r'``ordine 0\'\' è la dimensione che avrebbero gli stessi gettoni con un codice entropico ideale '
         r'd\'ordine 0 (senza intestazioni). Tempi in secondi del comando \kw{kgzip2}, dall\'avvio alla fine. '
         r'In tutte le righe il '
         r'ritorno è identico byte per byte e l\'uscita compressa coincide con il modello.}',
         r'\label{tab:corpus}', r'\end{table}']
assert tutti_ok
tab_corpus = '\n'.join(corp)
pc = lambda k: f'{100 * rapporti[k][0]:.1f}'.replace('.', '{,}') + r'\%'
pz = lambda k: f'{100 * rapporti[k][1]:.1f}'.replace('.', '{,}') + r'\%'
commento_corpus = (
    rf"Sul testo kgzip2 riduce i file a {pc('janus8k.c')}--{pc('readme8k.md')}, contro "
    rf"{pz('janus8k.c')}--{pz('readme8k.md')} di bzip2. Sui dati molto regolari fa meglio di bzip2: "
    rf"l'immagine 64$\times$64 scende a {pc('cerchio64.pgm')} contro {pz('cerchio64.pgm')}, il file periodico a "
    rf"{pc('periodico8k.txt')} contro {pz('periodico8k.txt')}, gli zeri a {pc('zeri4k.bin')} contro {pz('zeri4k.bin')}; "
    r"qui conta anche l'intestazione più corta. Sul testo ripetuto due volte bzip2 sfrutta meglio la "
    rf"ripetizione ({pz('doppio8k.tex')} contro {pc('doppio8k.tex')}); sui byte casuali il blocco memorizzato "
    rf"tiene il file a {pc('casuale4k.bin')}, contro {pz('casuale4k.bin')} di bzip2. La colonna ``ordine 0'' mostra quanto si guadagnerebbe "
    r"sostituendo il codice gamma con un codice adattivo: sul testo quattro o cinque punti, quasi tutta la distanza da bzip2.")

# --- profilo ----------------------------------------------------------------
prof = (DATI / 'profilo_kgzip2.txt').read_text().splitlines()
pr_righe = []
tot = 0
for r in prof[1:]:
    m = re.match(r'\s+(.+?)\s+(-?[\d.]+) s\s+\(cumulato\s+([\d.]+) s\)', r)
    if m:
        pr_righe.append((m.group(1), float(m.group(2)))); tot = float(m.group(3))
tp = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrr@{}}', r'\toprule',
      r'stadio & secondi & quota \\', r'\midrule']
for nome, s in pr_righe:
    if nome.startswith('(carico'):
        continue
    tp.append(f'{nome} & {s:.2f} & {100 * s / tot:.0f}\\%'.replace('.', '{,}') + r' \\')
tp += [r'\midrule', f'totale & {tot:.2f} & 100\\%'.replace('.', '{,}') + r' \\', r'\bottomrule',
       r'\end{tabular}',
       r'\caption{Costo per stadio su un blocco di 8192 byte della tesi, andata e ritorno '
       r'(\kw{call} e \kw{uncall} dello stadio). La seconda riga della BWT comprende l\'ordinamento '
       r'disfatto e rifatto dentro \kw{bwt}.}', r'\label{tab:profilo}', r'\end{table}']
quota_sort = sum(s for n, s in pr_righe if n.startswith('BWT')) / tot
nuovo_bwt = sum(s for n, s in pr_righe if n.startswith('BWT'))
vecchio_bwt = sum(float(x) for x in re.findall(r'BWT[^\n]*?\s(-?[\d.]+) s\s+\(cumulato', (DATI / 'profilo_kgzip2_raddoppio_v1.txt').read_text()))
medio_bwt = sum(float(x) for x in re.findall(r'BWT[^\n]*?\s(-?[\d.]+) s\s+\(cumulato', (DATI / 'profilo_kgzip2_v2.txt').read_text()))
tot_v2 = float(re.findall(r'cumulato\s+([\d.]+) s', (DATI / 'profilo_kgzip2_v2.txt').read_text())[-1])
virgola = lambda t: re.sub(r'(?<=\d)\.(?=\d)', '{,}', t)
tab_profilo = '\n'.join(tp) + '\n\n' + virgola(
    rf"La BWT, ordinamento compreso, è il {100 * quota_sort:.0f}\% del tempo. Dentro \kw{{bwt}} "
    r"l'ordinamento si esegue due volte (\kw{call} e \kw{uncall}), e altrettante nel verso opposto: "
    r"è il prezzo della pulizia. "
    rf"Nella prima versione del raddoppio, che ripuliva ogni giro ricalcolandolo, le due righe della BWT "
    rf"costavano {vecchio_bwt:.1f} s; mettendo su \kw{{scarto}} i dati dei giri conclusi scendevano a "
    rf"{medio_bwt:.1f} s, e con un solo counting sort per giro e gli interventi di §\ref{{sec:efficienza}} "
    rf"sono {nuovo_bwt:.1f} s. L'intera andata e ritorno di tutti gli stadi è passata da {tot_v2:.1f} a {tot:.1f} s.")

# --- concorrenza -------------------------------------------------------------------
conc = {}
for r in json.loads((DATI / 'concorrenza.json').read_text()):
    if r['algoritmo'] == 'kgzip2':
        conc[('par', r['blocco'])] = (r['par']['comprimi'], r['par']['uncall'])
        conc[('seq', r['blocco'])] = (r['seq']['comprimi'], r['seq']['uncall'])
tc = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrrrrrr@{}}', r'\toprule',
      r'& \multicolumn{3}{c}{comprimi (s)} & \multicolumn{3}{c}{\kw{uncall} (s)} \\',
      r'\cmidrule(lr){2-4}\cmidrule(lr){5-7}',
      r'blocchi & sequenziale & \kw{par} & guadagno & sequenziale & \kw{par} & guadagno \\', r'\midrule']
for b in (4096, 2048):
    if ('par', b) in conc and ('seq', b) in conc:
        (pc1, pu1), (sc1, su1) = conc[('par', b)], conc[('seq', b)]
        tc.append(f'{8192 // b} da {b} & {sc1:.1f} & {pc1:.1f} & {sc1 / pc1:.2f}$\\times$ & '
                  f'{su1:.1f} & {pu1:.1f} & {su1 / pu1:.2f}$\\times$'.replace('.', '{,}') + r' \\')
tc += [r'\bottomrule', r'\end{tabular}',
       r'\caption{Gli 8 KiB della tesi divisi in blocchi, come rami di un \kw{par} o uno dopo '
       r'l\'altro. Stesso programma, stessi byte prodotti; tempi della VM, macchina a 2 core.}', r'\label{tab:conc}',
       r'\end{table}']
inv = [r['kgzip2']['uncall'][1] / r['kgzip2']['comprimi'][1] for r in righe if r['kgzip2']['comprimi'][1] >= 1]
rinv = sum(inv) / len(inv)
rinv_s = f'{rinv:.2f}'.replace('.', '{,}')
concorrenza = '\n'.join(tc) + '\n\n' + (
    r"I blocchi sono indipendenti e il \kw{par} li esegue su thread diversi in entrambi i versi: "
    r"anche la decompressione è parallela senza che nessuno l'abbia scritta, perché l'inverso di un "
    r"\kw{par} è il \kw{par} degli inversi. Con 2 core il guadagno non può superare $2\times$; il "
    r"capitolo 4 ha già mostrato, su 6 core, che il \kw{par} raggiunge il 91\% del throughput di "
    r"processi indipendenti." "\n\n"
    rf"Quanto al costo dell'inverso: sui file della Tabella~\ref{{tab:corpus}} con almeno un secondo di "
    rf"compressione, l'\kw{{uncall}} costa in media {rinv_s} volte la compressione nella VM. Non è un "
    r"decodificatore più lento: ripete le stesse operazioni in ordine opposto. Nella prima versione i bit "
    r"passavano dal parser, una riga ciascuno, e la decompressione degli 8 KiB della tesi pagava 5 s di "
    r"frontend in più; con i dati scritti direttamente nel bytecode quel costo è sparito.")

# --- correttezza, abstract, conclusioni --------------------------------------------
correttezza = (
    r"La BWT con le quattro varianti dell'ordinamento è stata confrontata con il riferimento su 300 casi "
    r"(byte casuali con alfabeto fino a 256 simboli, testo, blocchi periodici, costanti, alfabeto di tre "
    r"simboli; $n$ fino a 400): nessuna discordanza, e le quattro varianti danno lo stesso \kw{offs}, la "
    r"stessa colonna e lo stesso \kw{idx} anche sui blocchi periodici, dove molte rotazioni sono identiche. "
    rf"La suite di test della repository (\kw{{test/test\_completo.py}}, {ntest()} controlli, nessuno fallito) "
    r"comprime e decomprime con entrambi gli algoritmi i 9 file della Tabella~\ref{tab:corpus} e 13 casi "
    r"limite (file vuoto, di 1 e 2 byte, corse di esattamente 4, corse di 300 byte, quasi-corse, tutti i 256 "
    r"byte, due blocchi in \kw{par}): l'uscita compressa coincide byte per byte con il modello, il ritorno "
    r"con l'originale, e ogni file viene poi alterato e troncato per controllare che sia rifiutato. Prova "
    r"anche i binari nativi (stesso bytecode del driver Python, stessi byte del modello su tutti i casi) e "
    r"lo streaming: un file a più frame compresso con gruppi diversi dà gli stessi byte, si "
    r"decomprime con gruppi diversi e concatenato ad altri flussi, rifiuta i dati estranei in coda, e su un "
    r"file a più frame ogni troncamento e un byte alterato in ogni posizione vengono rifiutati. Infine i "
    r"comandi veri con le opzioni di bzip2 e di xz e i loro codici d'uscita (rimozione dell'ingresso, "
    r"\kw{-k}, \kw{-f}, \kw{-c}, \kw{-s}, \kw{-T}, filtro da stdin a più blocchi, flussi concatenati, \kw{-t} su "
    r"file alterati e troncati, suffissi sconosciuti, nessuna uscita parziale).")
abstract_num = (
    rf"Su 9 file il ritorno è identico byte per byte. Su file di testo da 8 KiB kgzip2 arriva a "
    rf"{pc('janus8k.c')}--{pc('readme8k.md')} della dimensione originale (bzip2: {pz('janus8k.c')}--{pz('readme8k.md')}) "
    r"e sui dati molto regolari fa meglio di bzip2; ordinare un blocco periodico da 64 byte passa da "
    rf"{g(D[('bolle','periodico',64)])} s a {g(D[('raddoppio','periodico',64)])} s, e uno da 8192 byte richiede "
    rf"{g(D[('raddoppio','periodico',8192)])} s.")
conclusioni = (
    r"Un compressore reversibile completo si scrive una volta sola: \kw{call comprimi} comprime, "
    r"\kw{uncall comprimi} decomprime, e i \kw{par} fra blocchi valgono nei due versi. La condizione è la "
    r"pulizia di ogni stadio, e il lavoro mostra che si ottiene con poche tecniche ricorrenti: la coppia di "
    r"procedure per la BWT, i testimoni azzerati guardando lo stato, la spazzatura su uno stack ripulita "
    r"disfacendo chi l'ha prodotta, e formati pensati per essere letti dalla cima, cioè nell'ordine in cui li "
    r"consuma l'inverso. Il punto che Lyngby et al. indicavano come aperto, l'ordinamento delle rotazioni, "
    r"si chiude con il raddoppio dei prefissi: $O(n\log n)$ qualunque siano i dati, contro l'$O(n^3)$ del "
    r"capitolo 4. La distanza da bzip2 che resta è quasi tutta nel codice entropico, il prossimo stadio da "
    r"rendere reversibile.")

for k, v in {'@@ABSTRACT_NUMERI@@': abstract_num, '@@CORRETTEZZA@@': correttezza,
             '@@TAB_SORT@@': tab_sort, '@@PLOT_SORT@@': plot, '@@COMMENTO_SORT@@': commento_sort,
             '@@TAB_CORPUS@@': tab_corpus, '@@COMMENTO_CORPUS@@': commento_corpus,
             '@@TAB_PROFILO@@': tab_profilo, '@@CONCORRENZA@@': concorrenza,
             '@@CONCLUSIONI@@': conclusioni, '@@MEMORIA@@': memoria('kgzip2'),
             '@@NTEST@@': ntest(), '@@MANOMISSIONE@@': manomissione('kgzip2'),
             '@@EFFICIENZA@@': efficienza('kgzip2', NOMIF), '@@LIVELLI@@': livelli('kgzip2')}.items():
    assert k in tex, k
    tex = tex.replace(k, v)
tex = tex.replace("\\'", "'")
assert '@@' not in tex
assert '—' not in tex
(QUI / 'kgzip2_pieno.tex').write_text(tex)
print('ok')
