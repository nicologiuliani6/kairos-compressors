# kairos-compressors

Real file compressors written in [Kairos](https://github.com/nicologiuliani6/kairos),
a reversible concurrent language: every program runs forwards and backwards.
Each compressor is written once. Compression is `call comprimi(...)`,
decompression is `uncall comprimi(...)` of the same procedure: no decoder exists
in the source.

| folder | algorithm | pipeline |
|---|---|---|
| [`kgzip2/`](kgzip2) | bzip2 family | initial RLE, BWT (prefix-doubling sort), move-to-front, zero RLE, Elias gamma |
| [`klzma/`](klzma) | LZMA family (7-Zip, xz) | LZ77 with hash chains, rep0 and lazy matching, LZMA context model, binary rANS |

Both are native command-line tools: static binaries of about 1 MB, with the
options of bzip2 (`kgzip2`) and of xz (`klzma`), that run without Kairos or
Python installed. They stream: a file of any size goes through in groups of
blocks, with constant memory.

## Results

Sizes in bytes after compression with the default options (`kgzip2 -9`,
`klzma -6`; every file here fits in one block). LZMA is the 7-Zip coder without
any header (`xz --format=raw`); kgzip2 and klzma include their frame header and
8 bytes of CRC. Times are seconds of the whole command, compression /
decompression, on 2 vCPUs.

| file | bytes | bzip2 -9 | xz -9e | LZMA | kgzip2 | klzma | kgzip2 s | klzma s |
|---|---|---|---|---|---|---|---|---|
| thesis (LaTeX) | 8192 | **3343** | 3544 | 3485 | 3816 | 3483 | 0.2 / 0.2 | 0.1 / 0.2 |
| Janus.c | 8192 | 3214 | 3172 | **3113** | 3601 | 3124 | 0.2 / 0.2 | 0.1 / 0.1 |
| README | 8192 | 3473 | 3380 | **3321** | 3928 | 3340 | 0.2 / 0.2 | 0.1 / 0.1 |
| text repeated twice | 8192 | 2182 | 1956 | 1899 | 2934 | **1830** | 0.4 / 0.4 | 0.1 / 0.1 |
| periodic | 8192 | 61 | 112 | 54 | 58 | **42** | 0.3 / 0.3 | 0.1 / 0.1 |
| image 64x64 | 4109 | 124 | 168 | **109** | 116 | 123 | 0.0 / 0.0 | 0.1 / 0.1 |
| zeros | 4096 | 43 | 92 | 32 | **25** | 31 | 0.0 / 0.0 | 0.0 / 0.0 |
| random | 4096 | 4580 | 4156 | 4158 | **4111** | 4112 | 0.1 / 0.0 | 0.1 / 0.0 |

On every file the compressed output is identical, byte for byte, to an
independent Python model, and the round trip restores the original.
`make bench` regenerates the table (`bench/risultati.md`).

### Against bzip2 and xz on a larger input

256 KiB of Kairos sources (C, Python, Markdown, no repeated content), default
options, bzip2 1.0.8 and xz 5.4.5 on the same machine
(`bench/canonici.py`, `doc/dati/canonici.json`). Times are the whole command;
kgzip2 and klzma use both cores, bzip2 and xz one.

| | bytes | ratio | compress | decompress | peak memory |
|---|---|---|---|---|---|
| bzip2 -9 | 64878 | 24.7% | 0.015 s | 0.007 s | 12 MiB |
| kgzip2 -9 | 81223 | 31.0% | 4.5 s | 4.6 s | 118 MiB |
| xz -6 | 64348 | 24.5% | 0.066 s | 0.005 s | 21 MiB |
| klzma -6 | 74370 | 28.4% | 4.0 s | 4.2 s | 73 MiB |
| xz -9e | 64312 | 24.5% | 0.096 s | 0.005 s | 48 MiB |
| klzma -9e | 69304 | 26.4% | | | |

kgzip2 writes 25% more bytes than bzip2: a fixed Elias gamma code instead of
Huffman tables, and blocks of at most 64 KiB instead of 900 KiB. klzma writes
15% more than xz at the default preset and 8% more at `-9e`: independent
blocks of at most 256 KiB instead of a dictionary of several MiB. On files of a
few KiB the gap closes (table above). Both are one to two orders of
magnitude slower: the time is the interpreter's (about 30 KiB/s per core),
not the format's, since an LZMA decoder written by hand performs the same
steps. Memory is 1.5 to 10 times higher, mostly because the VM keeps every byte
as a 64-bit integer.

## Quick start

```bash
git clone --recursive https://github.com/nicologiuliani6/kairos-compressors
cd kairos-compressors
make eseguibili              # dist/bin/kgzip2 and dist/bin/klzma
sudo make installa           # /usr/local/bin and the man pages
klzma file.txt               # file.txt.klz, file.txt removed
klzma -d file.txt.klz        # uncall of the same program
kgzip2 -k file.txt           # keep the input
klzma -l file.txt.klz        # streams, blocks, sizes, ratio
tar c folder | klzma -9 > folder.tar.klz   # streaming, constant memory
cat a.klz b.klz | klzma -d > ab            # concatenated streams
make test                    # 495 checks
```

## Options

`kgzip2` takes the options of bzip2: `-c` stdout, `-d` decompress, `-z`
compress, `-k` keep, `-f` force, `-t` test, `-q` quiet, `-v` verbose, `-s`
small (one block at a time instead of one per core), `-1` .. `-9` block size
(4, 8, 12, 16, 24, 32, 40, 48, 64 KiB; default `-9`), `--fast`, `--best`,
`-L`, `-V`, `-h`, with the long forms and combined short options (`-dkv`).
Exit codes as bzip2: 0 ok, 1 environment (missing file, bad option, I/O), 2
damaged compressed file, 3 internal error. Blocks stop at 64 KiB because the
initial RLE writes a run length in two bytes.

`klzma` takes the options of xz: `-z`, `-d`, `-t`, `-l` list, `-k`, `-f`, `-c`,
`-0` .. `-9` presets (default `-6`), `-e` extreme, `-T N` threads (0 = one per
core), `-q`, `-v`, `-S .suf`, `--block-size=SIZE`, `-h`, `-H`, `-V`, with the
long forms. Exit codes as xz: 0 ok, 1 error, 2 warnings only.

| preset | -0 | -1 | -2 | -3 | -4 | -5 | **-6** | -7 | -8 | -9 |
|---|---|---|---|---|---|---|---|---|---|---|
| block (KiB) | 8 | 8 | 16 | 16 | 32 | 32 | 64 | 64 | 128 | 256 |
| search depth | 4 | 8 | 8 | 16 | 16 | 32 | 32 | 64 | 64 | 128 |

`-e` doubles the depth. With both tools the output never depends on the
number of blocks run in parallel, and with no file they filter stdin to
stdout. The man pages are in [`nativo/man`](nativo/man).

## How it works

A binary holds three things: the Kairos library of its algorithm, already
translated to bytecode at build time by the Kairos frontend
([`nativo/genera.py`](nativo/genera.py)); the Kairos VM, compiled from
`kairos/src/vm`; and a driver in C ([`nativo/`](nativo)). The driver reads the
input in fixed-size blocks and collects them in groups, one block per core.
For each group it writes the `main` directly in bytecode: the declarations, the
data as one instruction per byte (or per bit, to decompress), a `par` with one
`call comprimi` (or `uncall comprimi`) per block, and the `show`s of the
results. It appends that to the library, runs it in the VM in a child process,
and writes one frame per block. Only one group is in memory at a time.

Each stage of each pipeline is *clean* in the sense of Lyngby, Nylandsted,
Glück and Yokoyama (RC 2024): it consumes its input and leaves only its
output. That is what lets `uncall` start from the compressed bits alone. The
techniques, per stage, are in [`kgzip2/README.md`](kgzip2/README.md) and
[`klzma/README.md`](klzma/README.md); the full reports, in Italian, are in
[`doc/`](doc): `kgzip2.pdf` and `klzma.pdf`.

The format (`.kgz`, `.klz`, described in `comune/contenitore.py`) is a magic
number, the algorithm's parameters, then one frame per block: type (Kairos or
stored, plus a "last" flag), length, the algorithm's counters and the packed
bits (or the stored bytes), and a CRC32 of the file up to that point. The last
frame also carries the CRC32 of all the original data. Each frame's CRC is
checked as soon as it is read, before the VM sees it, so a damaged file stops
at the first damaged frame and never reaches `uncall`. Concatenated streams
decompress to the concatenated data, as with gzip and xz.

