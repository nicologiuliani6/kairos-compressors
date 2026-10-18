/* kgzip2: compressore reversibile in stile bzip2, scritto in Kairos.
 *
 * La compressione esegue `call comprimi(...)` della libreria kgzip2.kairos,
 * la decompressione `uncall comprimi(...)`. Le opzioni sono quelle di bzip2.
 */
#include "kc.h"
#include "gen/kgzip2_lib.h"

#include <stdlib.h>
#include <string.h>

#define VERSIONE "1.0"
/* -1 .. -9: dimensione dei blocchi in KiB. Al massimo 64 KiB: l'RLE iniziale
 * scrive la lunghezza di una corsa in due byte (al piu' 65539), e un blocco piu'
 * grande potrebbe contenere una corsa piu' lunga. */
static const int LIVELLO_KIB[10] = { 0, 4, 8, 12, 16, 24, 32, 40, 48, 64 };
#define KGZIP2_MAX_BLOCCO 65536

static const char *ARRAY[] = {"blocco", "r", "offs", "out", "tv", "cam", "ric", "m", "rk", "rk2", "ide"};
static const char *ARRAY_NA[] = {"tab", "freq", "prima", "visti"};
static const char *ARRAY_NR[] = {"cnt", "pos"};
static const char *STACK[] = {"scarto", "src", "dst", "bit", "uscita"};
static const char *CONT[] = {"idx", "n1", "ng", "nel", "nb"};
#define N(a) ((int)(sizeof a / sizeof a[0]))
#define NA 256

static size_t dim_array(int a, size_t n) { return a == 0 ? n : n + n / 2 + 6; }
static size_t nr(size_t n) { size_t d = n + n / 2 + 6; return d > NA ? d : NA; }

static void argomenti(Testo *t, int i)
{
    for (int a = 0; a < N(ARRAY); a++) t_fmt(t, " %s_%d", ARRAY[a], i);
    for (int a = 0; a < N(ARRAY_NA); a++) t_fmt(t, " %s_%d", ARRAY_NA[a], i);
    for (int a = 0; a < N(ARRAY_NR); a++) t_fmt(t, " %s_%d", ARRAY_NR[a], i);
    for (int s = 0; s < N(STACK) - 1; s++) t_fmt(t, " %s_%d", STACK[s], i);
    for (int c = 0; c < N(CONT); c++) t_fmt(t, " %s_%d", CONT[c], i);
    t_fmt(t, " n_%d na nr_%d", i, i);
}

/* Il programma di un gruppo, come driver.programma in kgzip2/driver.py.
 * `dati` scrive le istruzioni dei dati al posto del segnaposto. */
static void programma(Testo *t, const size_t *len, int k, int inverso,
                      void (*dati)(Testo *, void *), void *ctx)
{
    kc_inizio_programma(t, KGZIP2_LIBRERIA);
    kc_istr(t, "DECL int na");
    kc_istr(t, "PUSHEQ na %d", NA);
    for (int i = 0; i < k; i++) {
        for (int s = 0; s < N(STACK); s++) kc_istr(t, "DECL stack %s_%d", STACK[s], i);
        for (int c = 0; c < N(CONT); c++) kc_istr(t, "DECL int %s_%d", CONT[c], i);
        kc_istr(t, "DECL int n_%d", i);
        kc_istr(t, "PUSHEQ n_%d %zu", i, len[i]);
        kc_istr(t, "DECL int nr_%d", i);
        kc_istr(t, "PUSHEQ nr_%d %zu", i, nr(len[i]));
    }
    for (int i = 0; i < k; i++) {
        for (int a = 0; a < N(ARRAY); a++) kc_istr(t, "LOCAL array %s_%d 0 %zu", ARRAY[a], i, dim_array(a, len[i]));
        for (int a = 0; a < N(ARRAY_NA); a++) kc_istr(t, "LOCAL array %s_%d 0 %d", ARRAY_NA[a], i, NA);
        for (int a = 0; a < N(ARRAY_NR); a++) kc_istr(t, "LOCAL array %s_%d 0 %zu", ARRAY_NR[a], i, nr(len[i]));
    }
    if (inverso) for (int i = 0; i < k; i++) kc_istr(t, "LOCAL int t_%d 0", i);
    dati(t, ctx);
    if (inverso) for (int i = k - 1; i >= 0; i--) kc_istr(t, "DELOCAL int t_%d 0", i);
    if (k > 1) kc_istr(t, "PAR_START");
    for (int i = 0; i < k; i++) {
        if (k > 1) kc_istr(t, "THREAD_%d", i);
        t_str(t, inverso ? "@1      UNCALL comprimi" : "@1      CALL comprimi");
        argomenti(t, i);
        t_str(t, "\n");
    }
    if (k > 1) kc_istr(t, "PAR_END");
    for (int i = 0; i < k; i++) {
        if (!inverso) {
            for (int c = 0; c < N(CONT); c++) kc_istr(t, "SHOW %s_%d", CONT[c], i);
            kc_istr(t, "SHOW bit_%d", i);
        } else {
            kc_istr(t, "CALL scarica blocco_%d uscita_%d n_%d", i, i, i);
            kc_istr(t, "SHOW uscita_%d", i);
        }
    }
    for (int i = k - 1; i >= 0; i--) {
        for (int a = N(ARRAY_NR) - 1; a >= 0; a--) kc_istr(t, "DELOCAL array %s_%d 0 %zu", ARRAY_NR[a], i, nr(len[i]));
        for (int a = N(ARRAY_NA) - 1; a >= 0; a--) kc_istr(t, "DELOCAL array %s_%d 0 %d", ARRAY_NA[a], i, NA);
        for (int a = N(ARRAY) - 1; a >= 0; a--) kc_istr(t, "DELOCAL array %s_%d 0 %zu", ARRAY[a], i, dim_array(a, len[i]));
    }
    kc_fine_programma(t);
}

