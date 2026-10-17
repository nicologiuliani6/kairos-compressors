# doc/kgzip2.pdf and doc/klzma.pdf from the LaTeX sources and the measured data
# (bench/risultati.json, doc/dati/). Needs pdflatex with pgfplots.

PY := $(abspath ../.venv/bin/python)

all: kgzip2.pdf klzma.pdf

kgzip2.pdf: kgzip2/kgzip2.tex kgzip2/riempi.py ../bench/risultati.json
	cd kgzip2 && $(PY) riempi.py && pdflatex -interaction=nonstopmode -halt-on-error kgzip2_pieno.tex >/dev/null \
	    && pdflatex -interaction=nonstopmode -halt-on-error kgzip2_pieno.tex >/dev/null
	cp kgzip2/kgzip2_pieno.pdf kgzip2.pdf

klzma.pdf: klzma/corpo.tex klzma/preambolo.tex klzma/riempi.py ../bench/risultati.json
	cd klzma && $(PY) riempi.py && pdflatex -interaction=nonstopmode -halt-on-error klzma_pieno.tex >/dev/null \
	    && pdflatex -interaction=nonstopmode -halt-on-error klzma_pieno.tex >/dev/null
	cp klzma/klzma_pieno.pdf klzma.pdf

.PHONY: all