The Python side ([`comune/`](comune), the `driver.py` of each algorithm) is the
reference implementation of the same format and programs: the tests check
that the binaries produce the same bytecode and the same bytes.

## Optimizations

Every change keeps the compressed output identical (the tests compare it with
the Python model); the VM is unchanged (its own speedup is below the table). Seconds per corpus file, compression /
decompression, before and after:

| file | kgzip2 before | kgzip2 now | klzma before | klzma now |
|---|---|---|---|---|
| thesis (LaTeX) | 12.5 / 11.4 | 5.0 / 4.8 | 7.5 / 7.7 | 5.5 / 5.8 |
| Janus.c | 12.3 / 11.1 | 4.9 / 4.7 | 6.6 / 6.8 | 4.6 / 5.0 |
| README | 13.0 / 11.6 | 5.2 / 5.0 | 6.8 / 7.1 | 4.8 / 5.2 |
| text repeated twice | 21.8 / 21.3 | 8.1 / 8.2 | 3.9 / 4.1 | 2.8 / 3.1 |
| periodic | 18.4 / 18.5 | 7.1 / 7.3 | 2.1 / 2.2 | 1.0 / 1.1 |
| image 64x64 | 3.0 / 3.1 | 0.7 / 0.8 | 1.1 / 1.2 | 0.6 / 0.7 |
| zeros | 0.8 / 0.8 | 0.2 / 0.2 | 1.0 / 1.1 | 0.5 / 0.5 |
| random | 23.1 / 0.0 | 8.6 / 0.0 | 5.3 / 0.0 | 2.3 / 0.0 |

