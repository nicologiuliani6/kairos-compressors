# klzma

A compressor built on LZMA, the algorithm of 7-Zip and xz, written in Kairos.
The decompressor is `uncall` of the compressor.

```
block --LZ77 (hash chains, rep0, lazy)--> tokens --LZMA contexts, binary rANS--> bits
```

## From LZMA to klzma

| | LZMA | klzma |
|---|---|---|
| match finder | hash chains / binary trees | hash chains, 32 candidates |
| parse | optimal (normal mode) or greedy with lazy | greedy with one step of lazy matching |
| repeat distances | rep0..rep3, short rep | rep0 |
| literals | bit tree on the previous byte; matched literal after a match | bit tree on the previous byte |
| lengths, distances | LZMA length coder, distance slots, reverse trees, align | the same (slots 12-13 with one direct bit + align) |
| state machine | 12 states | the same |
| entropy coder | range coder, shift-updated probabilities | **binary rANS, probabilities from counts** |
| blocks | LZMA2 chunks, shared dictionary | independent blocks, streamed in groups that are branches of a `par` (like xz multithreaded), stored blocks |

Rep1-3 and the matched literal were measured on the Python model and left out:
on 8 KiB blocks they cost more contexts than they save
(`bench/esperimenti_klzma.py`).

## Why rANS

LZMA updates probabilities with `p += (2048 - p) >> 5`. The update is not
injective (2016 and 2017 both become 2017), so it cannot be undone without
garbage. rANS maps the state with
`x' = (x / f) * 4096 + c + (x mod f)`: an exact bijection on integers, whose
inverse is the decoder. Probabilities come from two counts per context, which
backwards are simply subtracted.

## Why the order matters

An adaptive coder run forwards would end with the model in the state "after
all the data", and its inverse would need that state. klzma first counts all
decisions (read-only, `conta_modello`), then codes the tokens from the last to
the first, decrementing each count before coding its bit. The model ends at
zero, and `uncall comprimi` is exactly an LZMA decoder: it starts from an empty
model, decodes the tokens from the first, with state, rep0 and previous byte
already rebuilt, and updates the model after each bit. rANS is a stack and
`uncall` undoes the last step first: the two reversals cancel out.

## Files

| file | content |
|---|---|
| `klzma.kairos` | the library: LZ77, histogram, rANS, `comprimi` |
| `driver.py` | the Kairos program of a group of blocks, data loading as bytecode, frame counters |
| `__main__.py` | the `klzma` command |
| `modello.py` | the same pipeline in Python, with an independent forward decoder |

## KLZ4 format

The frame format shared with kgzip2 (`comune/contenitore.py`): `KLZ4`, the
search depth D, then one frame per block: type (Kairos or stored, plus a
"last" flag), length, for Kairos frames the final rANS state and the number of
bits followed by the bits, for stored frames the bytes; a CRC32 of the file up
to that point, checked before the VM; on the last frame also the CRC32 of the
original data.
