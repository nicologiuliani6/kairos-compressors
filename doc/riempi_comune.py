"""Pezzi comuni ai due riempi.py: memoria in streaming e numero dei controlli."""
import json
import pathlib
import re

DATI = pathlib.Path(__file__).resolve().parent / 'dati'
v = lambda s: re.sub(r'(?<=\d)\.(?=\d)', '{,}', s)   # virgola decimale, solo fra cifre


def ntest():
    """Controlli superati nell'ultima esecuzione completa della suite."""
    m = re.search(r'^(\d+) controlli superati, (\d+) falliti', (DATI / 'test_completo.log').read_text(), re.M)
    assert m and m.group(2) == '0', 'la suite completa ha controlli falliti'
    return m.group(1)


def _dati(alg):
    M = [r for r in json.loads((DATI / 'memoria.json').read_text()) if r['algoritmo'] == alg]
    per = {}
    for r in M:
        per.setdefault(r['versione'], {}).setdefault(r['kib'], {})[r['verso']] = r
    return per


def memoria(alg):
    """Tabella e commento: picco di memoria nelle tre versioni e throughput del binario."""
    per = _dati(alg)
    nat, stre, prima = per.get('nativo', {}), per.get('streaming', {}), per.get('prima', {})
    kib = sorted(k for k in nat if {'comprimi', 'decomprimi'} <= set(nat[k]))
    tot = lambda r: r['python_mib'] + r['vm_mib']
    T = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}rrrrrr@{}}', r'\toprule',
         r'& \multicolumn{3}{c}{picco di memoria (MiB)} & \multicolumn{2}{c}{secondi (nativo)} \\',
         r'\cmidrule(lr){2-4}\cmidrule(lr){5-6}',
         r'KiB & prima & streaming in Python & nativo & comprimi & \kw{uncall} \\', r'\midrule']
    for k in kib:
        c, d = nat[k]['comprimi'], nat[k]['decomprimi']
        p = prima.get(k, {}).get('comprimi')
        pp = (r'non riesce' if 'errore' in p else f"{tot(p):.0f}") if p else '--'
        sk = stre.get(k, {})
        ss = f"{max(tot(x) for x in sk.values()):.0f}" if {'comprimi', 'decomprimi'} <= set(sk) else '--'
        T.append(v(f"{k} & {pp} & {ss} & {max(c['mib'], d['mib']):.0f} & {c['secondi']:.0f} & "
                   f"{d['secondi']:.0f}") + r' \\')
    T += [r'\bottomrule', r'\end{tabular}',
          r'\caption{Picco di memoria residente al crescere del file (sorgenti di Kairos concatenati). '
          r"``Prima'': la versione che leggeva tutto il file e metteva tutti i blocchi in un solo programma "
          r"(solo compressione, Python e VM insieme); ``streaming in Python'': il driver Python a gruppi, blocchi "
          r"da 8 KiB; ``nativo'': il binario, con le opzioni predefinite (blocchi da 64 KiB, uno per core), "
          r'massimo fra compressione e decompressione. 2 core.}', rf'\label{{tab:memoria-{alg}}}', r'\end{table}']
    pk = sorted(k for k in prima if 'errore' not in prima[k]['comprimi'])
    falliti = sorted(k for k in prima if 'errore' in prima[k]['comprimi'])
    pend = (tot(prima[pk[-1]]['comprimi']) - tot(prima[pk[0]]['comprimi'])) * 2 ** 20 / ((pk[-1] - pk[0]) * 1024)
    sm = [max(tot(x) for x in stre[k].values()) for k in stre if {'comprimi', 'decomprimi'} <= set(stre[k])]
    nm = [max(nat[k]['comprimi']['mib'], nat[k]['decomprimi']['mib']) for k in kib]
    grande = kib[-1]
    vel_c = grande * 1024 / nat[grande]['comprimi']['secondi']
    vel_d = grande * 1024 / nat[grande]['decomprimi']['secondi']
    giorni = 100e9 / vel_c / 86400
    testo = v(
        rf"Prima dello streaming l'involucro leggeva tutto il file e metteva tutti i blocchi in un solo "
        rf"programma: la memoria cresceva con il file, di circa {pend:.0f} byte di RAM per byte d'ingresso, "
        rf"da {tot(prima[pk[0]]['comprimi']):.0f} MiB per {pk[0]} KiB a {tot(prima[pk[-1]]['comprimi']):.0f} MiB "
        rf"per {pk[-1]} KiB" +
        (rf", e a {falliti[0]} KiB non riusciva affatto: con più di 10 blocchi in un programma i nomi per "
         rf"blocco si sovrapponevano (§\ref{{sec:pipeline}})" if falliti else '') +
        rf". Con lo streaming il picco smette di dipendere dal file: col driver Python stava fra "
        rf"{min(sm):.0f} e {max(sm):.0f} MiB, quasi tutti dell'interprete Python e del frontend; il binario "
        rf"nativo, che non li contiene, sta fra {min(nm):.0f} e {max(nm):.0f} MiB da {kib[0]} a {grande} KiB "
        rf"(Tabella~\ref{{tab:memoria-{alg}}}), con blocchi otto volte più grandi. Il tempo invece resta "
        rf"lineare: {vel_c / 1024:.1f} KiB al secondo in compressione e {vel_d / 1024:.1f} in decompressione "
        rf"su 2 core. Un file da 100 GB si comprime con poche decine di MiB, ma richiederebbe circa "
        rf"{giorni:.0f} giorni: la memoria non è più il limite, il tempo sì.")
    return '\n'.join(T) + '\n\n' + testo


