# kgzip2

A block compressor built on the bzip2 pipeline, written in Kairos. The
decompressor is not written: it is the compressor run backwards.

```
block --RLE--> r --BWT--> out, idx --MTF--> m --zero RLE--> tokens --Elias gamma--> bits
```

The whole pipeline is one procedure, `comprimi`, in [`kgzip2.kairos`](kgzip2.kairos).
Compression runs `call comprimi(...)`, decompression `uncall comprimi(...)`.
Blocks (8 KiB by default) are branches of one `par`, in both directions.

## Why the inverse is a decompressor

`uncall comprimi` starts from the bits and five counters per block. That works
because every stage is *clean* (Lyngby, Nylandsted, Glück, Yokoyama, RC 2024):
it consumes its input and leaves only its output.

| stage | how it stays clean |
|---|---|
| initial RLE | a run of L >= 4 becomes `lo, hi, v, v, v, v`, count *under* the copies: the inverse reads from the top, and four equal values on top identify a run |
| BWT | pair of procedures: the forward transform keeps the block, `uncall bwt_inversa` recomputes it from `(out, idx)` and zeroes it |
| move-to-front | after the move the symbol is in `tab[0]`, which zeroes the input; the final table depends only on `m` and is reset by `uncall rigioca` |
| zero RLE | a run of zeros is `L, 0` (the 0 on top announces it); the branch witness is cleared by peeking the output |
| Elias gamma | halving keeps the remainder (`h += x / 2; x -= h; x -= h`); the unary part is pushed by `uncall corsa`, which backwards stops by itself on the 1 |

## Sorting the rotations

The BWT of `kairos/lossless/bwt.kairos` sorts rotations with a bubble sort that
compares whole rotations: O(n^3). Here they are sorted by **prefix doubling**
(Manber and Myers): pairs of ranks sorted by two stable counting sorts, O(n log n)
whatever the data, with early stop when all ranks are distinct. The old ranks,
the intermediate order and the "stopped" flag go onto `scarto`, which
`uncall ordina` empties. [`fusione.kairos`](fusione.kairos) keeps the intermediate
step (early-exit comparison and a reversible merge sort) and
[`ordinamenti.py`](ordinamenti.py) compares all four sorts.

## Files

| file | content |
|---|---|
| `kgzip2.kairos` | the library: every stage and `comprimi` |
| `driver.py` | program generation, data loading as bytecode, KGZ3 container |
| `__main__.py` | the `kgzip2` command (`python -m kgzip2`, `bin/kgzip2`, `dist/bin/kgzip2`) |
| `modello.py` | the same pipeline in Python, bit for bit |
| `fusione.kairos`, `ordinamenti.py` | rotation sorts: bubble, early exit, merge, prefix doubling |
| `profilo.py` | cost of each stage, with truncated programs |

## KGZ3 container

`KGZ3`, number of blocks; per block a mode (0 Kairos, 1 stored) and the length,
plus `idx, n1, tokens, elements, bits` for mode 0; the bits of all mode-0
blocks, then the bytes of stored blocks; CRC32 of the original data and CRC32
of the whole file. The file CRC is checked before running the VM, so a damaged
file never reaches `uncall`. A block whose bits are not shorter than its bytes is
stored.
