/* klzma: compressore reversibile in stile LZMA (7-Zip, xz), scritto in Kairos.
 *
 * La compressione esegue `call comprimi(...)` della libreria klzma.kairos,
 * la decompressione `uncall comprimi(...)`. Le opzioni sono quelle di xz.
 */
#include "kc.h"
#include "gen/klzma_lib.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>

#define VERSIONE "1.0"

/* Preset -0 .. -9: dimensione dei blocchi (KiB) e profondita' D della ricerca
 * nelle catene di hash. -e raddoppia D. */
static const int PRESET_KIB[10] = { 8, 8, 16, 16, 32, 32, 64, 64, 128, 256 };
static const int PRESET_D[10]   = { 4, 8, 8, 16, 16, 32, 32, 64, 64, 128 };
#define PRESET_PREDEFINITO 6

static const char *NOMI[] = {"b", "n", "D", "prev", "head", "ty", "ln", "ds", "st", "rp",
                             "slotbase", "cnt", "pot2", "scarto", "bitst", "x", "nb"};
#define N(a) ((int)(sizeof a / sizeof a[0]))

/* gli array di un blocco, nell'ordine di driver._arr */
static void array_blocco(int i, size_t n, const char **nome, size_t *dim)
{
    static const char *A[] = {"b", "prev", "head", "ty", "ln", "ds", "st", "rp", "slotbase", "cnt", "pot2"};
    size_t D[] = {n, n, KLZMA_HSIZE, n, n, n, n, n, 64, KLZMA_NCNT, 32};
    for (int a = 0; a < 11; a++) { nome[a] = A[a]; dim[a] = D[a]; }
    (void)i;
}

static void costanti(Testo *t, int i, const char *op)
{
    for (int k = 0; k < 32; k++) kc_istr(t, "%s pot2_%d[%d] %lld", op, i, k, 1LL << k);
    for (int s = 1; s < 64; s++) kc_istr(t, "%s slotbase_%d[%d] %lld", op, i, s, (long long)KLZMA_SLOTBASE[s]);
}

static void programma(Testo *t, const size_t *len, int k, int64_t D, int inverso,
                      void (*dati)(Testo *, void *), void *ctx)
{
    kc_inizio_programma(t, KLZMA_LIBRERIA);
    for (int i = 0; i < k; i++) {
        kc_istr(t, "DECL stack scarto_%d", i);
        kc_istr(t, "DECL stack bitst_%d", i);
        kc_istr(t, "DECL stack uscita_%d", i);
        kc_istr(t, "DECL int x_%d", i);
        kc_istr(t, "DECL int nb_%d", i);
        kc_istr(t, "DECL int n_%d", i);
        kc_istr(t, "DECL int D_%d", i);
        kc_istr(t, "PUSHEQ n_%d %zu", i, len[i]);
        kc_istr(t, "PUSHEQ D_%d %lld", i, (long long)D);
    }
    const char *nome[11];
    size_t dim[11];
    for (int i = 0; i < k; i++) {
        array_blocco(i, len[i], nome, dim);
        for (int a = 0; a < 11; a++) kc_istr(t, "LOCAL array %s_%d 0 %zu", nome[a], i, dim[a]);
    }
    for (int i = 0; i < k; i++) costanti(t, i, "PUSHEQ");
    if (inverso) for (int i = 0; i < k; i++) kc_istr(t, "LOCAL int t_%d 0", i);
    dati(t, ctx);
    if (inverso) for (int i = k - 1; i >= 0; i--) kc_istr(t, "DELOCAL int t_%d 0", i);
    if (k > 1) kc_istr(t, "PAR_START");
    for (int i = 0; i < k; i++) {
        if (k > 1) kc_istr(t, "THREAD_%d", i);
        t_str(t, inverso ? "@1      " KLZMA_UNCALL : "@1      CALL comprimi");
        for (int a = 0; a < N(NOMI); a++) t_fmt(t, " %s_%d", NOMI[a], i);
        t_str(t, "\n");
    }
    if (k > 1) kc_istr(t, "PAR_END");
    for (int i = 0; i < k; i++) {
        if (!inverso) {
            kc_istr(t, "SHOW x_%d", i);
            kc_istr(t, "SHOW nb_%d", i);
            kc_istr(t, "SHOW bitst_%d", i);
        } else {
            kc_istr(t, "CALL scarica b_%d uscita_%d n_%d", i, i, i);
            kc_istr(t, "SHOW uscita_%d", i);
        }
    }
    /* le costanti si tolgono in ordine inverso */
    for (int i = k - 1; i >= 0; i--) {
        for (int s = 63; s >= 1; s--) kc_istr(t, "MINEQ slotbase_%d[%d] %lld", i, s, (long long)KLZMA_SLOTBASE[s]);
        for (int q = 31; q >= 0; q--) kc_istr(t, "MINEQ pot2_%d[%d] %lld", i, q, 1LL << q);
    }
    for (int i = k - 1; i >= 0; i--) {
        array_blocco(i, len[i], nome, dim);
        for (int a = 10; a >= 0; a--) kc_istr(t, "DELOCAL array %s_%d 0 %zu", nome[a], i, dim[a]);
    }
    kc_fine_programma(t);
}