def efficienza(alg, nomi):
    """Tempi per file prima e dopo le ottimizzazioni."""
    prima = {r['file']: r for r in json.loads((DATI / 'risultati_prima_ottimizzazioni.json').read_text())}
    ora = {r['file']: r for r in json.loads((DATI.parent.parent / 'bench' / 'risultati.json').read_text())}
    T = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrrrr@{}}', r'\toprule',
         r'& \multicolumn{2}{c}{prima (s)} & \multicolumn{2}{c}{ora (s)} \\',
         r'\cmidrule(lr){2-3}\cmidrule(lr){4-5}',
         r'file & comprimi & \kw{uncall} & comprimi & \kw{uncall} \\', r'\midrule']
    rc, ru = [], []
    for f, nome in nomi.items():
        if f not in prima or f not in ora or prima[f][alg]['comprimi'][1] < 0.5:
            continue
        a, b = prima[f][alg], ora[f][alg]
        T.append(v(f"{nome} & {a['comprimi'][1]:.1f} & {a['uncall'][1]:.1f} & {b['comprimi'][1]:.1f} & "
                   f"{b['uncall'][1]:.1f}") + r' \\')
        rc.append(a['comprimi'][1] / b['comprimi'][1])
        if a['uncall'][1] >= 0.5:
            ru.append(a['uncall'][1] / b['uncall'][1])
    T += [r'\bottomrule', r'\end{tabular}',
          r'\caption{Secondi per file prima e dopo le ottimizzazioni, stessa macchina e stessa VM. '
          r"``Prima'': tempo della VM con il driver Python, prima degli interventi; ``ora'': il comando "
          r'nativo intero, dall\'avvio alla fine. I file compressi sono identici.}', rf'\label{{tab:efficienza-{alg}}}',
          r'\end{table}']
    media = lambda x: sum(x) / len(x)
    testo = v(rf"Sui file del corpus (Tabella~\ref{{tab:efficienza-{alg}}}) la compressione è in media "
              rf"{media(rc):.1f} volte più veloce e la decompressione {media(ru):.1f} volte, da {min(rc):.1f} a "
              rf"{max(rc):.1f} volte secondo il file.")
    return '\n'.join(T).replace("all\\'avvio", "all'avvio") + '\n\n' + testo


# --- file alterati e uncall --------------------------------------------------

def _mano(nome):
    return json.loads((DATI / nome).read_text())


def _conta(r):
    tot = len(r['prove'])
    c = r['totale']
    return dict(tot=tot, ass=c.get('asserzione', 0), nt=c.get('non termina', 0),
                sb=c.get('uscita sbagliata', 0), gi=c.get('uscita giusta', 0), rev=r['reversibilita'])


def _riga(nome, k):
    p = lambda x: v(f"{100 * x / k['tot']:.1f}") + r'\%'
    return (f"{nome} & {k['tot']} & {p(k['ass'])} & {p(k['rev'])} & {p(k['nt'])} & {p(k['sb'])}" + r' \\')