typedef struct { Blocco **b; int k; } DatiComp;

static void dati_comp(Testo *t, void *ctx)
{
    DatiComp *d = ctx;
    for (int i = 0; i < d->k; i++)
        for (size_t q = 0; q < d->b[i]->n; q++)
            if (d->b[i]->dati[q]) kc_istr(t, "PUSHEQ blocco_%d[%zu] %u", i, q, d->b[i]->dati[q]);
}

static int comprimi(const Algoritmo *a, Blocco *b, int k, const int64_t *param, char **errore)
{
    (void)a; (void)param;
    Blocco **kai = calloc((size_t)k, sizeof *kai);
    size_t *len = calloc((size_t)k, sizeof *len);
    int m = 0;
    for (int i = 0; i < k; i++) {
        if (b[i].n > KGZIP2_MAX_BLOCCO) {
            *errore = kc_strdup_printf("blocco oltre %d byte", KGZIP2_MAX_BLOCCO);
            free(kai); free(len);
            return -1;
        }
        if (b[i].n >= 2) { kai[m] = &b[i]; len[m] = b[i].n; m++; }   /* 1 byte: memorizzato */
    }
    int esito = 0;
    if (m) {
        Testo t = {0};
        DatiComp d = { kai, m };
        programma(&t, len, m, 0, dati_comp, &d);
        Valori v;
        esito = kc_esegui(t.s, &v, errore);
        t_libera(&t);
        for (int j = 0; j < m && !esito; j++) {
            char nome[32];
            for (int c = 0; c < N(CONT); c++) {
                snprintf(nome, sizeof nome, "%s_%d", CONT[c], j);
                const Valore *x = kc_valore(&v, nome);
                if (!x || x->lista) { *errore = kc_strdup_printf("uscita della VM incompleta (%s)", nome); esito = -1; break; }
                kai[j]->conti[c] = x->val;
            }
            if (esito) break;
            snprintf(nome, sizeof nome, "bit_%d", j);
            const Valore *x = kc_valore(&v, nome);
            if (!x || !x->lista || (int64_t)x->n != kai[j]->conti[N(CONT) - 1]) {
                *errore = kc_strdup_printf("uscita della VM incompleta (%s)", nome);
                esito = -1;
                break;
            }
            kai[j]->nbit = x->n;
            kai[j]->bit = malloc(x->n ? x->n : 1);
            for (size_t q = 0; q < x->n; q++) kai[j]->bit[q] = (uint8_t)(x->v[q] != 0);
            kai[j]->kairos = 1;
        }
        if (!esito) kc_libera_valori(&v);
    }
    free(kai);
    free(len);
    return esito;
}

typedef struct { Frame *f; int k; } DatiDec;

static void dati_dec(Testo *t, void *ctx)
{
    DatiDec *d = ctx;
    for (int i = 0; i < d->k; i++) {
        kc_istr_bit(t, i, "bit", d->f[i].bit, d->f[i].nbit);
        for (int c = 0; c < N(CONT); c++)
            if (d->f[i].conti[c]) kc_istr(t, "PUSHEQ %s_%d %lld", CONT[c], i, (long long)d->f[i].conti[c]);
    }
}

static int decomprimi(const Algoritmo *a, Frame *f, int k, const int64_t *param, char **errore)
{
    (void)a; (void)param;
    size_t *len = calloc((size_t)k, sizeof *len);
    for (int i = 0; i < k; i++) len[i] = f[i].n;
    Testo t = {0};
    DatiDec d = { f, k };
    programma(&t, len, k, 1, dati_dec, &d);
    free(len);
    Valori v;
    int esito = kc_esegui(t.s, &v, errore);
    t_libera(&t);
    if (esito) return -1;
    for (int i = 0; i < k && !esito; i++) esito = kc_prendi_uscita(&v, i, &f[i], errore);
    kc_libera_valori(&v);
    return esito;
}

static const Algoritmo KGZIP2 = { "kgzip2", ".kgz", "KGZ4", 0, 5, comprimi, decomprimi };

