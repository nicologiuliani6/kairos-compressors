# kgzip2

A block compressor built on the bzip2 pipeline, written in Kairos. The
decompressor is not written: it is the compressor run backwards.

```
block --RLE--> r --BWT--> out, idx --MTF--> m --zero RLE--> tokens --Elias gamma--> bits
```

The whole pipeline is one procedure, `comprimi`, in [`kgzip2.kairos`](kgzip2.kairos).
Compression runs `call comprimi(...)`, decompression `uncall comprimi(...)`.
Blocks (64 KiB by default, 4 to 64 KiB with `-1` .. `-9`) are read as a
stream; each group of blocks (one per core) is one VM run, with the blocks as
branches of a `par`, in both directions. Blocks stop at 64 KiB because the
initial RLE writes a run length in two bytes (at most 65539).

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
(Manber and Myers): pairs of ranks sorted by stable counting sorts, O(n log n)
whatever the data, with early stop when all ranks are distinct. The first round
sorts the pairs of bytes with two counting sorts over 256 keys; from the second
round the order by the second key is the previous order shifted by h, so one
counting sort is enough. Ranks do not depend on the order inside ties, so the
result is the same; only the round that compares whole rotations (2h >= n)
keeps the two-pass sort, which leaves identical rotations in index order. The old ranks,
the intermediate order and the "stopped" flag go onto `scarto`, which
`uncall ordina` empties. [`fusione.kairos`](fusione.kairos) keeps the intermediate
step (early-exit comparison and a reversible merge sort) and
[`ordinamenti.py`](ordinamenti.py) compares all four sorts.

## Files

| file | content |
|---|---|
| `kgzip2.kairos` | the library: every stage and `comprimi` |
| `driver.py` | Python reference: the Kairos program of a group of blocks, data as bytecode, frame counters, procedure order |
| `../nativo/kgzip2.c` | the `kgzip2` command (options of bzip2), built into `dist/bin/kgzip2` |
| `modello.py` | the same pipeline in Python, bit for bit |
| `fusione.kairos`, `ordinamenti.py` | rotation sorts: bubble, early exit, merge, prefix doubling |
| `profilo.py` | cost of each stage, with truncated programs |

## KGZ4 format

The frame format shared with klzma (`comune/contenitore.py`): `KGZ4`, then one
frame per block. A frame holds a type (mode 0 Kairos or 1 stored, plus a
"last" flag), the block length, for mode 0 the five counters
`idx, n1, tokens, elements, bits` and the packed bits, for mode 1 the bytes.
Every frame ends with a CRC32 of the file up to that point, checked as soon as
the frame is read and before the VM sees it; the last frame also carries the
CRC32 of all the original data. A block whose bits are not shorter than its
bytes is stored. Concatenated `.kgz` streams decompress to the concatenated
data.
