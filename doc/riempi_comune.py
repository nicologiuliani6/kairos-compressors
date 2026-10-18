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
    ora, prima = {}, {}
    for r in M:
        if r['versione'] == 'streaming':
            ora.setdefault(r['kib'], {})[r['verso']] = r
        else:
            prima[r['kib']] = r
    return ora, prima


def memoria(alg):
    """Tabella e commento: picco di RAM prima e dopo lo streaming, e throughput."""
    ora, prima = _dati(alg)
    kib = sorted(k for k in ora if {'comprimi', 'decomprimi'} <= set(ora[k]))
    T = [r'\begin{table}[t]', r'\centering\small', r'\begin{tabular}{@{}rrrrrrrr@{}}', r'\toprule',
         r'& & \multicolumn{2}{c}{prima (MiB)} & \multicolumn{2}{c}{streaming (MiB)} & '
         r'\multicolumn{2}{c}{secondi} \\',
         r'\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}',
         r'KiB & byte compressi & Python & VM & Python & VM & comprimi & \kw{uncall} \\', r'\midrule']
    for k in kib:
        c, d = ora[k]['comprimi'], ora[k]['decomprimi']
        py = max(c['python_mib'], d['python_mib'])
        vm = max(c['vm_mib'], d['vm_mib'])
        p = prima.get(k)
        if p and 'errore' in p:
            pp = r'\multicolumn{2}{c}{non riesce}'
        else:
            pp = (f"{p['python_mib']:.0f} & {p['vm_mib']:.0f}") if p else '-- & --'
        T.append(v(f"{k} & {c['byte_compressi']} & {pp} & {py:.0f} & {vm:.0f} & "
                   f"{c['secondi']:.0f} & {d['secondi']:.0f}") + r' \\')
    T += [r'\bottomrule', r'\end{tabular}',
          r'\caption{Picco di memoria residente al crescere del file (sorgenti di Kairos concatenati), '
          r"per il processo Python e per il processo della VM; ``prima'': la versione che leggeva tutto il file "
          r'e metteva tutti i blocchi in un solo programma (solo compressione). Il processo della VM nasce da un '
          r"\kw{fork} dell'involucro, e il suo picco comprende le pagine condivise con Python. Blocchi da 8 KiB, "
          r'gruppi di 2, 2 core.}', rf'\label{{tab:memoria-{alg}}}', r'\end{table}']
    falliti = sorted(k for k in prima if 'errore' in prima[k])
    pk = sorted(k for k in prima if 'errore' not in prima[k])
    tot = lambda r: r['python_mib'] + r['vm_mib']
    pend = (tot(prima[pk[-1]]) - tot(prima[pk[0]])) * 2 ** 20 / ((pk[-1] - pk[0]) * 1024)
    pend_vm = (prima[pk[-1]]['vm_mib'] - prima[pk[0]]['vm_mib']) * 2 ** 20 / ((pk[-1] - pk[0]) * 1024)
    pys = [max(ora[k]['comprimi']['python_mib'], ora[k]['decomprimi']['python_mib']) for k in kib]
    vms = [max(ora[k]['comprimi']['vm_mib'], ora[k]['decomprimi']['vm_mib']) for k in kib]
    grande = kib[-1]
    vel_c = grande * 1024 / ora[grande]['comprimi']['secondi']
    vel_d = grande * 1024 / ora[grande]['decomprimi']['secondi']
    giorni = 100e9 / vel_c / 86400
    testo = v(
        rf"Prima dello streaming l'involucro leggeva tutto il file e metteva tutti i blocchi in un solo "
        rf"programma: la memoria cresceva con il file, di circa {pend:.0f} byte di RAM per byte d'ingresso "
        rf"(Python e VM insieme, di cui {pend_vm:.0f} nella VM), da {tot(prima[pk[0]]):.0f} MiB per "
        rf"{pk[0]} KiB a {tot(prima[pk[-1]]):.0f} MiB per {pk[-1]} KiB" +
        (rf", e a {falliti[0]} KiB non riusciva affatto: con più di 10 blocchi in un programma i nomi per "
         rf"blocco si sovrapponevano (§\ref{{sec:pipeline}})" if falliti else '') +
        rf". Con lo streaming, da {kib[0]} a "
        rf"{grande} KiB il picco resta fra {min(pys):.0f} e {max(pys):.0f} MiB per Python e fra "
        rf"{min(vms):.0f} e {max(vms):.0f} MiB per la VM (Tabella~\ref{{tab:memoria-{alg}}}): dipende dal "
        rf"gruppo, non dal file. Il tempo invece resta lineare: {vel_c / 1024:.1f} KiB al secondo in "
        rf"compressione e {vel_d / 1024:.1f} in decompressione su 2 core, verifica esclusa. Un file da 100 GB ora si comprime "
        rf"con poche decine di MiB, ma richiederebbe circa {giorni:.0f} giorni: la memoria non è più il "
        rf"limite, il tempo sì.")
    return '\n'.join(T) + '\n\n' + testo


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
            rf"Senza di esso (lo stesso esperimento del rapporto su kgzip2; dal comando, \kw{{klzma -t -{{}}-salta-crc}}), su {kl['tot']} "
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
         r'Le prove sono le stesse nelle due righe di kgzip2. ``Da controlli di reversibilità'': \kw{delocal} e '
         r"asserzioni d'uscita, che esistono solo perché il programma deve potersi invertire; il resto della "
         r"colonna precedente sono \kw{pop} da stack vuoti e indici fuori dai limiti. ``Non termina'': oltre "
         r'dieci volte il tempo normale.}', r'\label{tab:manomissione}', r'\end{table}']
    testo = v(
        r"Il CRC di ogni frame ferma un file alterato prima della VM. Che cosa succederebbe senza? "
        r"L'esperimento (\kw{bench/manomissione.py}) comprime 1 KiB della tesi, lo altera e lancia "
        r"direttamente \kw{uncall comprimi}, saltando il CRC (lo stesso fa il comando con \kw{-{}-salta-crc}): "
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