"Before" is the VM time with the Python driver before these changes; "now" is the
whole native command. The files compressed are identical.

- **One counting sort per round** (kgzip2). From the second round of prefix
  doubling the order by the second key is the previous order shifted by h
  (Manber and Myers), so each round needs one stable counting sort instead of
  two. Ranks do not depend on the order inside ties, and when all pairs are
  distinct the order is unique; only the round that compares whole rotations
  (2h >= n) keeps the two-pass sort, which leaves identical rotations in index
  order. The first round counts 256 keys (bytes) instead of n.
- **Fewer instructions in hot loops**: the BWT extraction reads the character
  directly instead of two calls; a move-to-front step is one swap instead of
  seven instructions; the initial-RLE witness looks at the two top cells and
  goes on only if they are equal; the probability of each coded bit (klzma) is
  computed in line instead of `call prob` / `uncall prob`; in tight search
  loops `if c then x += 1 fi` becomes `x += c`, since a comparison is 0 or 1.
- **Procedure layout.** For every jump and every call the VM finds the target
  line by scanning the bytecode text from the start (`go_to_line`), so the
  same loop costs more the further down it is: a measured 2x for a procedure
  placed after 2,000 lines instead of before. The drivers emit the procedures
  with the busiest loops first ([`comune/libreria.py`](comune/libreria.py)); the
  `.kairos` sources keep their reading order. With a VM that resolves jumps
  once this would no longer matter, and would do no harm.

### The VM (Kairos `main`, from commit `8e6cd9e`)

The VM itself was made faster without changing the language: an index of
bytecode lines (constant-time jumps and calls), instructions decoded once per
thread, compiled expressions with a cached variable lookup, and loop guards
with the same semantics as Janus but cheaper. `uncall` still rebuilds the
inverse at run time by default. With `--compiled-uncall` the frontend emits an
inverse `p__inv` for every procedure without `par` or channels and `uncall p`
becomes a plain call; the native kgzip2 and klzma are built that way.
Compressed bytes are identical in every variant. Seconds for the 8 KiB thesis
file, compression / decompression:

| | original VM | original VM + flag | new VM | new VM + flag |
|---|---|---|---|---|
| kgzip2 | 5.11 / 4.76 | 12.67 / 13.09 | 0.31 / 0.34 | 0.18 / 0.19 |
| klzma | 5.60 / 5.97 | 11.26 / 12.02 | 0.25 / 0.37 | 0.15 / 0.16 |

## Memory and speed

Peak resident memory of the whole command (the binary and its VM processes),
compressing and decompressing the Kairos sources concatenated, with the default
options (64 KiB blocks, one per core; `make memoria`, `doc/dati/memoria.json`).
"Before" is the first version, which read the whole file and put all blocks in
one program (Python and VM together); "Python streaming" is the Python driver
in groups of 8 KiB blocks.

| input | before | Python streaming | native kgzip2 | native klzma | kgzip2 s (c/u) | klzma s (c/u) |
|---|---|---|---|---|---|---|
| 16 KiB | 78 MiB (kgzip2), 72 MiB (klzma) | 83 MiB (kgzip2), 78 MiB (klzma) | 17 MiB | 13 MiB | 0.4 / 0.4 | 0.3 / 0.3 |
| 64 KiB | 126 MiB (kgzip2), 104 MiB (klzma) | 87 MiB (kgzip2), 81 MiB (klzma) | 58 MiB | 41 MiB | 1.8 / 1.9 | 1.5 / 1.6 |
| 256 KiB | fails (kgzip2), 222 MiB (klzma) | 89 MiB (kgzip2), 81 MiB (klzma) | 118 MiB | 73 MiB | 4.5 / 4.6 | 4.0 / 4.2 |
| 1024 KiB | - | 86 MiB (klzma) | 130 MiB | 73 MiB | 19.0 / 19.5 | 15.7 / 15.1 |

The first version failed above 80 KiB with kgzip2: with more than 10 blocks in one
program the per-block names overlapped (`n1` of block 0 and `n` of block 10 were
both `n10`), which Kairos rejects as a race in the `par`. Names now carry a
separator (`n1_0`, `n_10`), and the tests run 25 blocks in one `par`.

Memory depends on the group (block size times cores), not on the file: with the
default 64 KiB blocks on 2 cores it peaks at about 75 MiB for klzma and 130 MiB for
kgzip2, whose BWT keeps more arrays per byte (the faster VM keeps decoded
instructions and a line index per program, up to 1.5x the memory of the
previous VM). Time is linear: about 65 KiB/s for klzma and 54 KiB/s for kgzip2 on 2 cores,
so a 100 GB file would take about 17 days with klzma. Memory is no
longer the limit; the speed of the VM is.

## Damaged files and `uncall`

Each frame CRC stops a damaged file before the VM. Without it
(`bench/manomissione.py`), `uncall comprimi` runs on the damaged data: bit flips,
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
| `nativo/` | the C driver (`kc.c`, `kgzip2.c`, `klzma.c`), `genera.py` (library bytecode at build time), man pages |
| `kgzip2/`, `klzma/` | one folder per algorithm: Kairos library, Python driver, Python model |
| `comune/` | Python reference: running Kairos programs (`kvm.py`), frame format and CRCs (`contenitore.py`), streaming (`flusso.py`), procedure layout (`libreria.py`) |
| `test/` | `test_completo.py` and the test corpus |
| `bench/` | comparisons with bzip2/xz/LZMA, memory as the file grows, damaged files, profiles, concurrency, klzma variants |
| `doc/` | LaTeX sources, raw measurement data, PDFs |
| `kairos/` | Kairos, as a git submodule (frontend and VM) |

A new algorithm is a new folder with a `.kairos` library whose `comprimi`
procedure is clean, a Python `driver.py` (the program of a group of blocks,
`comprimi_gruppo`, `decomprimi_gruppo` and `blocco_modello` from its model;
`comune/flusso.py` does the rest), and a C file in `nativo/` that writes the
same `main` and parses the same options; then add its name to the lists in
`nativo/genera.py`, `nativo/Makefile`, `test/test_completo.py` and the
benchmarks.

## Requirements

To build: Linux x86-64, gcc, Python 3.10+ with `ply` (`make prepara`); the
Kairos frontend runs only at build time. The binaries are static and run on
any Linux x86-64.

## License

MIT, like Kairos.
