# Tests

`python3 test/test_completo.py` (or `make test`, which builds the binaries
first) checks both algorithms. `--rapido` skips the corpus.

With the Python driver, on the files of `corpus/` and on 13 edge cases (empty
file, 1 and 2 bytes, runs of exactly 4, long runs, all 256 byte values, two
blocks in a `par`, ...):

- the compressed output equals, byte for byte, the output of the Python model;
- decompression (`uncall`) restores the original;
- three corrupted copies and one truncated copy are rejected before the VM.

Streaming: a file of several frames compressed with different group sizes
gives the same bytes and decompresses with different group sizes and when
concatenated with other streams; 25 blocks in one `par` (per-block names must
not overlap); trailing garbage is rejected; on a file of stored frames every
truncation and a corrupted byte at every position are rejected. Without the
CRC, 20 bit flips per algorithm go straight to `uncall`: none may make it loop
forever (it must stop on its own checks or end, and then the data CRC catches
it).

The native binaries (`dist/bin`):

- the `main` the C driver writes in bytecode equals, after normalization, the
  one of the Python driver, compressing and decompressing, with one and two
  blocks;
- every case above, through `kgzip2 -c` / `klzma -c`, equals the model with the
  default options (64 KiB blocks), and `-dc` restores it;
- the real commands in a temporary folder: input removal, `-t` and `-tv`, `-d`,
  `-k`, refusing to overwrite and `-f`, `-dc`, the stdin/stdout filter and `-`,
  the empty file, a corrupted and a truncated file (exit code 2 for kgzip2 as
  bzip2, 1 for klzma as xz, and no partial output left), not compressing a
  `.kgz`/`.klz` again, an unknown suffix (`.out` like bzip2, skipped with a
  warning like xz), a folder, a missing file, an unknown option, `-h` and
  `-V`; a pipe of several blocks equal to the model with one and with several
  blocks per VM run, concatenated streams from a pipe, trailing garbage;
  kgzip2 with a run as long as a 64 KiB block; klzma presets `-0` and `-9`,
  `-e`, `-l`, `-S`; no temporary file left.

Last, the four rotation sorts of kgzip2 against a reference.

The corpus: `tesi8k.tex` (thesis LaTeX), `janus8k.c` (Kairos VM source),
`readme8k.md` (Kairos README), `doppio8k.tex` (4 KiB of text twice),
`periodico8k.txt`, `cerchio64.pgm` and `cerchio.pgm` (images), `zeri4k.bin`,
`casuale4k.bin`.
