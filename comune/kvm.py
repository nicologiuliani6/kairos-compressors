"""Esecuzione dei programmi Kairos dall'involucro.

Il frontend di Kairos (parser, controlli statici, bytecode) traduce soltanto la
parte fissa del programma: la libreria e un `main` senza dati. I dati, che
sono la parte grande (una riga per byte o per bit), entrano come istruzioni di
bytecode scritte direttamente al posto dell'istruzione segnaposto
`segnaposto_dati += 0`. La VM esegue in un processo figlio, con un tempo
massimo: un programma che non termina non blocca il chiamante.
"""
import ast as _ast
import ctypes
import os
import pathlib
import re
import sys
import tempfile
import time

QUI = pathlib.Path(__file__).resolve().parent
RADICE = QUI.parent
SEGNAPOSTO = 'segnaposto_dati'


class ErroreKairos(Exception):
    pass


def _kairos_home():
    if getattr(sys, 'frozen', False):
        # eseguibile PyInstaller: frontend nell'archivio, libvm.so in kairos/build
        return pathlib.Path(sys._MEIPASS) / 'kairos'
    cand = []
    if os.environ.get('KAIROS_HOME'):
        cand.append(pathlib.Path(os.environ['KAIROS_HOME']))
    cand += [RADICE / 'kairos', RADICE.parent / 'kairos']
    for c in cand:
        if (c / 'src' / 'frontend' / 'parser.py').exists():
            return c
    raise SystemExit('Kairos non trovato: imposta KAIROS_HOME oppure aggiungi il sottomodulo kairos/')


def _libvm(home):
    for p in (home / 'build' / 'libvm.so', home / 'libvm.so',
              pathlib.Path('/usr/local/lib/kairos/libvm.so')):
        if p.exists():
            return p
    raise SystemExit('libvm.so non trovata: esegui `make release` nella cartella di Kairos')


HOME = _kairos_home()
LIBVM = _libvm(HOME)
sys.setrecursionlimit(200000)
sys.path.insert(0, str(HOME))
from src.frontend.lexer import lexer                                  # noqa: E402
from src.frontend.parser import parser, run_static_checks, desugar_try  # noqa: E402
from src.frontend.bytecode import ByteCode_Compiler                   # noqa: E402
from src.frontend.errors import KairosCompileError                    # noqa: E402


def compila(sorgente):
    """Sorgente Kairos -> righe di bytecode."""
    lexer.lineno = 1
    try:
        albero = parser.parse(sorgente, lexer=lexer)
        if albero is None:
            raise ErroreKairos('il parser non ha prodotto un albero')
        albero = desugar_try(albero)
        run_static_checks(albero)
        bc = ByteCode_Compiler()
        bc.process(albero)
    except KairosCompileError as e:
        raise ErroreKairos(str(e))
    righe = []
    while not bc.queue.empty():
        _p, tag, ins = bc.queue.get()
        righe.append(f'{tag:<6}  {ins}')
    return righe


def con_dati(righe, istruzioni):
    """Mette le istruzioni dei dati al posto del segnaposto."""
    for k, r in enumerate(righe):
        parti = r.split(None, 1)
        if len(parti) == 2 and parti[1].strip() == f'PUSHEQ {SEGNAPOSTO} 0':
            return righe[:k] + [f'{parti[0]:<6}  {d}' for d in istruzioni] + righe[k + 1:]
    raise ErroreKairos('segnaposto dei dati non trovato nel bytecode')


def esegui(righe, timeout=None):
    """Esegue il bytecode nella VM, in un processo figlio. Restituisce
    (valori stampati da show, secondi). Se il figlio supera `timeout` secondi
    viene terminato."""
    codice = ('\n'.join(righe) + '\n').encode()
    with tempfile.TemporaryFile() as out:
        t0 = time.perf_counter()
        pid = os.fork()
        if pid == 0:                                   # figlio: solo la VM
            stato = 1
            try:
                os.dup2(out.fileno(), 1)
                os.dup2(out.fileno(), 2)
                lib = ctypes.CDLL(str(LIBVM))
                lib.vm_run_from_string.argtypes = [ctypes.c_char_p]
                lib.vm_run_from_string.restype = None
                lib.vm_run_from_string(codice)
                ctypes.CDLL(None).fflush(None)
                stato = 0
            finally:
                os._exit(stato)
        fine = None if timeout is None else t0 + timeout
        while True:
            fatto, st = os.waitpid(pid, os.WNOHANG)
            if fatto:
                break
            if fine is not None and time.perf_counter() > fine:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
                raise ErroreKairos(f'la VM non ha terminato entro {timeout} s')
            time.sleep(0.01)
        dt = time.perf_counter() - t0
        out.seek(0)
        testo = out.read().decode(errors='replace')
    corpo = testo.split('=== VM dump ===')[0]
    codice_uscita = os.waitstatus_to_exitcode(st)
    if codice_uscita != 0 or re.search(r'\bError\b|\[VM\]', corpo):
        raise ErroreKairos('la VM si e\' fermata: ' + corpo[-1500:].strip())
    valori = {}
    for m in re.finditer(r'^(\w+): (.*)$', corpo, re.M):
        valori[m.group(1)] = _ast.literal_eval(m.group(2))
    return valori, dt


def frontend_e_vm(sorgente, istruzioni, timeout=None):
    """Compila la parte fissa, inserisce i dati, esegue. Restituisce
    (valori, secondi di frontend, secondi di VM)."""
    t0 = time.perf_counter()
    righe = con_dati(compila(sorgente), istruzioni)
    t1 = time.perf_counter()
    valori, dt = esegui(righe, timeout)
    return valori, t1 - t0, dt