typedef struct { Blocco **b; int k; } DatiComp;

static void dati_comp(Testo *t, void *ctx)
{
    DatiComp *d = ctx;
    for (int i = 0; i < d->k; i++)
        for (size_t q = 0; q < d->b[i]->n; q++)
            if (d->b[i]->dati[q]) kc_istr(t, "PUSHEQ b_%d[%zu] %u", i, q, d->b[i]->dati[q]);
}

static int comprimi(const Algoritmo *a, Blocco *b, int k, const int64_t *param, char **errore)
{
    (void)a;
    Blocco **kai = calloc((size_t)k, sizeof *kai);
    size_t *len = calloc((size_t)k, sizeof *len);
    int m = 0;
    for (int i = 0; i < k; i++)
        if (b[i].n >= 1) { kai[m] = &b[i]; len[m] = b[i].n; m++; }
    int esito = 0;
    if (m) {
        Testo t = {0};
        DatiComp d = { kai, m };
        programma(&t, len, m, param[0], 0, dati_comp, &d);
        Valori v;
        esito = kc_esegui(t.s, &v, errore);
        t_libera(&t);
        for (int j = 0; j < m && !esito; j++) {
            char nx[32], nn[32], nb[32];
            snprintf(nx, sizeof nx, "x_%d", j);
            snprintf(nn, sizeof nn, "nb_%d", j);
            snprintf(nb, sizeof nb, "bitst_%d", j);
            const Valore *x = kc_valore(&v, nx), *c = kc_valore(&v, nn), *s = kc_valore(&v, nb);
            if (!x || !c || !s || x->lista || c->lista || !s->lista || (int64_t)s->n != c->val) {
                *errore = kc_strdup_printf("uscita della VM incompleta (blocco %d)", j);
                esito = -1;
                break;
            }
            kai[j]->conti[0] = x->val;
            kai[j]->conti[1] = c->val;
            kai[j]->nbit = s->n;
            kai[j]->bit = malloc(s->n ? s->n : 1);
            for (size_t q = 0; q < s->n; q++) kai[j]->bit[q] = (uint8_t)(s->v[q] != 0);
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
        kc_istr_bit(t, i, "bitst", d->f[i].bit, d->f[i].nbit);
        kc_istr(t, "PUSHEQ x_%d %lld", i, (long long)d->f[i].conti[0]);
        kc_istr(t, "PUSHEQ nb_%d %zu", i, d->f[i].nbit);
    }
}

static int decomprimi(const Algoritmo *a, Frame *f, int k, const int64_t *param, char **errore)
{
    (void)a;
    size_t *len = calloc((size_t)k, sizeof *len);
    for (int i = 0; i < k; i++) len[i] = f[i].n;
    Testo t = {0};
    DatiDec d = { f, k };
    programma(&t, len, k, param[0], 1, dati_dec, &d);
    free(len);
    Valori v;
    int esito = kc_esegui(t.s, &v, errore);
    t_libera(&t);
    if (esito) return -1;
    for (int i = 0; i < k && !esito; i++) esito = kc_prendi_uscita(&v, i, &f[i], errore);
    kc_libera_valori(&v);
    return esito;
}

static const Algoritmo KLZMA = { "klzma", ".klz", "KLZ4", 1, 2, comprimi, decomprimi };

/* ======================================================================
 *  Opzioni, come xz
 * ====================================================================== */

static void aiuto(FILE *f, int lungo)
{
    fprintf(f,
        "uso: klzma [OPZIONI]... [FILE]...\n"
        "Comprime o decomprime FILE nel formato .klz, con l'algoritmo di LZMA scritto in\n"
        "Kairos: la decompressione e' `uncall` dello stesso programma che comprime.\n"
        "\n"
        "  -z, --compress      comprime (predefinito)\n"
        "  -d, --decompress    decomprime (anche --uncompress)\n"
        "  -t, --test          verifica l'integrita' dei file compressi\n"
        "  -l, --list          elenca informazioni sui file .klz\n"
        "  -k, --keep          tiene (non cancella) i file d'ingresso\n"
        "  -f, --force         sovrascrive i file d'uscita e comprime anche cio' che sembra\n"
        "                      gia' compresso\n"
        "  -c, --stdout        scrive su stdout e non cancella i file d'ingresso\n"
        "  -0 ... -9           preset di compressione; predefinito 6\n"
        "  -e, --extreme       comprime di piu', piu' lentamente\n"
        "  -T, --threads=NUM   blocchi in parallelo; 0 = quanti sono i core (predefinito)\n"
        "  -q, --quiet         sopprime gli avvisi; due volte anche gli errori\n"
        "  -v, --verbose       piu' dettagli; due volte ancora di piu'\n"
        "  -h, --help          aiuto breve\n"
        "  -H, --long-help     aiuto completo\n"
        "  -V, --version       versione\n");
    if (lungo)
        fprintf(f,
            "\n"
            "  -S, --suffix=.SUF   usa il suffisso .SUF invece di .klz\n"
            "      --block-size=DIM  dimensione dei blocchi (per esempio 64KiB o 1MiB)\n"
            "      --to-stdout     come --stdout\n"
            "\n"
            "Preset (dimensione dei blocchi e profondita' della ricerca):\n");
    if (lungo)
        for (int p = 0; p <= 9; p++)
            fprintf(f, "  -%d  blocchi da %3d KiB, %3d candidati%s\n", p, PRESET_KIB[p], PRESET_D[p],
                    p == PRESET_PREDEFINITO ? "  (predefinito)" : "");
    fprintf(f, "\nSenza FILE, o con FILE uguale a -, legge lo standard input.\n");
}

static void versione(void)
{
    printf("klzma " VERSIONE "\n"
           "Copyright (c) 2026 Nicolo' Giuliani. Licenza MIT.\n"
           "Contiene la macchina virtuale di Kairos (licenza MIT).\n");
}

static int dimensione(const char *s, size_t *out)
{
    char *e;
    errno = 0;
    unsigned long long v = strtoull(s, &e, 10);
    if (errno || e == s) return -1;
    if (!strcmp(e, "") || !strcmp(e, "B")) {}
    else if (!strcmp(e, "k") || !strcmp(e, "K") || !strcmp(e, "KiB") || !strcmp(e, "kB") || !strcmp(e, "KB")) v <<= 10;
    else if (!strcmp(e, "M") || !strcmp(e, "MiB") || !strcmp(e, "MB")) v <<= 20;
    else return -1;
    if (v < 1 || v > KC_MAX_BLOCCO) return -1;
    *out = (size_t)v;
    return 0;
}

static int numero(const char *s, int *out)
{
    char *e;
    long v = strtol(s, &e, 10);
    if (e == s || *e || v < 0 || v > 4096) return -1;
    *out = (int)v;
    return 0;
}

int main(int argc, char **argv)
{
    Comando c = {0};
    c.stile_xz = 1;
    int preset = PRESET_PREDEFINITO, estremo = 0;
    size_t blocco = 0;
    char **file = calloc((size_t)argc, sizeof *file);
    int n = 0, solo_file = 0;
    for (int i = 1; i < argc; i++) {
        char *a = argv[i];
        if (solo_file || a[0] != '-' || !strcmp(a, "-")) { file[n++] = a; continue; }
        if (!strcmp(a, "--")) { solo_file = 1; continue; }
        if (a[1] == '-') {
            char *val = strchr(a, '=');
            size_t l = val ? (size_t)(val - a) : strlen(a);
            if (val) val++;
#define LUNGA(s) (l == strlen(s) && !strncmp(a, s, l))
            if (LUNGA("--help")) { aiuto(stdout, 0); return 0; }
            else if (LUNGA("--long-help")) { aiuto(stdout, 1); return 0; }
            else if (LUNGA("--version")) { versione(); return 0; }
            else if (LUNGA("--compress")) c.decomprimi = 0;
            else if (LUNGA("--decompress") || LUNGA("--uncompress")) c.decomprimi = 1;
            else if (LUNGA("--test")) c.test = 1;
            else if (LUNGA("--list")) c.lista = 1;
            else if (LUNGA("--keep")) c.tieni = 1;
            else if (LUNGA("--force")) c.forza = 1;
            else if (LUNGA("--stdout") || LUNGA("--to-stdout")) c.su_stdout = 1;
            else if (LUNGA("--extreme")) estremo = 1;
            else if (LUNGA("--quiet")) c.silenzio++;
            else if (LUNGA("--verbose")) c.verbosita++;
            else if (LUNGA("--threads") || LUNGA("--suffix") || LUNGA("--block-size")) {
                if (!val) {
                    if (i + 1 >= argc) { fprintf(stderr, "klzma: %s vuole un argomento\n", a); return 1; }
                    val = argv[++i];
                }
                if (LUNGA("--threads")) {
                    if (numero(val, &c.gruppo)) { fprintf(stderr, "klzma: numero di thread non valido: %s\n", val); return 1; }
                } else if (LUNGA("--suffix")) {
                    if (!*val || strchr(val, '/')) { fprintf(stderr, "klzma: suffisso non valido: %s\n", val); return 1; }
                    c.suffisso = val;
                } else if (dimensione(val, &blocco)) {
                    fprintf(stderr, "klzma: dimensione dei blocchi non valida: %s\n", val);
                    return 1;
                }
            } else {
                fprintf(stderr, "klzma: opzione sconosciuta: %s\n", a);
                fprintf(stderr, "Usa 'klzma --help' per l'aiuto.\n");
                return 1;
            }
#undef LUNGA
            continue;
        }
        for (char *p = a + 1; *p; p++) {
            switch (*p) {
            case 'h': aiuto(stdout, 0); return 0;
            case 'H': aiuto(stdout, 1); return 0;
            case 'V': versione(); return 0;
            case 'z': c.decomprimi = 0; break;
            case 'd': c.decomprimi = 1; break;
            case 't': c.test = 1; break;
            case 'l': c.lista = 1; break;
            case 'k': c.tieni = 1; break;
            case 'f': c.forza = 1; break;
            case 'c': c.su_stdout = 1; break;
            case 'e': estremo = 1; break;
            case 'q': c.silenzio++; break;
            case 'v': c.verbosita++; break;
            case 'T': case 'S': {
                char opt = *p;
                char *val = p[1] ? p + 1 : (i + 1 < argc ? argv[++i] : NULL);
                if (!val) { fprintf(stderr, "klzma: -%c vuole un argomento\n", opt); return 1; }
                if (opt == 'T') {
                    if (numero(val, &c.gruppo)) { fprintf(stderr, "klzma: numero di thread non valido: %s\n", val); return 1; }
                } else {
                    if (!*val || strchr(val, '/')) { fprintf(stderr, "klzma: suffisso non valido: %s\n", val); return 1; }
                    c.suffisso = val;
                }
                goto prossimo;          /* il resto dell'argomento era il valore */
            }
            default:
                if (*p >= '0' && *p <= '9') { preset = *p - '0'; break; }
                fprintf(stderr, "klzma: opzione sconosciuta: -%c\n", *p);
                fprintf(stderr, "Usa 'klzma --help' per l'aiuto.\n");
                return 1;
            }
        }
    prossimo:;
    }
    int64_t D = PRESET_D[preset] * (estremo ? 2 : 1);
    if (D > 256) D = 256;
    c.param[0] = D;
    c.dim_blocco = blocco ? blocco : (size_t)PRESET_KIB[preset] * 1024;
    if (c.test || c.lista) c.su_stdout = 0;
    int r = kc_esegui_comando(&KLZMA, &c, file, n);
    free(file);
    return r;
}
