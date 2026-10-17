# Kairos

**Try it now:** [nicologiuliani.site/docs/kairos](https://nicologiuliani.site/docs/kairos/#playground) — write and run Kairos programs in your browser, nothing to install.

Kairos is a **reversible, concurrent** programming language in the [Janus](https://en.wikipedia.org/wiki/Janus_%28time-reversible_computing_programming_language%29) family. Every program runs forwards and backwards: each command has a well-defined inverse, and `uncall` runs a procedure in reverse. Kairos follows Janus one-to-one on the reversible core (assignments, `if … fi`, `from … until`, `local … delocal`, `call`/`uncall`) and adds explicit parallelism (`par … and … rap`), synchronous channels with inferred protocols and channel passing (π-calculus style), stacks, arrays and a `try … rollback … yrt` construct.

The frontend is written in Python (PLY) and produces a textual bytecode; the VM is written in C and interprets it both forwards and backwards.

```kairos
procedure fib(int n, int a, int b)
    if n == 0 then
        a += 1
        b += 1
    else
        n -= 1
        call fib(n, a, b)
        a += b
        a <=> b
    fi a == b

procedure main()
    local int n = 10
    local int a = 0
    local int b = 0
    call fib(n, a, b)
    show(b)
    uncall fib(n, a, b)
    delocal int b = 0
    delocal int a = 0
    delocal int n = 10
```

---

## Contents

1. [Installation](#installation)
2. [Building from source](#building-from-source)
3. [Make targets](#make-targets)
4. [Repository layout](#repository-layout)
5. [Architecture](#architecture)
6. [The language](#the-language)
7. [Reversibility: rules and checks](#reversibility-rules-and-checks)
8. [The bytecode](#the-bytecode)
9. [Common errors](#common-errors)
10. [Debugger and VS Code](#debugger-and-vs-code)

---

## Installation

One line installs the right package for your distribution (`.deb`, `.rpm` or Arch; asks for the sudo password):

```bash
curl -fsSL https://github.com/nicologiuliani6/kairos/releases/latest/download/install.sh | bash
```

Or download the package from the [releases](https://github.com/nicologiuliani6/kairos/releases) (standalone frontend + VM, no Python needed) and install it by hand:

| Distribution | File | Install |
|---|---|---|
| Debian / Ubuntu | `kairos_<version>_amd64.deb` | `sudo apt install ./kairos_<version>_amd64.deb` |
| Fedora / RHEL | `kairos-<version>-1.<dist>.x86_64.rpm` | `sudo dnf install ./kairos-<version>-1.<dist>.x86_64.rpm` |
| Arch Linux | `kairos-<version>-1-x86_64.pkg.tar.zst` | `sudo pacman -U ./kairos-<version>-1-x86_64.pkg.tar.zst` |

The packages install `/usr/local/bin/kairos`, `/opt/kairos/kairos`, the debugger library `/usr/local/lib/kairos/dap.so` and the VM `/usr/local/lib/kairos/libvm.so` (they replace the old `kairosapp` package). Then:

```bash
kairos program.kairos                  # compile and run
kairos program.kairos --dump-bytecode  # also write the bytecode to bytecode.txt
```

Related tools, each with its own one-line installer:

- **VS Code debugger** (step back, reverse continue): `curl -fsSL https://github.com/nicologiuliani6/kairos-vscode-debugger/releases/latest/download/install.sh | bash` ([kairos-vscode-debugger](https://github.com/nicologiuliani6/kairos-vscode-debugger));
- **Mnemo**, a compiler from a reversible subset of C to Kairos: `curl -fsSL https://github.com/nicologiuliani6/mnemo/releases/latest/download/install.sh | bash` ([mnemo](https://github.com/nicologiuliani6/mnemo)).

To build a package locally use `packaging/linux/build-deb.sh`, `build-rpm.sh` or `build-arch.sh` (details in `packaging/linux/README.md`). Pushing a tag `vX.Y.Z` builds all three and attaches them to the release.

---

## Building from source

Requirements: `gcc`, `make`, Python ≥ 3.10 with the `venv` module (Debian/Ubuntu: `sudo apt install build-essential python3 python3-venv`).

```bash
git clone https://github.com/nicologiuliani6/kairos.git
cd kairos
make install-deps                     # venv + ply (+ pyinstaller)
make                                  # builds build/libvm.so
make run FILE=examples/fib.kairos     # runs a program
```

Or directly:

```bash
./venv/bin/python -m src.kairos examples/fib.kairos [--dump-bytecode] [--vm-stats]
```

`--dump-bytecode` writes the bytecode to `bytecode.txt`; `--vm-stats` (or `KAIROS_VM_STATS=1`) prints how many cells are still alive at the end. After editing the VM's C sources run `make build-release` again, otherwise the old `libvm.so` stays in use (the frontend warns about it on stderr).

---

## Make targets

| Target | Effect |
|---|---|
| `make` / `make build-release` | optimised `build/libvm.so` (`-O3 -march=native -flto`, not redistributable) |
| `make build` | portable `libvm.so` (`-O2`) |
| `make build-dap` | `build/libvm_dap.so` for the debugger |
| `make run FILE=f.kairos` | runs a program with `--dump-bytecode` |
| `make test` | runs `tests/`, `examples/` and `lossless/` (5 s timeout each; `KAIROS_EXCLUDE` in the makefile excludes files) |
| `make test-error` | every program in `test_error/` must stop with its tagged error (`*_ok.kairos` must run) |
| `make test-dap` | debugger smoke test (step, step back, streamed output) |
| `make release-app` | standalone app `build/dist/kairos` (PyInstaller) |
| `make install-deps` / `make check-system` | venv and dependencies / system requirements check |
| `make clean` | removes build artefacts |

Programs that must be rejected (expected static and runtime errors) live in `test_error/`, one per rule.

---

## Repository layout

```
src/
  kairos.py            entry point: compile and run
  frontend/
    lexer.py, parser.py   lexing and parsing (PLY) + static checks + try desugaring
    sessions.py           channel protocols inside par blocks
    inverse.py            compiled inverse body of recursive procedures
    bytecode.py           AST → bytecode
  vm/
    Janus.c               forward execution (vm_run_BT), first pass, dump
    vm_invert.h           backward execution (uncall)
    vm_ops.h, ops_arith.h instructions and their inverses
    vm_par.h, vm_channel.h, vm_session.h, vm_ref_lock.h   par, channels, sessions, locks
    vm_frames.h           cloned frames (recursion, threads)
    Janus_dap.c           debugger API (step, step back, breakpoints)
examples/   examples (fib, producer/consumer, π-calculus, try, SAT, janus1982/ …)
lossless/   reversible compression (BWT) and measurements
tests/      programs that must run without errors
test_error/ programs that must be rejected
packaging/  .deb / .rpm / Arch packages
```

---

## Architecture

```
file.kairos ─▶ lexer ─▶ parser (+ static checks, try desugaring)
            ─▶ inverse.py (p__inv for recursive procedures)
            ─▶ bytecode.py ─▶ bytecode string ─▶ libvm.so (ctypes)
                                                  ├─ vm_exec            first pass: frames, DECL, PARAM, LABEL
                                                  ├─ vm_run_BT          forward execution
                                                  └─ invert_op_to_line  backward execution
```

The bytecode reaches the VM in memory, with no intermediate file, and there is **a single copy** of it: every thread of a `par` reads the same read-only string, copying only the line it is executing. At the end the VM prints the variables of `main` (`=== VM dump ===`).

---

## The language

### Types

| Type | Initial value | Notes |
|---|---|---|
| `int` | `0` | signed 64-bit integer, two's complement: arithmetic wraps modulo 2^64 |
| `int a[n]` | `n` cells set to `m` | constant length fixed at declaration |
| `stack` | `nil` | LIFO list of integers |
| `channel` | `empty` | synchronous (rendez-vous) channel |

### Declarations, `local` and `delocal`

In `main` a declaration without `local` (`int x`, `stack s`, `channel c`) creates a frame variable, initially empty. Elsewhere (the compiler enforces it) use `local`/`delocal`:

```kairos
local int x = 0
local int y = x          // y starts from the current value of x (ints only)
local stack s = nil
local channel c = empty
...
delocal channel c = empty
delocal stack s = nil    // s must be empty
delocal i