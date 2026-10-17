"""Riga di comando comune, con la semantica di gzip, bzip2 e xz.

    PROG [opzioni] [FILE...]

  -d  decomprime          -z  comprime (predefinito)
  -t  verifica i file compressi (decomprime in memoria)
  -k  tiene il file d'ingresso      -f  sovrascrive l'uscita
  -c  scrive su stdout              -v  riporta dimensioni e tempi
  -1 .. -9  dimensione del blocco in KiB (predefinito -8)
  -s  blocchi in sequenza invece che rami di un par
  --timeout S  tempo massimo della VM per file (predefinito 3600 s)

Senza FILE legge da stdin e scrive su stdout. In compressione il file
d'ingresso si rimuove solo dopo aver scritto l'uscita e averla verificata con
una decompressione completa (salvo -k, -c o --no-verifica).
"""
import argparse
import os
import pathlib
import sys

from . import contenitore as C
from . import kvm


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
    ap.add_argument('-s', '--sequenziale', action='store_true')
    ap.add_argument('--timeout', type=float, default=3600.0)
    ap.add_argument('--no-verifica', action='store_true',
                    help='non decomprime per verificare prima di rimuovere l\'ingresso')
    for k in range(1, 10):
        ap.add_argument(f'-{k}', dest='livello', action='store_const', const=k)
    ap.set_defaults(livello=8)
    for args, kw in (opzioni_extra or []):
        ap.add_argument(*args, **kw)
    a = ap.parse_args()
    driver.SEQUENZIALE = a.sequenziale
    extra = {k: getattr(a, k) for k in getattr(driver, 'OPZIONI', ())}
    dim = 1024 * a.livello

    def log(msg):
        if a.verbose:
            print(f'{nome}: {msg}', file=sys.stderr)

    def comprimi(dati):
        out, (tf, tv) = driver.comprimi(dati, dim, timeout=a.timeout, **extra)
        perc = 100 * len(out) / len(dati) if dati else 0
        log(f'{len(dati)} -> {len(out)} byte ({perc:.1f}%), frontend {tf:.1f} s, VM {tv:.1f} s')
        return out

    def decomprimi(buf):
        out, (tf, tv) = driver.decomprimi(buf, timeout=a.timeout)
        log(f'{len(buf)} -> {len(out)} byte, frontend {tf:.1f} s, VM {tv:.1f} s')
        return out

    stato = 0
    if not a.file:                                    # filtro stdin -> stdout
        try:
            dati = sys.stdin.buffer.read()
            if a.test:
                decomprimi(dati)
            else:
                sys.stdout.buffer.write(decomprimi(dati) if a.decompress else comprimi(dati))
        except (C.FileNonValido, kvm.ErroreKairos) as e:
            print(f'{nome}: {e}', file=sys.stderr)
            stato = 1
        sys.exit(stato)

    for nomef in a.file:
        f = pathlib.Path(nomef)
        try:
            if not f.is_file():
                raise C.FileNonValido('non e\' un file regolare')
            dati = f.read_bytes()
            if a.test:
                decomprimi(dati)
                print(f'{f}: ok')
                continue
            if a.decompress:
                if f.suffix != estensione and not a.stdout:
                    raise C.FileNonValido(f'estensione sconosciuta (attesa {estensione})')
                out = decomprimi(dati)
                dest = f.with_suffix('')
            else:
                if f.suffix == estensione and not a.force:
                    raise C.FileNonValido(f'ha gia\' l\'estensione {estensione}')
                out = comprimi(dati)
                if not (a.no_verifica or a.stdout or a.keep):
                    if decomprimi(out) != dati:
                        raise C.FileNonValido('la verifica dopo la compressione non coincide')
                dest = f.with_name(f.name + estensione)
            if a.stdout:
                sys.stdout.buffer.write(out)
                continue
            if dest.exists() and not a.force:
                raise C.FileNonValido(f'{dest} esiste gia\' (usa -f)')
            tmp = dest.with_name(dest.name + '.tmp')
            tmp.write_bytes(out)
            os.replace(tmp, dest)
            try:
                os.utime(dest, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns))
            except OSError:
                pass
            if not a.keep:
                f.unlink()
        except (C.FileNonValido, kvm.ErroreKairos, OSError) as e:
            print(f'{nome}: {f}: {e}', file=sys.stderr)
            stato = 1
    sys.exit(stato)
