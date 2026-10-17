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
installed, with the command-line behaviour of gzip, bzip2 and xz.

## Results

8 KiB blocks, sizes in bytes after compression. LZMA is the 7-Zip coder
without any header (`xz --format=raw`); kgzip2 and klzma include 8 bytes of
CRC. Times are VM seconds for compression / decompression on 2 vCPUs.

| file | bytes | bzip2 -9 | xz -9e | LZMA | kgzip2 | klzma | kgzip2 s | klzma s |
|---|---|---|---|---|---|---|---|---|
| thesis (LaTeX) | 8192 | 3343 | 3544 | 3485 | 3817 | **3484** | 12.4 / 11.4 | 7.5 / 7.7 |
| Janus.c | 8192 | 3214 | 3172 | **3113** | 3602 | 3125 | 12.4 / 11.4 | 6.7 / 6.9 |
| README | 8192 | 3473 | 3380 | **3321** | 3929 | 3341 | 12.8 / 11.6 | 6.8 / 7.2 |
| text repeated twice | 8192 | 2182 | 1956 | 1899 | 2935 | **1831** | 22.1 / 21.4 | 4.0 / 4.0 |
| periodic | 8192 | 61 | 112 | 54 | 59 | **43** | 18.7 / 18.7 | 2.1 / 2.2 |
| image 64x64 | 4109 | 124 | 168 | **109** | 117 | 124 | 3.1 / 3.0 | 1.1 / 1.2 |
| zeros | 4096 | 43 | 92 | 32 | **26** | 32 | 0.8 / 0.8 | 1.0 / 1.1 |
| random | 4096 | 4580 | 4156 | 4158 | **4112** | 4113 | 23.3 / 0 | 5.5 / 0 |

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
tar c folder | dist/bin/klzma > folder.tar.klz
make test                  # 281 checks
```

Options (both commands): `-d` decompress, `-t` test, `-k` keep, `-f` force,
`-c` stdout, `-v` verbose, `-1`..`-9` block size in KiB (default `-8`),
`-s` sequential blocks instead of a `par`, `--timeout` for the VM. With no file
they filter stdin to stdout. `klzma -D N` sets the hash-chain search depth.

Without building: `python3 -m kgzip2 FILE` or `bin/kgzip2 FILE` from the
repository root, with `ply` installed and `kairos/build/libvm.so` built.

## How it works

The Kairos frontend translates only the fixed part of each program (the
library and a `main` without data). The data, one instruction per byte or per
bit, is written straight into the bytecode in place of a placeholder, so the
parser never sees it. The VM runs in a child process with a time limit; blocks
are branches of a `par` in both directions.

Each stage of each pipeline is *clean* in the sense of Lyngby, Nylandsted,
Glück and Yokoyama (RC 2024): it consumes its input and leaves only its
output. That is what lets `uncall` start from the compressed bits alone. The
techniques, per stage, are in [`kgzip2/README.md`](kgzip2/README.md) and
[`klzma/README.md`](klzma/README.md); the full reports, in Italian, are in
[`doc/`](doc): `kgzip2.pdf` and `klzma.pdf`.

The containers (`.kgz`, `.klz`) end with a CRC32 of the original data and a
CRC32 of the whole file. The file CRC is checked before the VM starts, so a
damaged file is rejected and never reaches `uncall`.

## Layout

| path | content |
|---|---|
| `kairos/` | Kairos, as a git submodule (frontend and VM) |
| `comune/` | running Kairos programs (`kvm.py`), containers and CRC, the command line |
| `kgzip2/`, `klzma/` | one folder per algorithm: Kairos library, driver, Python model, command |
| `bin/` | development launchers (`bin/kgzip2`, `bin/klzma`) |
| `test/` | `test_completo.py` and the test corpus |
| `bench/` | comparisons with bzip2/xz/LZMA, profiles, concurrency, klzma variants |
| `dist/` | `costruisci.sh`: standalone executables with PyInstaller |
| `doc/` | LaTeX sources, raw measurement data, PDFs |

A new algorithm is a new folder with a `.kairos` library whose `comprimi`
procedure is clean, a `driver.py` exposing `comprimi`, `decomprimi` and
`atteso` (the expected output from its Python model), and a short
`__main__.py`; then add its name to the lists in `test/test_completo.py`,
`bench/misura.py` and `dist/costruisci.sh`.

## Requirements

Linux x86-64, gcc, Python 3.10+ (only to build). The executables are built
against the glibc of the build machine: build on the oldest distribution you
want to support.

## License

MIT, like Kairos.