/* ======================================================================
 *  Opzioni, come bzip2
 * ====================================================================== */

static void aiuto(FILE *f)
{
    fprintf(f,
        "kgzip2 " VERSIONE " (Kairos gzip2): compressore reversibile a blocchi in stile bzip2.\n"
        "La decompressione e' `uncall` dello stesso programma Kairos che comprime.\n"
        "\n"
        "uso: kgzip2 [opzioni e nomi di file in qualunque ordine]\n"
        "\n"
        "   -h --help           mostra questo aiuto\n"
        "   -d --decompress     decomprime\n"
        "   -z --compress       comprime (predefinito)\n"
        "   -k --keep           tiene (non cancella) i file d'ingresso\n"
        "   -f --force          sovrascrive i file d'uscita esistenti\n"
        "   -t --test           verifica l'integrita' dei file compressi\n"
        "   -c --stdout         scrive su stdout\n"
        "   -q --quiet          sopprime gli avvisi non critici\n"
        "   -v --verbose        piu' dettagli (ripetibile)\n"
        "   -L --license        mostra la licenza\n"
        "   -V --version        mostra la versione\n"
        "   -s --small          usa meno memoria (un blocco alla volta)\n"
        "   -1 .. -9            dimensione dei blocchi: 4, 8, 12, 16, 24, 32, 40, 48, 64 KiB\n"
        "                       (predefinito -9)\n"
        "   --fast              come -1\n"
        "   --best              come -9\n"
        "\n"
        "   Senza nomi di file kgzip2 comprime o decomprime da stdin a stdout.\n"
        "   Le opzioni corte si possono unire: -v -4 equivale a -v4 o -4v.\n");
}

static void licenza(void)
{
    printf("kgzip2 " VERSIONE "\n"
           "Copyright (c) 2026 Nicolo' Giuliani. Licenza MIT: si puo' usare, copiare,\n"
           "modificare e distribuire liberamente, senza alcuna garanzia.\n"
           "Contiene la macchina virtuale di Kairos (licenza MIT).\n");
}

int main(int argc, char **argv)
{
    Comando c = {0};
    c.dim_blocco = (size_t)LIVELLO_KIB[9] * 1024;
    char **file = calloc((size_t)argc, sizeof *file);
    int n = 0, solo_file = 0;
    for (int i = 1; i < argc; i++) {
        char *a = argv[i];
        if (solo_file || a[0] != '-' || !strcmp(a, "-")) { file[n++] = a; continue; }
        if (!strcmp(a, "--")) { solo_file = 1; continue; }
        if (a[1] == '-') {
            if (!strcmp(a, "--help")) { aiuto(stdout); return 0; }
            else if (!strcmp(a, "--decompress")) c.decomprimi = 1;
            else if (!strcmp(a, "--compress")) c.decomprimi = 0;
            else if (!strcmp(a, "--keep")) c.tieni = 1;
            else if (!strcmp(a, "--force")) c.forza = 1;
            else if (!strcmp(a, "--test")) c.test = 1;
            else if (!strcmp(a, "--stdout")) c.su_stdout = 1;
            else if (!strcmp(a, "--quiet")) c.silenzio++;
            else if (!strcmp(a, "--verbose")) c.verbosita++;
            else if (!strcmp(a, "--license")) { licenza(); return 0; }
            else if (!strcmp(a, "--version")) { licenza(); return 0; }
            else if (!strcmp(a, "--small")) c.gruppo = 1;
            else if (!strcmp(a, "--fast")) c.dim_blocco = (size_t)LIVELLO_KIB[1] * 1024;
            else if (!strcmp(a, "--best")) c.dim_blocco = (size_t)LIVELLO_KIB[9] * 1024;
            else {
                fprintf(stderr, "kgzip2: opzione sconosciuta: %s\n", a);
                aiuto(stderr);
                return 1;
            }
            continue;
        }
        for (char *p = a + 1; *p; p++) {
            switch (*p) {
            case 'h': aiuto(stdout); return 0;
            case 'd': c.decomprimi = 1; break;
            case 'z': c.decomprimi = 0; break;
            case 'k': c.tieni = 1; break;
            case 'f': c.forza = 1; break;
            case 't': c.test = 1; break;
            case 'c': c.su_stdout = 1; break;
            case 'q': c.silenzio++; break;
            case 'v': c.verbosita++; break;
            case 'L': case 'V': licenza(); return 0;
            case 's': c.gruppo = 1; break;
            default:
                if (*p >= '1' && *p <= '9') { c.dim_blocco = (size_t)LIVELLO_KIB[*p - '0'] * 1024; break; }
                fprintf(stderr, "kgzip2: opzione sconosciuta: -%c\n", *p);
                aiuto(stderr);
                return 1;
            }
        }
    }
    if (c.test) c.su_stdout = 0;
    int r = kc_esegui_comando(&KGZIP2, &c, file, n);
    free(file);
    return r;
}
