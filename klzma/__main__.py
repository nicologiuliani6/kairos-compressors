"""python -m klzma [opzioni] [FILE...]"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from comune.cli import main        # noqa: E402
from klzma import driver           # noqa: E402

main('klzma', driver, '.klz',
     'klzma: compressore reversibile in stile LZMA (7-Zip), scritto in Kairos. '
     'La decompressione e\' uncall dello stesso programma Kairos.',
     [(('-D',), dict(type=int, default=driver.D_PREDEFINITO, dest='D',
                     help='profondita\' della ricerca nelle catene di hash (predefinito 32)'))])
