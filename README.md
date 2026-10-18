# kairos-compressori

Real file compressors written in [Kairos](https://github.com/nicologiuliani6/kairos),
a reversible concurrent language: every program runs forwards and backwards.
Each compressor is written once. Compression is `call comprimi(...)`,
decompression is `uncall comprimi(...)` of the same procedure: no decoder exists
in the source.

| folder | algorithm | pipeline |
|---|---|---|
| [`kgzip2/`](kgzip2) | bzip2 family | initial RLE, BWT (prefix-doubling sort), move-to-front, zero RLE, Elias gamma |
| [`klzma/`](klzma) | LZMA family (7-Zip, xz) | LZ77 with hash chains, rep0 and lazy matching, LZMA context model, binary rANS |

Both produce single-file executables that run without Kairos or Python
installed, with the command-line behaviour of gzip, bzip2 and xz. They stream:
a file of any size goes through in groups of blocks, with constant memory.

## Results

8 KiB blocks, sizes in bytes after compression. LZMA is the 7-Zip coder
without any header (`xz --format=raw`); kgzip2 and klzma include their frame
header and 8 bytes of CRC. Times are VM seconds for compression /
decompression on 2 vCPUs.

| file | bytes | bzip2 -9 | xz -9e | LZMA | kgzip2 | klzma | kgzip2 s | klzma s |
|---|---|---|---|---|---|---|---|---|
| thesis (LaTeX) | 8192 | **3343** | 3544 | 3485 | 3816 | 3483 | 12.5 / 11.4 | 7.5 / 7.7 |
| Janus.c | 8192 | 3214 | 3172 | **3113** | 3601 | 3124 | 12.3 / 11.1 | 6.6 / 6.8 |
| README | 8192 | 3473 | 3380 | **3321** | 3928 | 3340 | 13.0 / 11.6 | 6.8 / 7.1 |
| text repeated twice | 8192 | 2182 | 1956 | 1899 | 2934 | **1830** | 21.8 / 21.3 | 3.9 / 4.1 |
| periodic | 8192 | 61 | 112 | 54 | 58 | **42** | 18.4 / 18.5 | 2.1 / 2.2 |
| image 64x64 | 4109 | 124 | 168 | **109** | 116 | 123 | 3.0 / 3.1 | 1.1 / 1.2 |
| zeros | 4096 | 43 | 92 | 32 | **25** | 31 | 0.8 / 0.8 | 1.0 / 1.1 |
| random | 4096 | 4580 | 4156 | 4158 | **4111** | 4112 | 23.1 / 0 | 5.3 / 0 |

On every file the compressed output is identical, byte for byte, to an
independent Python model, and the round trip restores the original.
`make bench` regenerates the table (`bench/risultati.md`).

## Quick start

```bash
git clone --recursive https://github.com/nicologiuliani6/kairos-compressori
cd kairos-compressori
make eseguibili            # builds kairos/ VM, then dist/bin/kgzip2 and dist/bin/klzma
dist/bin/klzma -v file.txt             # file.txt.klz; file.txt removed after a verified write
dist/bin/klzma -d file.txt.klz         # uncall of the same program
dist/bin/kgzip2 -k file.txt            # keep the input
tar c folder | dist/bin/klzma > folder.tar.klz   # streaming, constant memory
cat a.klz b.klz | dist/bin/klzma -d > ab         # concatenated streams
make test                  # 367 checks
```

Options (both commands): `-d` decompress, `-t` test, `-k` keep, `-f` force,
`-c` stdout, `-v` verbose with progress, `-1`..`-9` block size in KiB (default
`-8`), `-T N` blocks per VM run, as branches of a `par` (default: one per
core), `-s` one block at a time (`-T 1`), `--timeout` for each VM run,
`--salta-crc` (experiments: a damaged file reaches `uncall` without the frame
CRC check). With no file they filter stdin to stdout. `klzma -D N` sets the hash-chain search
depth. The output does not depend on `-T`.

Without building: `python3 -m kgzip2 FILE` or `bin/kgzip2 FILE` from the
repository root, with `ply` installed and `kairos/build/libvm.so` built.

## How it works

The input is read as a stream of fixed-size blocks, collected in groups of
K (one per core). Each group is one VM run with the blocks as branches of a
`par`, in both directions, and its frames are written as soon as it ends: only
one group is in memory at a time. The Kairos frontend translates only the
fixed part of each program (the library and a `main` without data), once: all
full groups have the same shape, so they reuse the same bytecode. The data,
one instruction per byte or per bit, is written straight into the bytecode in
place of a placeholder, so the parser never sees it. The VM runs in a child
process with a time limit.

Each stage of each pipeline is *clean* in the sense of Lyngby, Nylandsted,
Glück and Yokoyama (RC 2024): it consumes its input and leaves only its
output. That is what lets `uncall` start from the compressed bits alone. The
techniques, per stage, are in [`kgzip2/README.md`](kgzip2/README.md) and
[`klzma/README.md`](klzma/README.md); the full reports, in Italian, are in
[`doc/`](doc): `kgzip2.pdf` and `klzma.pdf`.

The format (`.kgz`, `.klz`, in `comune/contenitore.py`) is a magic number,
the algorithm's parameters, then one frame per block: type (Kairos or stored,
plus a "last" flag), length, the algorithm's counters and the packed bits (or
the stored bytes), and a CRC32 of the file up to that point. The last frame
also carries the CRC32 of all the original data. Each frame's CRC is checked
as soon as it is read, before the VM sees it, so a damaged file stops at the
first damaged frame and never reaches `uncall`. Concatenated streams
decompress to the concatenated data, as with gzip and xz.

