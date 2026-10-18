"""Ordine delle procedure nel bytecode.

La VM di Kairos, per ogni salto (cicli, if) e per ogni chiamata, ritrova la
riga di arrivo scorrendo il testo del bytecode dall'inizio: un salto costa
quindi in proporzione alla posizione della riga. Mettere in testa le procedure
dove gira la maggior parte dei cicli rende piu' veloce lo stesso programma,
senza cambiarne la semantica. Il sorgente .kairos resta nell'ordine in cui si
legge meglio; il riordino si fa qui, prima del frontend. Con una VM che risolve
i salti una volta sola l'ordine non conterebbe piu', e non farebbe danni.
"""
import re


def riordina(sorgente, ordine):
    """Le procedure nominate in `ordine` per prime, in quell'ordine; le altre
    dopo, nell'ordine del sorgente."""
    pezzi, nomi, corrente, nome = [], [], [], None
    for riga in sorgente.splitlines():
        m = re.match(r'procedure\s+(\w+)\s*\(', riga)
        if m:
            if corrente:
                pezzi.append('\n'.join(corrente))
                nomi.append(nome)
            corrente, nome = [riga], m.group(1)
        elif nome is not None:
            corrente.append(riga)
    if corrente:
        pezzi.append('\n'.join(corrente))
        nomi.append(nome)
    mancanti = [p for p in ordine if p not in nomi]
    if mancanti:
        raise ValueError(f'procedure sconosciute: {mancanti}')
    per_nome = dict(zip(nomi, pezzi))
    resto = [n for n in nomi if n not in ordine]
    return '\n\n'.join(per_nome[n] for n in list(ordine) + resto) + '\n'