def manomissione(alg):
    ora, prima = _mano('manomissione.json'), _mano('manomissione_prima.json')
    kg, kl, kgp = _conta(ora['kgzip2']), _conta(ora['klzma']), _conta(prima['kgzip2'])
    pc = lambda x, k: v(f"{100 * x / k['tot']:.1f}") + r'\%'
    base = ora['kgzip2']['base']
    motivi_kl = ora['klzma']['motivi']
    idx_kl = motivi_kl.get('indice fuori dai limiti', 0)
    if alg == 'klzma':
        return v(
            rf"\paragraph{{Un file alterato.}} Il CRC di ogni frame ferma un file alterato prima della VM. "
            rf"Senza di esso (lo stesso esperimento del rapporto su kgzip2, \kw{{bench/manomissione.py}}), su {kl['tot']} "
            rf"alterazioni di un blocco di 1 KiB (bit invertiti, coppie di bit, contatori cambiati di uno) la VM "
            rf"si ferma da sola nel {pc(kl['ass'], kl)} dei casi e non gira mai all'infinito; il "
            rf"{pc(kl['sb'], kl)} termina con dati sbagliati, che il CRC dei dati ferma alla fine. Quasi sempre "
            rf"({idx_kl} casi) a fermarla è un indice fuori dai limiti: perso il sincronismo del rANS, presto "
            r"una distanza punta prima dell'inizio del blocco. È lo stesso controllo che farebbe un decodificatore "
            r"LZ scritto con cura; i controlli propri della reversibilità (\kw{delocal}, asserzioni d'uscita) "
            rf"ne fermano solo {kl['rev']}. In kgzip2 la proporzione è opposta: lì sono loro a fermare "
            rf"il {pc(kg['rev'], kg)} delle alterazioni (il rapporto su kgzip2 descrive l'esperimento per intero).")
    T = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrrrrr@{}}', r'\toprule',
         r'& prove & VM fermata & \quad da controlli & non termina & uscita \\',
         r'& & da sola & di reversibilità & & sbagliata \\', r'\midrule',
         _riga(r'kgzip2, prima della correzione', kgp), _riga('kgzip2', kg), _riga('klzma', kl),
         r'\bottomrule', r'\end{tabular}',
         r'\caption{\kw{uncall comprimi} su un blocco di 1 KiB della tesi alterato, senza il controllo del CRC. '
         r"Le prove sono le stesse nelle due righe di kgzip2. ``Da controlli di reversibilità'': \kw{delocal} e "
         r"asserzioni d'uscita, che esistono solo perché il programma deve potersi invertire; il resto della "
         r"colonna precedente sono \kw{pop} da stack vuoti e indici fuori dai limiti. ``Non termina'': oltre "
         r'dieci volte il tempo normale.}', r'\label{tab:manomissione}', r'\end{table}']
    testo = v(
        r"Il CRC di ogni frame ferma un file alterato prima della VM. Che cosa succederebbe senza? "
        r"L'esperimento (\kw{bench/manomissione.py}) comprime 1 KiB della tesi, lo altera e lancia "
        r"direttamente \kw{uncall comprimi}, saltando il CRC: "
        r"200 bit invertiti a caso, 50 coppie di bit adiacenti alterate, ogni contatore del frame cambiato "
        rf"di $\pm1$, un bit in più o in meno in fondo. Una decompressione normale dura {base['secondi_uncall']:.1f} s; "
        rf"oltre {base['limite']:.0f} s conta come non terminata (Tabella~\ref{{tab:manomissione}})." "\n\n"
        r"Ne esce una proprietà che un decompressore ordinario non ha: quasi sempre la VM si ferma da sola. "
        r"L'inverso deve disfare esattamente il calcolo del compressore, e un file che il compressore non "
        r"avrebbe mai prodotto lascia una traccia: un ausiliario che non torna a zero (\kw{delocal}), "
        r"un'asserzione d'uscita che contraddice il ramo, una \kw{pop} su uno stack vuoto. Nessuno di questi "
        r"controlli è stato scritto per validare l'ingresso: sono le condizioni che rendono il programma "
        r"invertibile, lette all'indietro. Ogni invariante del formato (corse massimali dell'RLE iniziale, una "
        r"corsa di zeri sempre annunciata dal suo 0, il cammino della BWT che deve tornare su \kw{idx}, il "
        rf"numero esatto di bit) diventa un controllo gratuito: in kgzip2 sono questi a fermare il "
        rf"{pc(kg['rev'], kg)} delle alterazioni." "\n\n"
        rf"La prima misura ha trovato però un difetto: il {pc(kgp['nt'], kgp)} delle alterazioni faceva girare "
        r"kgzip2 all'infinito. La causa era \kw{corsa}, che estende una corsa finché la cima dello stack è "
        r"uguale al simbolo, con guardia d'ingresso \kw{run == 1}. All'indietro la guardia d'ingresso diventa "
        r"la condizione d'uscita, e nella RLE degli zeri l'inverso parte dalla lunghezza letta dal file e "
        r"spinge zeri finché \kw{run} torna a 1. Se l'alterazione fa leggere una corsa lunga 0, \kw{run} scende "
        r"a $-1, -2, \dots$ senza mai valere 1, e la VM spinge zeri per sempre. La correzione è una riga: "
        r"\kw{from run <= 1}. Sui dati validi \kw{run} parte da 1 e cresce, le due guardie coincidono nei due "
        r"versi e il file compresso non cambia; su quelli alterati l'inverso esce comunque, e il \kw{delocal} "
        rf"di \kw{{run}} in \kw{{rle0}} ferma la VM. Sulle stesse prove le non terminazioni passano da {kgp['nt']} "
        rf"a {kg['nt']}, tutte diventate asserzioni, e la suite di test controlla che nessun bit invertito faccia "
        r"girare l'\kw{uncall} all'infinito. La regola vale per ogni ciclo reversibile: una guardia d'uguaglianza "
        r"su un contatore che arriva dai dati va scritta come disuguaglianza monotona, perché all'indietro è lei "
        r"a dover fermare il ciclo." "\n\n"
        rf"Restano le uscite sbagliate senza errori, il {pc(kg['sb'], kg)} in kgzip2 e il {pc(kl['sb'], kl)} in "
        r"klzma: alterazioni che portano a un altro file che il compressore avrebbe potuto produrre davvero. Il "
        r"caso più netto è \kw{idx} cambiato di uno, che passa sempre: la BWT è una biiezione fra "
        r"$(\kw{out}, \kw{idx})$ e i blocchi, quindi un altro indice decodifica un altro blocco perfettamente "
        r"coerente. È un limite di principio: un compressore toglie ridondanza, e dove non ce n'è non c'è "
        r"nulla da controllare. Per questo i CRC restano: quello dei frame ferma tutto prima della VM, quello "
        r"dei dati copre i casi che la reversibilità non può vedere. In klzma, infine, la VM si ferma quasi "
        rf"sempre ({idx_kl} casi su {kl['tot']}) per un indice fuori dai limiti, cioè per lo stesso controllo "
        r"che farebbe un decodificatore LZ scritto con cura: i controlli propri della reversibilità lì contano "
        r"poco.")
    return '\n'.join(T) + '\n\n' + testo