## Memory and speed

Peak resident memory of the Python process and of the VM process, compressing
the Kairos sources concatenated (`make memoria`, `doc/dati/memoria.json`).
"before" is the previous version, which read the whole file and put all
blocks in one program; "now" is the maximum over compression and
decompression.

| input | before: Python / VM | now kgzip2: Python / VM | now klzma: Python / VM | kgzip2 s (c/u) | klzma s (c/u) |
|---|---|---|---|---|---|
| 16 KiB | 52 / 26 MiB (kgzip2), 50 / 22 MiB (klzma) | 52 / 42 MiB | 50 / 37 MiB | 14 / 12 | 8 / 8 |
| 64 KiB | 68 / 58 MiB (kgzip2), 62 / 41 MiB (klzma) | 56 / 44 MiB | 51 / 39 MiB | 55 / 51 | 30 / 33 |
| 256 KiB | fails (kgzip2), 106 / 116 MiB (klzma) | 56 / 44 MiB | 51 / 39 MiB | 238 / 223 | 104 / 113 |
| 1024 KiB | - | - | 52 / 43 MiB | - | 415 / 452 |

The old kgzip2 failed above 80 KiB: with more than 10 blocks in one program the
per-block names overlapped (`n1` of block 0 and `n` of block 10 were both
`n10`), which Kairos rejects as a race in the `par`. Names now carry a
separator (`n1_0`, `n_10`), and the tests run 25 blocks in one `par`.

Memory now depends on the group, not on the file. Time is still linear:
about 2.5 KiB/s for klzma and 1.1 KiB/s for kgzip2 on 2 cores, so
a 100 GB file needs tens of MiB of RAM but about 459 days with klzma.
Memory is no longer the limit; time is.

## Damaged files and `uncall`

Each frame CRC stops a damaged file before the VM. Without it (`--salta-crc`,
`bench/manomissione.py`), `uncall comprimi` runs on the damaged data: bit flips,
pairs of bits, counters changed by one, on a 1 KiB block. The VM almost always
stops by itself. The inverse must undo the compressor exactly, so data the
compressor could not have produced leaves a trace: an auxiliary that does not
return to zero (`delocal`), an exit assertion contradicting its branch, a pop
from an empty stack. Nobody wrote these checks to validate input: they are the
conditions that make the program invertible, read backwards.

| | trials | VM stops by itself | of which reversibility checks | never ends | wrong output |
|---|---|---|---|---|---|
| kgzip2, before the fix | 260 | 71.2% | 57.7% | 25.4% | 3.5% |
| kgzip2 | 260 | 96.5% | 83.1% | 0.0% | 3.5% |
| klzma | 254 | 98.4% | 3.1% | 0.0% | 1.6% |

The first run found a bug: 25.4% of the damaged files made kgzip2 loop forever.
In `corsa` the entry guard `run == 1` becomes, backwards, the exit test; a run
length read as 0 made `run` go to -1, -2, ... pushing zeros forever. The guard is
now `run <= 1`: identical on valid data in both directions (the compressed
files do not change), but backwards it always exits, and the `delocal` of `run`
stops the VM. The same trials now never loop, and a test checks it.

The wrong outputs are files the compressor could really have produced: for
instance the BWT index changed by one always decodes to another consistent
block. A compressor removes redundancy, and without redundancy there is
nothing to check: that is why the CRCs stay. In klzma the VM stops mostly on an
out-of-bounds index (a match distance before the block start), the check a
careful LZ decoder would also make; in kgzip2 the reversibility checks do most
of the work.

## Layout

| path | content |
|---|---|
| `kairos/` | Kairos, as a git submodule (frontend and VM) |
| `comune/` | running Kairos programs (`kvm.py`), the frame format and CRCs (`contenitore.py`), streaming in groups (`flusso.py`), the command line (`cli.py`) |
| `kgzip2/`, `klzma/` | one folder per algorithm: Kairos library, driver, Python model, command |
| `bin/` | development launchers (`bin/kgzip2`, `bin/klzma`) |
| `test/` | `test_completo.py` and the test corpus |
| `bench/` | comparisons with bzip2/xz/LZMA, memory as the file grows, damaged files, profiles, concurrency, klzma variants |
| `dist/` | `costruisci.sh`: standalone executables with PyInstaller |
| `doc/` | LaTeX sources, raw measurement data, PDFs |

A new algorithm is a new folder with a `.kairos` library whose `comprimi`
procedure is clean, a `driver.py` and a short `__main__.py`. The driver gives
its magic number, its header parameters and the number of counters per frame,
and three functions: `comprimi_gruppo` and `decomprimi_gruppo` (one VM run for
a group of blocks) and `blocco_modello` (the expected counters and bits from
its Python model); `comune/flusso.py` does the rest (streaming, frames, CRCs,
in-memory helpers for tests). Then add its name to the lists in
`test/test_completo.py`, `bench/misura.py`, `bench/memoria.py` and
`dist/costruisci.sh`.

## Requirements

Linux x86-64, gcc, Python 3.10+ (only to build). The executables are built
against the glibc of the build machine: build on the oldest distribution you
want to support.

## License

MIT, like Kairos.
