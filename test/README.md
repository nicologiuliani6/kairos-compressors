# Tests

`python3 test/test_completo.py` (or `make test`) runs, for both algorithms, on
the files of `corpus/` and on 13 edge cases (empty file, 1 and 2 bytes, runs of
exactly 4, long runs, all 256 byte values, two blocks in a `par`, ...):

- the compressed output equals, byte for byte, the output of the Python model;
- decompression (`uncall`) restores the original;
- three corrupted copies and one truncated copy are rejected before the VM;

then streaming: a file of several frames compressed with different group
sizes gives the same bytes, decompresses with different group sizes and when
concatenated with other streams, trailing garbage is rejected, and on a file of
several frames every truncation and a corrupted byte at every position are
rejected. Without the CRC, 20 bit flips per algorithm go straight to `uncall`:
none may make it loop forever (it must stop on its own checks or end, and then
the data CRC catches it). Then the real commands in a temporary folder (input removal after
verification, `-k`, `-c`, `-T`, a multi-block stdin filter, concatenated
streams from a pipe, `-t` on corrupted and truncated files, `--salta-crc`,
refusing to overwrite, no temporary file left) and the four rotation sorts of kgzip2
against a reference. `--rapido` skips the corpus.

The corpus: `tesi8k.tex` (thesis LaTeX), `janus8k.c` (Kairos VM source),
`readme8k.md` (Kairos README), `doppio8k.tex` (4 KiB of text twice),
`periodico8k.txt`, `cerchio64.pgm` and `cerchio.pgm` (images), `zeri4k.bin`,
`casuale4k.bin`.