# --- preset e dimensione dei blocchi ---------------------------------------

def _blocchi_nativo(alg):
    """{KiB: (secondi comprimi, MiB comprimi, secondi decomprimi, MiB decomprimi)} di un blocco solo."""
    out = {}
    for m in re.finditer(rf'^{alg}\s+blocco\s+(\d+) KiB: comprimi ([\d.]+) s (\d+) MiB, decomprimi ([\d.]+) s (\d+) MiB',
                         (DATI / 'blocchi_nativo.txt').read_text(), re.M):
        out[int(m.group(1))] = (float(m.group(2)), int(m.group(3)), float(m.group(4)), int(m.group(5)))
    return out


def livelli(alg):
    P = json.loads((DATI / 'preset.json').read_text())
    n = P['kib'] * 1024
    pc = lambda b: v(f'{100 * b / n:.1f}') + r'\%'
    bl = _blocchi_nativo(alg)
    if alg == 'klzma':
        T = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrrrr@{}}', r'\toprule',
             r'preset & blocco (KiB) & candidati & byte & \% \\', r'\midrule']
        for p, r in P['klzma'].items():
            T.append(f"\\kw{{-{p}}} & {r['blocco_kib']} & {r['D']} & {r['byte']} & {pc(r['byte'])}" + r' \\')
        T += [r'\midrule', f"xz \\kw{{-9e}} & & & {P['xz']} & {pc(P['xz'])}" + r' \\',
              f"LZMA puro & & & {P['lzma_raw']} & {pc(P['lzma_raw'])}" + r' \\',
              f"bzip2 \\kw{{-9}} & & & {P['bzip2']} & {pc(P['bzip2'])}" + r' \\',
              r'\bottomrule', r'\end{tabular}',
              rf"\caption{{I preset su {P['kib']} KiB di sorgenti di Kairos (C, Python, Markdown), byte dal "
              r"modello Python, che coincidono con quelli del binario. Il predefinito è \kw{-6}.}",
              r'\label{tab:preset}', r'\end{table}']
        k = P['klzma']
        tempo = ', '.join(f"{b} KiB in {bl[b][0]:.0f} s" for b in sorted(bl))
        testo = v(
            r"\paragraph{Preset e dimensione dei blocchi.} I blocchi sono indipendenti, e ognuno riparte da un "
            r"dizionario vuoto: la dimensione dei blocchi conta molto più della profondità della ricerca. Sui "
            rf"sorgenti di Kairos (Tabella~\ref{{tab:preset}}) si passa da {k['0']['byte']} byte con \kw{{-0}} a "
            rf"{k['9']['byte']} con \kw{{-9}}; a parità di blocco, da 32 a 64 candidati (\kw{{-6}} contro \kw{{-7}}) si "
            rf"guadagna lo {100 * (k['6']['byte'] - k['7']['byte']) / k['6']['byte']:.1f}\%. Il tempo per byte "
            rf"invece quasi non dipende dal blocco: un blocco solo, con il binario, si comprime in {tempo}, cioè "
            r"circa in proporzione ai byte. Un blocco grande costa memoria (con 256 KiB la VM arriva a "
            rf"{max(max(x[1], x[3]) for x in bl.values())} MiB in decompressione, per ogni blocco in parallelo) e, "
            r"sui file piccoli, parallelismo: per questo il predefinito è 64 KiB. " + (
                rf"Con \kw{{-9}} klzma fa meglio di xz \kw{{-9e}} su questi file ({k['9']['byte']} contro "
                rf"{P['xz']} byte, ma xz paga un'intestazione più lunga) "
                if k['9']['byte'] < P['xz'] else
                rf"Anche con \kw{{-9}} klzma resta sopra xz \kw{{-9e}} ({k['9']['byte']} contro {P['xz']} byte) "
            ) + r"e sopra LZMA puro, che vede tutto il file con un dizionario unico.")
        return '\n'.join(T) + '\n\n' + testo
    T = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}lrrr@{}}', r'\toprule',
         r'livello & blocco (KiB) & byte & \% \\', r'\midrule']
    for p, r in P['kgzip2'].items():
        T.append(f"\\kw{{-{p}}} & {r['blocco_kib']} & {r['byte']} & {pc(r['byte'])}" + r' \\')
    T += [r'\midrule', f"bzip2 \\kw{{-9}} & & {P['bzip2']} & {pc(P['bzip2'])}" + r' \\',
          r'\bottomrule', r'\end{tabular}',
          rf"\caption{{I livelli su {P['kib']} KiB di sorgenti di Kairos, byte dal modello Python, che "
          r"coincidono con quelli del binario. Il predefinito è \kw{-9}.}", r'\label{tab:livelli}', r'\end{table}']
    k = P['kgzip2']
    tempo = ', '.join(f"{b} KiB in {bl[b][0]:.0f} s" for b in sorted(bl))
    testo = v(
        r"\paragraph{Dimensione dei blocchi.} La BWT rende di più su blocchi grandi: sui sorgenti di Kairos "
        rf"(Tabella~\ref{{tab:livelli}}) si passa da {k['1']['byte']} byte con blocchi da 4 KiB a "
        rf"{k['9']['byte']} con 64 KiB (bzip2 \kw{{-9}}, con blocchi da 900 KiB e Huffman: {P['bzip2']}). Il tempo "
        rf"cresce poco più che in proporzione ai byte, per il $\log n$ dell'ordinamento: un blocco solo si "
        rf"comprime in {tempo}; la memoria arriva a {max(max(x[1], x[3]) for x in bl.values())} MiB per blocco "
        r"con 64 KiB, in decompressione.")
    return '\n'.join(T) + '\n\n' + testo
