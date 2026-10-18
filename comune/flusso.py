"""Compressione e decompressione in streaming, comuni ai due algoritmi.

L'ingresso si legge a blocchi di dimensione fissa (l'ultimo puo' essere piu'
corto). Ogni gruppo di K blocchi diventa una sola esecuzione della VM, con i
blocchi come rami di un `par`, e i suoi frame si scrivono appena pronti. In
memoria restano solo i blocchi del gruppo corrente, qualunque sia la
dimensione del file. I gruppi pieni hanno tutti la stessa forma, quindi il
frontend di Kairos traduce il programma una volta sola (kvm.compila tiene i
programmi gia' tradotti). L'uscita non dipende da K: c'e' un frame per blocco.

Un algoritmo e' un modulo con:
    MAGIA, PARAMETRI (nomi dei parametri nell'intestazione), NCONT (contatori
    di un frame, l'ultimo e' il numero di bit),
    comprimi_gruppo(blocchi, timeout, *parametri) -> ([(conti, bits) o None], tf, tv)
    decomprimi_gruppo([(n, conti, bits)], timeout, *parametri) -> ([bytes], tf, tv)
    blocco_modello(blocco, *parametri) -> (conti, bits) o None   (per i test)
"""
import io
import os
import zlib

from . import contenitore as C


def core():
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


class Statistiche:
    def __init__(self):
        self.ingresso = self.uscita = self.blocchi = self.gruppi = 0
        self.frontend = self.vm = 0.0


def blocchi(ingresso, dim):
    """(blocco, ultimo), con un blocco di anticipo per sapere qual e' l'ultimo.
    Un ingresso vuoto da' un solo blocco vuoto."""
    if not 1 <= dim <= C.MAX_BLOCCO:
        raise ValueError(f'dimensione del blocco fuori dai limiti: {dim}')
    cur = C.leggi_pieno(ingresso, dim)
    while True:
        nxt = C.leggi_pieno(ingresso, dim) if len(cur) == dim else b''
        yield cur, not nxt
        if not nxt:
            return
        cur = nxt


def dividi(dati, dim):
    return [b for b, _ in blocchi(io.BytesIO(dati), dim)]


def _gruppi(it, k):
    g = []
    for x in it:
        g.append(x)
        if len(g) == k:
            yield g
            g = []
    if g:
        yield g


def _svuota(uscita):
    if hasattr(uscita, 'flush'):
        uscita.flush()


def comprimi(alg, ingresso, uscita, dim, gruppo=None, timeout=None, parametri=(), avanzamento=None):
    s = C.Scrittore(uscita, alg.MAGIA, parametri)
    st = Statistiche()
    for g in _gruppi(blocchi(ingresso, dim), gruppo or core()):
        ris, tf, tv = alg.comprimi_gruppo([b for b, _ in g], timeout, *parametri)
        for (b, ultimo), r in zip(g, ris):
            s.frame(b, *(r or (None, None)), ultimo)
            st.ingresso += len(b)
        st.blocchi += len(g)
        st.gruppi += 1
        st.frontend += tf
        st.vm += tv
        st.uscita = s.scritti
        _svuota(uscita)
        if avanzamento:
            avanzamento(st)
    return st


def decomprimi(alg, ingresso, uscita, gruppo=None, timeout=None, avanzamento=None):
    k = gruppo or core()
    lt = C.Lettore(ingresso, alg.MAGIA, len(alg.PARAMETRI), alg.NCONT)
    st = Statistiche()
    primo = True
    while True:
        par = lt.inizia(primo)
        if par is None:
            return st
        primo = False
        crc, fine = 0, False
        while not fine:
            g = []
            while len(g) < k and not fine:       # ogni frame si controlla qui, prima della VM
                g.append(lt.frame())
                fine = g[-1].ultimo
            kai = [(f.n, f.conti, f.carico) for f in g if f.modo == 0]
            usc = iter(())
            if kai:
                ris, tf, tv = alg.decomprimi_gruppo(kai, timeout, *par)
                usc = iter(ris)
                st.frontend += tf
                st.vm += tv
            for f in g:
                b = next(usc) if f.modo == 0 else f.carico
                if len(b) != f.n:
                    raise C.FileNonValido('blocco ricostruito di lunghezza errata')
                crc = zlib.crc32(b, crc)
                uscita.write(b)
                st.uscita += len(b)
            st.blocchi += len(g)
            st.gruppi += 1
            st.ingresso = lt.letti
            _svuota(uscita)
            if avanzamento:
                avanzamento(st)
        if crc != g[-1].crc_dati:
            raise C.FileNonValido('CRC dei dati ricostruiti errato')


def atteso(alg, dati, dim, parametri=()):
    """Il file che produce il modello Python, con lo stesso formato."""
    u = io.BytesIO()
    s = C.Scrittore(u, alg.MAGIA, parametri)
    for b, ultimo in blocchi(io.BytesIO(dati), dim):
        r = alg.blocco_modello(b, *parametri)
        s.frame(b, *(r or (None, None)), ultimo)
    return u.getvalue()


# --- comodita' in memoria, per i test e i benchmark ---

def comprimi_dati(alg, dati, dim, gruppo=None, timeout=None, parametri=()):
    u = io.BytesIO()
    st = comprimi(alg, io.BytesIO(dati), u, dim, gruppo, timeout, parametri)
    return u.getvalue(), (st.frontend, st.vm)


def decomprimi_dati(alg, buf, gruppo=None, timeout=None):
    u = io.BytesIO()
    st = decomprimi(alg, io.BytesIO(buf), u, gruppo, timeout)
    return u.getvalue(), (st.frontend, st.vm)
