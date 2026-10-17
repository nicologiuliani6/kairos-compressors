# Tests

`python3 test/test_completo.py` (or `make test`) runs, for both algorithms, on
the files of `corpus/` and on 13 edge cases (empty file, 1 and 2 bytes, runs of
exactly 4, long runs, all 256 byte values, two blocks in a `par`, ...):

- the compressed output equals, byte for byte, the output of the Python model;
- decompression (`uncall`) restores the original;
- three corrupted copies and one truncated copy are rejected before the VM;

then the real commands in a temporary folder (input removal, `-k`, `-c`,
stdin filter, `-t`, refusing to overwrite) and the four rotation sorts of
kgzip2 against a reference. `--rapido` skips the corpus.

The corpus: `tesi8k.tex` (thesis LaTeX), `janus8k.c` (Kairos VM source),
`readme8k.md` (Kairos README), `doppio8k.tex` (4 KiB of text twice),
`periodico8k.txt`, `cerchio64.pgm` and `cerchio.pgm` (images), `zeri4k.bin`,
`casuale4k.bin`.
