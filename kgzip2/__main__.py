"""python -m kgzip2 [opzioni] [FILE...]"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from comune.cli import main        # noqa: E402
from kgzip2 import driver          # noqa: E402

main('kgzip2', driver, '.kgz',
     'kgzip2 (Kairos gzip2): compressore reversibile in stile bzip2. '
     'La decompressione e\' uncall dello stesso programma Kairos.')
