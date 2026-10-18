# kairos-compressori
#
#   make prepara      Python environment (.venv) and Kairos VM (kairos/build/libvm.so)
#   make test-rapido  quick test suite (edge cases, commands, rotation sorts)
#   make test         full test suite (also the whole corpus, a few minutes)
#   make bench        bench/risultati.md and .json against bzip2, xz, LZMA
#   make memoria      doc/dati/memoria.json: RAM and time as the file grows (streaming)
#   make manomissione doc/dati/manomissione.json: what uncall does on damaged files without CRC
#   make eseguibili   dist/bin/kgzip2 and dist/bin/klzma: native static binaries (C + Kairos VM)
#   make pdf          doc/kgzip2.pdf and doc/klzma.pdf from the LaTeX sources
#   make installa     copies the executables and man pages under $(PREFIX) (default /usr/local)
#   make pulisci      removes generated files

PY      := .venv/bin/python
KAIROS  ?= kairos
PREFIX  ?= /usr/local

.PHONY: prepara test-rapido test bench memoria manomissione eseguibili pdf installa pulisci

VM_SRC  := $(KAIROS)/src/vm

prepara: $(KAIROS)/build/libvm.so
	@[ -x $(PY) ] || python3 -m venv .venv
	@$(PY) -c "import ply" 2>/dev/null || .venv/bin/pip install -q ply

# La VM di Kairos per l'uso locale, con gli stessi flag del suo `make release`.
$(KAIROS)/build/libvm.so:
	@[ -f $(VM_SRC)/Janus.c ] || git submodule update --init
	mkdir -p $(KAIROS)/build
	gcc -shared -fPIC -pthread -O3 -march=native -flto -fomit-frame-pointer -funroll-loops \
	    -DNDEBUG -Wno-stringop-truncation -Wl,--version-script=$(VM_SRC)/libvm.map -Wl,-O1 \
	    -o $@ $(VM_SRC)/Janus.c $(VM_SRC)/Janus_dap.c -I$(VM_SRC)

test-rapido: prepara eseguibili
	$(PY) test/test_completo.py --rapido

test: prepara eseguibili
	$(PY) test/test_completo.py

bench: prepara eseguibili
	$(PY) bench/misura.py

memoria: prepara eseguibili
	$(PY) bench/memoria.py 16 64 256

manomissione: prepara
	$(PY) bench/manomissione.py 200

eseguibili: prepara
	$(MAKE) -C nativo PY=$(abspath $(PY)) KAIROS=$(abspath $(KAIROS))

pdf:
	$(MAKE) -C doc

installa: eseguibili
	install -d $(PREFIX)/bin $(PREFIX)/share/man/man1
	install -m 755 dist/bin/kgzip2 dist/bin/klzma $(PREFIX)/bin/
	install -m 644 nativo/man/kgzip2.1 nativo/man/klzma.1 $(PREFIX)/share/man/man1/

pulisci:
	rm -rf dist/bin dist/lavoro nativo/gen **/__pycache__ */generati
