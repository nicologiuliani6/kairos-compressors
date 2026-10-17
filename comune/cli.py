"""Riga di comando comune, con la semantica di gzip, bzip2 e xz.

    PROG [opzioni] [FILE...]

  -d  decomprime          -z  comprime (predefinito)
  -t  verifica i file compressi (decomprime senza scrivere)
  -k  tiene il file d'ingresso      -f  sovrascrive l'uscita
  -c  scrive su stdout              -v  riporta dimensioni, tempi, avanzamento
  -1 .. -9  dimensione del blocco in KiB (predefinito -8)
  -T N  blocchi per esecuzione della VM, rami di un par (predefinito: i core)
  -s  un blocco alla volta (come -T 1)
  --timeout S  tempo massimo di ogni esecuzione della VM (predefinito 3600 s)

Senza FILE legge da stdin e scrive su stdout. Tutto procede in streaming: in
memoria stanno solo i blocchi del gruppo corrente, qualunque sia la dimensione
del file. In compressione il file d'ingresso si rimuove solo dopo aver scritto
l'uscita e averla verificata con una decompressione completa, confrontata
pezzo per pezzo con l'ingresso (salvo -k, -c o --no-verifica).
"""
import argparse
import os
import pathlib
import sys

from . import contenitore as C
from . import kvm


class _Confronto:
    """Uscita che confronta cio' che riceve con un file, pezzo per pezzo."""

    def __init__(self, f):
        self.f = f

    def write(self, b):
        if C.leggi_pieno(self.f, len(b)) != b:
            raise C.FileNonValido('la verifica dopo la compressione non coincide')

    def fine(self):
        if self.f.read(1):
            raise C.FileNonValido('la verifica dopo la compressione non coincide')


class _Nulla:
    def write(self, b):
        pass


def main(nome, driver, estensione, descrizione, opzioni_extra=None):
    ap = argparse.ArgumentParser(prog=nome, description=descrizione)
    ap.add_argument('file', nargs='*')
    ap.add_argument('-d', '--decompress', action='store_true')
    ap.add_argument('-z', '--compress', action='store_true')
    ap.add_argument('-t', '--test', action='store_true')
    ap.add_argument('-k', '--keep', action='store_true')
    ap.add_argument('-f', '--force', action='store_true')
    ap.add_argument('-c', '--stdout', action='store_true')
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('-T', '--thread', type=int, default=0, metavar='N',
                    help='blocchi per esecuzione della VM, rami di un par (0: i core)')
    ap.add_argument('-s', '--sequenziale', action='store_true', help='un blocco alla volta (come -T 1)')
    ap.add_argument('--timeout', type=float, default=3600.0,
                    help='secondi massimi di ogni esecuzione della VM')
    ap.add_argument('--no-verifica', action='store_true',
                    help='non decomprime per verificare prima di rimuovere l\'ingresso')
    for k in range(1, 10):
        ap.add_argument(f'-{k}', dest='livello', action='store_const', const=k)
    ap.set_defaults(livello=8)
    for args, kw in (opzioni_extra or []):
        ap.add_argument(*args, **kw)
    a = ap.parse_args()
    if a.thread < 0:
        ap.error('-T vuole un numero >= 0')
    gruppo = 1 if a.sequenziale else (a.thread or None)
    extra = {k: getattr(a, k) for k in getattr(driver, 'OPZIONI', ())}
    dim = 1024 * a.livello
    interattivo = a.verbose and sys.stderr.isatty()

    def log(msg):
        if a.verbose:
            print(f'{nome}: {msg}', file=sys.stderr)

    def avanzamento(st):
        if interattivo:
            print(f'\r{nome}: {st.blocchi} blocchi, {st.ingresso >> 10} KiB -> {st.uscita >> 10} KiB',
                  end='', file=sys.stderr, flush=True)

    def riepilogo(chi, st, comp):
        if interattivo:
            print('\r\033[K', end='', file=sys.stderr)
        perc = f' ({100 * st.uscita / st.ingresso:.1f}%)' if comp and st.ingresso else ''
        blocchi = f'{st.blocchi} blocc' + ('o' if st.blocchi == 1 else 'hi')
        esec = f'{st.gruppi} esecuzion' + ('e' if st.gruppi == 1 else 'i')
        log(f'{chi}{st.ingresso} -> {st.uscita} byte{perc}, {blocchi} in {esec} della VM, '
            f'frontend {st.frontend:.1f} s, VM {st.vm:.1f} s')

    def comprimi(ing, usc, chi=''):
        st = driver.comprimi_flusso(ing, usc, dim, gruppo=gruppo, timeout=a.timeout,
                                    avanzamento=avanzamento, **extra)
        riepilogo(chi, st, True)

    def decomprimi(ing, usc, chi=''):
        st = driver.decomprimi_flusso(ing, usc, gruppo=gruppo, timeout=a.timeout,
                                      avanzamento=avanzamento)
        riepilogo(chi, st, False)

    stato = 0
    if (not a.decompress and not a.test and (a.stdout or not a.file)
            and sys.stdout.isatty() and not a.force):
        print(f'{nome}: non scrivo dati compressi su un terminale (usa -f per farlo comunque)',
              file=sys.stderr)
        sys.exit(1)
    if not a.file:                                    # filtro stdin -> stdout
        try:
            if a.test:
                decomprimi(sys.stdin.buffer, _Nulla())
            elif a.decompress:
                decomprimi(sys.stdin.buffer, sys.stdout.buffer)
            else:
                comprimi(sys.stdin.buffer, sys.stdout.buffer)
        except (C.FileNonValido, kvm.ErroreKairos) as e:
            print(f'{nome}: {e}', file=sys.stderr)
            stato = 1
        sys.exit(stato)

    for nomef in a.file:
        f = pathlib.Path(nomef)
        tmp = None
        try:
            if not f.is_file():
                raise C.FileNonValido('non e\' un file regolare')
            if a.test:
                with open(f, 'rb') as ing:
                    decomprimi(ing, _Nulla(), f'{f}: ')
                print(f'{f}: ok')
                continue
            if a.decompress:
                if f.suffix != estensione and not a.stdout:
                    raise C.FileNonValido(f'estensione sconosciuta (attesa {estensione})')
                dest = f.with_suffix('')
                lavora = decomprimi
            else:
                if f.suffix == estensione and not a.force:
                    raise C.FileNonValido(f'ha gia\' l\'estensione {estensione}')
                dest = f.with_name(f.name + estensione)
                lavora = comprimi
            if a.stdout:
                with open(f, 'rb') as ing:
                    lavora(ing, sys.stdout.buffer, f'{f}: ')
                continue
            if dest.exists() and not a.force:
                raise C.FileNonValido(f'{dest} esiste gia\' (usa -f)')
            tmp = dest.with_name(dest.name + '.tmp')
            with open(f, 'rb') as ing, open(tmp, 'wb') as usc:
                lavora(ing, usc, f'{f}: ')
            if not a.decompress and not (a.no_verifica or a.keep):
                with open(tmp, 'rb') as ing, open(f, 'rb') as orig:
                    conf = _Confronto(orig)
                    driver.decomprimi_flusso(ing, conf, gruppo=gruppo, timeout=a.timeout)
                    conf.fine()
                log(f'{f}: verificato con una decompressione completa')
            os.replace(tmp, dest)
            tmp = None
            try:
                os.utime(dest, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns))
            except OSError:
                pass
            if not a.keep:
                f.unlink()
        except (C.FileNonValido, kvm.ErroreKairos, OSError) as e:
            print(f'{nome}: {f}: {e}', file=sys.stderr)
            stato = 1
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    sys.exit(stato)
