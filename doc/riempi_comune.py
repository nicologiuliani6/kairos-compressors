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
