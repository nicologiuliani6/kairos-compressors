# kairos-compressori
#
#   make prepara      Python environment (.venv) and Kairos VM (kairos/build/libvm.so)
#   make test-rapido  quick test suite (edge cases, commands, rotation sorts)
#   make test         full test suite (also the whole corpus, a few minutes)
#   make bench        bench/risultati.md and .json against bzip2, xz, LZMA
#   make memoria      doc/dati/memoria.json: RAM and time as the file grows (streaming)
#   make eseguibili   dist/bin/kgzip2 and dist/bin/klzma, standalone single files
#   make pdf          doc/kgzip2.pdf and doc/klzma.pdf from the LaTeX sources
#   make installa     copies the executables to $(PREFIX)/bin (default /usr/local)
#   make pulisci      removes generated files

PY      := .venv/bin/python
KAIROS  ?= kairos
PREFIX  ?= /usr/local

.PHONY: prepara test-rapido test bench memoria eseguibili pdf installa pulisci

VM_SRC  := $(KAIROS)/src/vm

prepara: $(KAIROS)/build/libvm.so
	@[ -x $(PY) ] || python3 -m venv .venv
	@$(PY) -c "import ply, PyInstaller" 2>/dev/null || .venv/bin/pip install -q ply pyinstaller

# La VM di Kairos per l'uso locale, con gli stessi flag del suo `make release`.
$(KAIROS)/build/libvm.so:
	@[ -f $(VM_SRC)/Janus.c ] || git submodule update --init
	mkdir -p $(KAIROS)/build
	gcc -shared -fPIC -pthread -O3 -march=native -flto -fomit-frame-pointer -funroll-loops \
	    -DNDEBUG -Wno-stringop-truncation -Wl,--version-script=$(VM_SRC)/libvm.map -Wl,-O1 \
	    -o $@ $(VM_SRC)/Janus.c $(VM_SRC)/Janus_dap.c -I$(VM_SRC)

test-rapido: prepara
	$(PY) test/test_completo.py --rapido

test: prepara
	$(PY) test/test_completo.py

bench: prepara
	$(PY) bench/misura.py

memoria: prepara
	$(PY) bench/memoria.py 16 64 256

eseguibili: prepara
	KAIROS_HOME=$(abspath $(KAIROS)) dist/costruisci.sh

pdf:
	$(MAKE) -C doc

installa: eseguibili
	install -m 755 dist/bin/kgzip2 dist/bin/klzma $(PREFIX)/bin/

pulisci:
	rm -rf dist/bin dist/lavoro **/__pycache__ */generati
