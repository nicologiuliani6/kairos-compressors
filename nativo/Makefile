# Binari nativi: dist/bin/kgzip2 e dist/bin/klzma.
#
# La libreria Kairos di ogni algoritmo si traduce in bytecode una volta, qui
# (genera.py, con il frontend Python di Kairos); il binario contiene quel
# bytecode, la VM di Kairos compilata da kairos/src/vm e il driver in C.
# A tempo d'esecuzione non servono ne' Python ne' Kairos.

PY      ?= ../.venv/bin/python
KAIROS  ?= ../kairos
VM      := $(KAIROS)/src/vm
OUT     := ../dist/bin
LAVORO  := ../dist/lavoro/nativo
CC      ?= gcc
# x86-64 generico: il binario gira su qualunque processore x86-64
ARCH    ?= -march=x86-64 -mtune=generic
CFLAGS  ?= -O2 -std=gnu11 -Wall -Wextra $(ARCH) -flto
VMFLAGS := -O3 $(ARCH) -flto -fomit-frame-pointer -funroll-loops -DNDEBUG -pthread \
           -Wno-stringop-truncation -Wno-unused-result
LDFLAGS ?= -static -pthread -flto=auto -O2

.PHONY: all pulisci

all: $(OUT)/kgzip2 $(OUT)/klzma

gen/kgzip2_lib.h gen/klzma_lib.h: genera.py ../kgzip2/kgzip2.kairos ../klzma/klzma.kairos \
                                  ../kgzip2/driver.py ../klzma/driver.py ../comune/libreria.py
	$(PY) genera.py

$(LAVORO)/vm.o: $(VM)/Janus.c $(wildcard $(VM)/*.h)
	@mkdir -p $(LAVORO)
	$(CC) $(VMFLAGS) -c -o $@ $(VM)/Janus.c -I$(VM)

$(LAVORO)/vm_dap.o: $(VM)/Janus_dap.c $(wildcard $(VM)/*.h)
	@mkdir -p $(LAVORO)
	$(CC) $(VMFLAGS) -c -o $@ $(VM)/Janus_dap.c -I$(VM)

$(LAVORO)/kc.o: kc.c kc.h
	@mkdir -p $(LAVORO)
	$(CC) $(CFLAGS) -c -o $@ kc.c

$(LAVORO)/%.o: %.c kc.h gen/%_lib.h
	@mkdir -p $(LAVORO)
	$(CC) $(CFLAGS) -c -o $@ $<

$(OUT)/%: $(LAVORO)/%.o $(LAVORO)/kc.o $(LAVORO)/vm.o $(LAVORO)/vm_dap.o
	@mkdir -p $(OUT)
	$(CC) -o $@ $^ $(LDFLAGS)
	strip $@

pulisci:
	rm -rf $(LAVORO) gen $(OUT)/kgzip2 $(OUT)/klzma
