/* kc: il driver nativo comune a kgzip2 e klzma (vedi kc.h). */
#define _GNU_SOURCE
#include "kc.h"

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

void vm_run_from_string_quiet(const char *bytecode);   /* dalla VM di Kairos */

/* ======================================================================
 *  Testo
 * ====================================================================== */

static void *mem(size_t n)
{
    void *p = malloc(n ? n : 1);
    if (!p) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
    return p;
}

void t_add(Testo *t, const char *s, size_t n)
{
    if (t->n + n + 1 > t->cap) {
        size_t c = t->cap ? t->cap : 4096;
        while (c < t->n + n + 1) c *= 2;
        char *p = realloc(t->s, c);
        if (!p) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
        t->s = p; t->cap = c;
    }
    memcpy(t->s + t->n, s, n);
    t->n += n;
    t->s[t->n] = 0;
}

void t_str(Testo *t, const char *s) { t_add(t, s, strlen(s)); }

static void t_vfmt(Testo *t, const char *fmt, va_list ap)
{
    char buf[512];
    va_list ap2;
    va_copy(ap2, ap);
    int k = vsnprintf(buf, sizeof buf, fmt, ap);
    if (k < (int)sizeof buf) { t_add(t, buf, (size_t)k); va_end(ap2); return; }
    char *g = mem((size_t)k + 1);
    vsnprintf(g, (size_t)k + 1, fmt, ap2);
    t_add(t, g, (size_t)k);
    free(g);
    va_end(ap2);
}

void t_fmt(Testo *t, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    t_vfmt(t, fmt, ap);
    va_end(ap);
}

void t_libera(Testo *t) { free(t->s); t->s = NULL; t->n = t->cap = 0; }

char *kc_strdup_printf(const char *fmt, ...)
{
    Testo t = {0};
    va_list ap;
    va_start(ap, fmt);
    t_vfmt(&t, fmt, ap);
    va_end(ap);
    if (!t.s) t_add(&t, "", 0);
    return t.s;
}

/* ======================================================================
 *  CRC32 (quello di zlib), varint, bit
 * ====================================================================== */

static uint32_t tab_crc[256];

static void crc_init(void)
{
    if (tab_crc[1]) return;
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        tab_crc[i] = c;
    }
}

static uint32_t crc32_agg(uint32_t crc, const void *dati, size_t n)
{
    const uint8_t *p = dati;
    crc = ~crc;
    while (n--) crc = tab_crc[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
    return ~crc;
}

static size_t varint(uint8_t *o, uint64_t v)
{
    size_t k = 0;
    do {
        uint8_t c = v & 0x7F;
        v >>= 7;
        o[k++] = c | (v ? 0x80 : 0);
    } while (v);
    return k;
}

static void be32(uint8_t *o, uint32_t v)
{
    o[0] = v >> 24; o[1] = v >> 16; o[2] = v >> 8; o[3] = v;
}

/* ======================================================================
 *  La VM
 * ====================================================================== */

int kc_core(void)
{
    cpu_set_t s;
    if (sched_getaffinity(0, sizeof s, &s) == 0) {
        int n = CPU_COUNT(&s);
        if (n > 0) return n;
    }
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n > 0 ? (int)n : 1;
}

static int parola(const char *s, const char *w)
{
    size_t lw = strlen(w);
    for (const char *p = strstr(s, w); p; p = strstr(p + 1, w)) {
        int prima = p == s || !(p[-1] == '_' || (p[-1] >= 'A' && p[-1] <= 'Z') ||
                                 (p[-1] >= 'a' && p[-1] <= 'z') || (p[-1] >= '0' && p[-1] <= '9'));
        char d = p[lw];
        int dopo = !(d == '_' || (d >= 'A' && d <= 'Z') || (d >= 'a' && d <= 'z') || (d >= '0' && d <= '9'));
        if (prima && dopo) return 1;
    }
    return 0;
}

static void analizza_uscita(char *testo, Valori *out)
{
    out->v = NULL; out->n = 0;
    size_t cap = 0;
    for (char *riga = testo; riga && *riga;) {
        char *fine = strchr(riga, '\n');
        if (fine) *fine = 0;
        char *p = riga;
        while ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z') || (*p >= '0' && *p <= '9') || *p == '_') p++;
        if (p > riga && p[0] == ':' && p[1] == ' ') {
            Valore v = {0};
            v.nome = strndup(riga, (size_t)(p - riga));
            char *q = p + 2;
            if (*q == '[') {
                v.lista = 1;
                size_t c = 0;
                q++;
                while (*q && *q != ']') {
                    char *e;
                    long long x = strtoll(q, &e, 10);
                    if (e == q) break;
                    if (v.n == c) {
                        c = c ? c * 2 : 1024;
                        v.v = realloc(v.v, c * sizeof *v.v);
                        if (!v.v) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
                    }
                    v.v[v.n++] = x;
                    q = e;
                    while (*q == ',' || *q == ' ') q++;
                }
            } else {
                v.val = strtoll(q, NULL, 10);
            }
            if (out->n == cap) {
                cap = cap ? cap * 2 : 16;
                out->v = realloc(out->v, cap * sizeof *out->v);
                if (!out->v) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
            }
            out->v[out->n++] = v;
        }
        riga = fine ? fine + 1 : NULL;
    }
}

int kc_esegui(const char *bytecode, Valori *out, char **errore)
{
    out->v = NULL; out->n = 0;
    FILE *tmp = tmpfile();
    if (!tmp) { *errore = kc_strdup_printf("file temporaneo: %s", strerror(errno)); return -1; }
    const char *dump = getenv("KC_BYTECODE");      /* per i test: copia del programma */
    if (dump && *dump) {
        FILE *f = fopen(dump, "w");
        if (f) { fputs(bytecode, f); fclose(f); }
    }
    fflush(stdout);
    fflush(stderr);
    pid_t pid = fork();
    if (pid < 0) { fclose(tmp); *errore = kc_strdup_printf("fork: %s", strerror(errno)); return -1; }
    if (pid == 0) {
        signal(SIGINT, SIG_DFL);
        signal(SIGTERM, SIG_DFL);
        int fd = fileno(tmp);
        dup2(fd, 1);
        dup2(fd, 2);
        vm_run_from_string_quiet(bytecode);
        fflush(stdout);
        fflush(stderr);
        _exit(0);
    }
    int st = 0;
    while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {}
    Testo t = {0};
    char buf[1 << 16];
    size_t k;
    rewind(tmp);
    while ((k = fread(buf, 1, sizeof buf, tmp)) > 0) t_add(&t, buf, k);
    fclose(tmp);
    if (!t.s) t_add(&t, "", 0);
    if (!WIFEXITED(st) || WEXITSTATUS(st) != 0 || strstr(t.s, "[VM]") || parola(t.s, "Error")) {
        size_t da = t.n > 1500 ? t.n - 1500 : 0;
        char *msg = t.s + da;
        while (*msg == '\n' || *msg == ' ') msg++;
        size_t l = strlen(msg);
        while (l && (msg[l - 1] == '\n' || msg[l - 1] == ' ')) msg[--l] = 0;
        if (WIFSIGNALED(st))
            *errore = kc_strdup_printf("la VM si e' fermata (segnale %d)", WTERMSIG(st));
        else
            *errore = kc_strdup_printf("la VM si e' fermata: %s", msg);
        t_libera(&t);
        return -1;
    }
    analizza_uscita(t.s, out);
    t_libera(&t);
    return 0;
}

const Valore *kc_valore(const Valori *v, const char *nome)
{
    for (size_t i = 0; i < v->n; i++)
        if (!strcmp(v->v[i].nome, nome)) return &v->v[i];
    return NULL;
}

void kc_libera_valori(Valori *v)
{
    for (size_t i = 0; i < v->n; i++) { free(v->v[i].nome); free(v->v[i].v); }
    free(v->v);
    v->v = NULL; v->n = 0;
}

/* ======================================================================
 *  Programmi
 * ====================================================================== */

void kc_inizio_programma(Testo *t, const char *libreria)
{
    t_str(t, "@0      START\n");
    t_str(t, libreria);
    t_str(t, "@1      PROC main\n");
}

void kc_fine_programma(Testo *t)
{
    t_str(t, "@1      END_PROC main\n@0      HALT\n");
}

void kc_istr(Testo *t, const char *fmt, ...)
{
    t_str(t, "@1      ");
    va_list ap;
    va_start(ap, fmt);
    t_vfmt(t, fmt, ap);
    va_end(ap);
    t_add(t, "\n", 1);
}

void kc_istr_bit(Testo *t, int i, const char *stack, const uint8_t *bit, size_t nbit)
{
    char uno[64], spinta[96];
    int l1 = snprintf(uno, sizeof uno, "@1      PUSHEQ t_%d 1\n", i);
    int l2 = snprintf(spinta, sizeof spinta, "@1      PUSH t_%d %s_%d\n", i, stack, i);
    for (size_t k = 0; k < nbit; k++) {
        if (bit[k]) t_add(t, uno, (size_t)l1);
        t_add(t, spinta, (size_t)l2);
    }
}

int kc_prendi_uscita(const Valori *v, int i, Frame *f, char **errore)
{
    char nome[32];
    snprintf(nome, sizeof nome, "uscita_%d", i);
    const Valore *u = kc_valore(v, nome);
    if (!u || !u->lista || u->n != f->n) {
        *errore = kc_strdup_printf("blocco ricostruito di lunghezza errata");
        return -1;
    }
    f->usc = mem(f->n);
    for (size_t k = 0; k < f->n; k++) {
        if (u->v[k] < 0 || u->v[k] > 255) {
            free(f->usc); f->usc = NULL;
            *errore = kc_strdup_printf("byte ricostruito fuori intervallo");
            return -1;
        }
        f->usc[k] = (uint8_t)u->v[k];
    }
    return 0;
}

/* ======================================================================
 *  Formato a frame (come comune/contenitore.py)
 * ====================================================================== */

typedef struct { FILE *f; uint32_t crc, crc_dati; uint64_t scritti; int errore; } Scrittore;

static void sc_scrivi(Scrittore *s, const void *b, size_t n)
{
    if (n && fwrite(b, 1, n, s->f) != n) s->errore = errno ? errno : EIO;
    s->crc = crc32_agg(s->crc, b, n);
    s->scritti += n;
}

static void sc_inizio(Scrittore *s, FILE *f, const Algoritmo *a, const int64_t *param)
{
    memset(s, 0, sizeof *s);
    s->f = f;
    uint8_t buf[64];
    size_t k = strlen(a->magia);
    memcpy(buf, a->magia, k);
    for (int i = 0; i < a->nparam; i++) k += varint(buf + k, (uint64_t)param[i]);
    sc_scrivi(s, buf, k);
}

static void sc_frame(Scrittore *s, const Blocco *b, int ultimo, int ncont)
{
    s->crc_dati = crc32_agg(s->crc_dati, b->dati, b->n);
    uint8_t testa[KC_MAX_CONT * 10 + 32];
    size_t lt = 0;
    int kairos = 0;
    if (b->kairos) {
        for (int k = 0; k < ncont; k++) lt += varint(testa + lt, (uint64_t)b->conti[k]);
        kairos = (b->nbit + 7) / 8 + lt < b->n;
    }
    uint8_t h[24];
    size_t lh = varint(h, (uint64_t)((kairos ? 0 : 1) + 2 * !!ultimo));
    lh += varint(h + lh, b->n);
    sc_scrivi(s, h, lh);
    if (kairos) {
        sc_scrivi(s, testa, lt);
        size_t nb = (b->nbit + 7) / 8;
        uint8_t *p = calloc(nb ? nb : 1, 1);
        if (!p) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
        for (size_t k = 0; k < b->nbit; k++)
            if (b->bit[k]) p[k >> 3] |= (uint8_t)(0x80 >> (k & 7));
        sc_scrivi(s, p, nb);
        free(p);
    } else {
        sc_scrivi(s, b->dati, b->n);
    }
    uint8_t c[4];
    if (ultimo) { be32(c, s->crc_dati); sc_scrivi(s, c, 4); }
    be32(c, s->crc);
    sc_scrivi(s, c, 4);
}

typedef struct { FILE *f; uint32_t crc; uint64_t letti; const Algoritmo *a; } Lettore;

#define DANNEGGIATO "il file e' danneggiato"

static size_t leggi_pieno(FILE *f, void *b, size_t n)
{
    size_t k = 0;
    while (k < n) {
        size_t r = fread((uint8_t *)b + k, 1, n - k, f);
        if (!r) break;
        k += r;
    }
    return k;
}

static int le_leggi(Lettore *l, void *b, size_t n, char **errore)
{
    size_t k = leggi_pieno(l->f, b, n);
    if (k < n) {
        *errore = ferror(l->f) ? kc_strdup_printf("errore di lettura: %s", strerror(errno))
                               : kc_strdup_printf("fine inattesa: il file e' troncato o danneggiato");
        return -1;
    }
    l->crc = crc32_agg(l->crc, b, n);
    l->letti += n;
    return 0;
}

static int le_varint(Lettore *l, uint64_t *v, char **errore)
{
    uint64_t x = 0;
    for (int s = 0; s < 70; s += 7) {
        uint8_t c;
        if (le_leggi(l, &c, 1, errore)) return -1;
        if (s == 63 && (c & 0x7E)) break;
        x |= (uint64_t)(c & 0x7F) << s;
        if (!(c & 0x80)) { *v = x; return 0; }
    }
    *errore = kc_strdup_printf("intestazione di frame non valida: " DANNEGGIATO);
    return -1;
}

/* 1: inizio di un flusso letto; 0: fine dell'ingresso dopo un flusso; -1 errore */
static int le_inizio(Lettore *l, int primo, int64_t *param, char **errore)
{
    size_t lm = strlen(l->a->magia);
    char m[16];
    size_t k = leggi_pieno(l->f, m, lm);
    l->letti += k;
    if (k == 0 && !primo) return 0;
    if (k != lm || memcmp(m, l->a->magia, lm)) {
        *errore = primo ? kc_strdup_printf("non e' un file %s", l->a->magia)
                        : kc_strdup_printf("dati non validi dopo la fine del flusso");
        return -1;
    }
    l->crc = crc32_agg(0, m, lm);
    for (int i = 0; i < l->a->nparam; i++) {
        uint64_t v;
        if (le_varint(l, &v, errore)) return -1;
        param[i] = (int64_t)v;
    }
    return 1;
}

typedef struct {
    int modo, ultimo;
    size_t n;
    int64_t conti[KC_MAX_CONT];
    uint8_t *corpo;        /* modo 1: i byte; modo 0: i bit, 0/1 */
    size_t nbit;
    uint32_t crc_dati;
} FrameLetto;

static int le_frame(Lettore *l, FrameLetto *fr, char **errore)
{
    memset(fr, 0, sizeof *fr);
    uint64_t tipo, n;
    if (le_varint(l, &tipo, errore) || le_varint(l, &n, errore)) return -1;
    if (tipo > 3 || n > KC_MAX_BLOCCO) {
        *errore = kc_strdup_printf("intestazione di frame non valida: " DANNEGGIATO);
        return -1;
    }
    fr->modo = (int)(tipo & 1);
    fr->ultimo = (int)(tipo >> 1);
    fr->n = (size_t)n;
    if (fr->modo == 0) {
        for (int k = 0; k < l->a->ncont; k++) {
            uint64_t v;
            if (le_varint(l, &v, errore)) return -1;
            fr->conti[k] = (int64_t)v;
        }
        uint64_t nbit = (uint64_t)fr->conti[l->a->ncont - 1];
        if (nbit >= 8 * n) {
            *errore = kc_strdup_printf("intestazione di frame non valida: " DANNEGGIATO);
            return -1;
        }
        size_t nb = (size_t)((nbit + 7) / 8);
        uint8_t *buf = mem(nb);
        if (le_leggi(l, buf, nb, errore)) { free(buf); return -1; }
        fr->nbit = (size_t)nbit;
        fr->corpo = mem(fr->nbit);
        for (size_t k = 0; k < fr->nbit; k++) fr->corpo[k] = (buf[k >> 3] >> (7 - (k & 7))) & 1;
        free(buf);
    } else {
        fr->corpo = mem(fr->n);
        if (le_leggi(l, fr->corpo, fr->n, errore)) { free(fr->corpo); fr->corpo = NULL; return -1; }
    }
    uint8_t c[4];
    if (fr->ultimo) {
        if (le_leggi(l, c, 4, errore)) goto male;
        fr->crc_dati = (uint32_t)c[0] << 24 | (uint32_t)c[1] << 16 | (uint32_t)c[2] << 8 | c[3];
    }
    uint32_t atteso = l->crc;
    if (le_leggi(l, c, 4, errore)) goto male;
    if (((uint32_t)c[0] << 24 | (uint32_t)c[1] << 16 | (uint32_t)c[2] << 8 | c[3]) != atteso) {
        *errore = kc_strdup_printf("CRC del file errato: " DANNEGGIATO);
        goto male;
    }
    return 0;
male:
    free(fr->corpo);
    fr->corpo = NULL;
    return -1;
}

/* ======================================================================
 *  Streaming
 * ====================================================================== */

static int gruppo_di(const Opzioni_flusso *o)
{
    return o && o->gruppo > 0 ? o->gruppo : kc_core();
}

int kc_comprimi(const Algoritmo *a, FILE *ing, FILE *usc, size_t dim, const int64_t *param,
                const Opzioni_flusso *o, Statistiche *st, char **errore)
{
    crc_init();
    memset(st, 0, sizeof *st);
    if (dim < 1 || dim > KC_MAX_BLOCCO) {
        *errore = kc_strdup_printf("dimensione del blocco fuori dai limiti");
        return KC_ERR_INTERNO;
    }
    int k = gruppo_di(o);
    Scrittore s;
    sc_inizio(&s, usc, a, param);
    Blocco *g = calloc((size_t)k, sizeof *g);
    uint8_t **buf = calloc((size_t)k + 1, sizeof *buf);
    int *ultimo = calloc((size_t)k, sizeof *ultimo);
    if (!g || !buf || !ultimo) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
    for (int i = 0; i <= k; i++) buf[i] = mem(dim);
    /* un blocco di anticipo per sapere qual e' l'ultimo */
    size_t ncur = leggi_pieno(ing, buf[k], dim);
    if (ferror(ing)) goto err_lettura;
    int fine = 0, esito = KC_OK;
    while (!fine) {
        int m = 0;
        while (m < k && !fine) {
            uint8_t *t = buf[m]; buf[m] = buf[k]; buf[k] = t;   /* il corrente va nel gruppo */
            size_t nxt = ncur == dim ? leggi_pieno(ing, buf[k], dim) : 0;
            if (ferror(ing)) goto err_lettura;
            memset(&g[m], 0, sizeof g[m]);
            g[m].dati = buf[m];
            g[m].n = ncur;
            ultimo[m] = nxt == 0;
            fine = ultimo[m];
            ncur = nxt;
            m++;
        }
        if (a->comprimi(a, g, m, param, errore)) { esito = KC_ERR_INTERNO; break; }
        for (int i = 0; i < m; i++) {
            sc_frame(&s, &g[i], ultimo[i], a->ncont);
            st->ingresso += g[i].n;
            free(g[i].bit);
            g[i].bit = NULL;
        }
        st->blocchi += (uint64_t)m;
        st->gruppi++;
        st->uscita = s.scritti;
        fflush(usc);
        if (s.errore) {
            *errore = kc_strdup_printf("errore di scrittura: %s", strerror(s.errore));
            esito = KC_ERR_IO;
            break;
        }
        if (o && o->avanzamento) o->avanzamento(st, o->dato);
    }
    for (int i = 0; i <= k; i++) free(buf[i]);
    free(buf); free(g); free(ultimo);
    return esito;
err_lettura:
    *errore = kc_strdup_printf("errore di lettura: %s", strerror(errno));
    for (int i = 0; i <= k; i++) free(buf[i]);
    free(buf); free(g); free(ultimo);
    return KC_ERR_IO;
}

int kc_decomprimi(const Algoritmo *a, FILE *ing, FILE *usc, const Opzioni_flusso *o,
                  Statistiche *st, char **errore)
{
    crc_init();
    memset(st, 0, sizeof *st);
    int k = gruppo_di(o);
    Lettore l = { .f = ing, .a = a };
    FrameLetto *g = calloc((size_t)k, sizeof *g);
    Frame *fk = calloc((size_t)k, sizeof *fk);
    int *qual = calloc((size_t)k, sizeof *qual);
    if (!g || !fk || !qual) { fputs("memoria esaurita\n", stderr); exit(KC_ERR_IO); }
    int primo = 1, esito = KC_OK;
    for (;;) {
        int64_t param[2] = {0, 0};
        int r = le_inizio(&l, primo, param, errore);
        if (r < 0) { esito = KC_ERR_DATI; break; }
        if (r == 0) break;
        primo = 0;
        uint32_t crc = 0;
        int fine = 0;
        while (!fine && esito == KC_OK) {
            int m = 0, nk = 0;
            while (m < k && !fine) {
                if (le_frame(&l, &g[m], errore)) { esito = KC_ERR_DATI; break; }
                fine = g[m].ultimo;
                m++;
            }
            if (esito != KC_OK) { for (int i = 0; i < m; i++) free(g[i].corpo); break; }
            for (int i = 0; i < m; i++)
                if (g[i].modo == 0) {
                    memset(&fk[nk], 0, sizeof fk[nk]);
                    fk[nk].n = g[i].n;
                    memcpy(fk[nk].conti, g[i].conti, sizeof g[i].conti);
                    fk[nk].bit = g[i].corpo;
                    fk[nk].nbit = g[i].nbit;
                    qual[i] = nk++;
                }
            if (nk && a->decomprimi(a, fk, nk, param, errore)) {
                esito = KC_ERR_DATI;
                for (int i = 0; i < nk; i++) free(fk[i].usc);
                for (int i = 0; i < m; i++) free(g[i].corpo);
                break;
            }
            for (int i = 0; i < m; i++) {
                const uint8_t *b = g[i].modo == 0 ? fk[qual[i]].usc : g[i].corpo;
                crc = crc32_agg(crc, b, g[i].n);
                if (g[i].n && fwrite(b, 1, g[i].n, usc) != g[i].n) {
                    *errore = kc_strdup_printf("errore di scrittura: %s", strerror(errno));
                    esito = KC_ERR_IO;
                }
                st->uscita += g[i].n;
            }
            uint32_t crc_fine = m ? g[m - 1].crc_dati : 0;
            for (int i = 0; i < nk; i++) { free(fk[i].usc); fk[i].usc = NULL; }
            for (int i = 0; i < m; i++) { free(g[i].corpo); g[i].corpo = NULL; }
            st->blocchi += (uint64_t)m;
            st->gruppi++;
            st->ingresso = l.letti;
            if (fflush(usc) && esito == KC_OK) {
                *errore = kc_strdup_printf("errore di scrittura: %s", strerror(errno));
                esito = KC_ERR_IO;
            }
            if (esito == KC_OK && o && o->avanzamento) o->avanzamento(st, o->dato);
            if (fine && esito == KC_OK && crc != crc_fine) {
                *errore = kc_strdup_printf("CRC dei dati ricostruiti errato");
                esito = KC_ERR_DATI;
            }
        }
        if (esito != KC_OK) break;
    }
    st->ingresso = l.letti;
    free(g); free(fk); free(qual);
    return esito;
}

int kc_elenca(const Algoritmo *a, FILE *ing, Elenco *e, char **errore)
{
    crc_init();
    memset(e, 0, sizeof *e);
    Lettore l = { .f = ing, .a = a };
    int primo = 1;
    for (;;) {
        int64_t param[2] = {0, 0};
        int r = le_inizio(&l, primo, param, errore);
        if (r < 0) return KC_ERR_DATI;
        if (r == 0) break;
        if (primo) e->param0 = param[0];
        primo = 0;
        e->flussi++;
        for (int fine = 0; !fine;) {
            FrameLetto fr;
            if (le_frame(&l, &fr, errore)) return KC_ERR_DATI;
            fine = fr.ultimo;
            e->blocchi++;
            e->originali += fr.n;
            free(fr.corpo);
        }
    }
    e->compressi = l.letti;
    return KC_OK;
}

/* ======================================================================
 *  La riga di comando: file, nomi, permessi, messaggi
 * ====================================================================== */

static const char *g_uscita_parziale;     /* da cancellare se arriva un segnale */

static void al_segnale(int s)
{
    if (g_uscita_parziale) unlink(g_uscita_parziale);
    signal(s, SIG_DFL);
    raise(s);
}

typedef struct {
    const Algoritmo *a;
    Comando *c;
    const char *nome;
    int mostra;
} Avanz;

static void avanzamento(const Statistiche *st, void *dato)
{
    Avanz *av = dato;
    if (!av->mostra) return;
    fprintf(stderr, "\r%s: %s: %llu blocchi, %llu KiB -> %llu KiB", av->a->nome, av->nome,
            (unsigned long long)st->blocchi, (unsigned long long)(st->ingresso >> 10),
            (unsigned long long)(st->uscita >> 10));
    fflush(stderr);
}

static void pulisci_riga(Avanz *av)
{
    if (av->mostra) { fputs("\r\033[K", stderr); fflush(stderr); }
}

/* gravita' degli esiti: 0 ok, 1 avviso, 2 errore */
typedef struct { int gravita; int codice; } Esito;

static void esito_avviso(const Comando *c, Esito *e)
{
    if (e->gravita < 1) { e->gravita = 1; e->codice = c->stile_xz ? 2 : 1; }
}

static void esito_errore(const Comando *c, Esito *e, int tipo)
{
    int codice;
    if (c->stile_xz) codice = 1;
    else codice = tipo == KC_ERR_DATI ? 2 : tipo == KC_ERR_INTERNO ? 3 : 1;
    if (e->gravita < 2 || codice > e->codice) { e->gravita = 2; e->codice = codice; }
}

static void msg(const Algoritmo *a, const Comando *c, int errore, const char *fmt, ...)
    __attribute__((format(printf, 4, 5)));

static void msg(const Algoritmo *a, const Comando *c, int errore, const char *fmt, ...)
{
    if (c->silenzio >= 2 || (!errore && c->silenzio >= 1)) return;
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "%s: ", a->nome);
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
}

static void dettagli(const Algoritmo *a, const Comando *c, const char *nome, int comp,
                     const Statistiche *st)
{
    if (c->verbosita < 1 || c->silenzio) return;
    if (comp) {
        double i = (double)st->ingresso, u = (double)st->uscita;
        if (st->ingresso)
            fprintf(stderr, "  %s: %6.3f:1, %6.3f bit/byte, %5.2f%% risparmiato, %llu in ingresso, %llu in uscita.\n",
                    nome, u ? i / u : 0.0, 8.0 * u / i, 100.0 * (1.0 - u / i),
                    (unsigned long long)st->ingresso, (unsigned long long)st->uscita);
        else
            fprintf(stderr, "  %s: nessun dato in ingresso, %llu in uscita.\n", nome,
                    (unsigned long long)st->uscita);
    } else {
        fprintf(stderr, "  %s: fatto (%llu -> %llu byte)\n", nome,
                (unsigned long long)st->ingresso, (unsigned long long)st->uscita);
    }
    (void)a;
}

static int ha_suffisso(const char *nome, const char *suf)
{
    size_t ln = strlen(nome), ls = strlen(suf);
    return ln > ls && !strcmp(nome + ln - ls, suf);
}

typedef struct { FILE *f; } Nulla;

static FILE *apri_nulla(void)
{
    FILE *f = fopen("/dev/null", "wb");
    return f;
}

static void stampa_elenco(const Algoritmo *a, const char *nome, const Elenco *e, int intestazione)
{
    if (intestazione)
        printf("Flussi Blocchi   Compresso  Originale  Rapporto  Controllo  Nome file\n");
    double r = e->originali ? (double)e->compressi / (double)e->originali : 0.0;
    printf("%6llu %7llu %11llu %10llu  %8.3f  %-9s  %s\n", (unsigned long long)e->flussi,
           (unsigned long long)e->blocchi, (unsigned long long)e->compressi,
           (unsigned long long)e->originali, r, "CRC32", nome);
    (void)a;
}

static int lavora(const Algoritmo *a, Comando *c, FILE *ing, FILE *usc, const char *nome,
                  int comp, Statistiche *st, char **errore)
{
    Avanz av = { a, c, nome, c->verbosita >= 1 && !c->silenzio && isatty(2) };
    Opzioni_flusso o = { c->gruppo, avanzamento, &av };
    int r = comp ? kc_comprimi(a, ing, usc, c->dim_blocco, c->param, &o, st, errore)
                 : kc_decomprimi(a, ing, usc, &o, st, errore);
    pulisci_riga(&av);
    return r;
}

static void copia_attributi(int fd, const struct stat *s)
{
    if (fchmod(fd, s->st_mode & 07777)) {}
    struct timespec t[2] = { s->st_atim, s->st_mtim };
    if (futimens(fd, t)) {}
}

static void un_file(const Algoritmo *a, Comando *c, const char *nome, Esito *es, Elenco *tot,
                    int *n_elenco)
{
    struct stat s;
    if (stat(nome, &s)) {
        msg(a, c, 1, c->stile_xz ? "%s: %s" : "impossibile aprire il file d'ingresso %s: %s",
            nome, strerror(errno));
        esito_errore(c, es, KC_ERR_IO);
        return;
    }
    if (S_ISDIR(s.st_mode)) {
        msg(a, c, 0, c->stile_xz ? "%s: e' una cartella, salto" : "il file d'ingresso %s e' una cartella",
            nome);
        esito_avviso(c, es);
        return;
    }
    if (!S_ISREG(s.st_mode) && !c->forza && !c->su_stdout && !c->test && !c->lista) {
        msg(a, c, 0, c->stile_xz ? "%s: non e' un file regolare, salto"
                                 : "il file d'ingresso %s non e' un file regolare", nome);
        esito_avviso(c, es);
        return;
    }
    FILE *ing = fopen(nome, "rb");
    if (!ing) {
        msg(a, c, 1, c->stile_xz ? "%s: %s" : "impossibile aprire il file d'ingresso %s: %s",
            nome, strerror(errno));
        esito_errore(c, es, KC_ERR_IO);
        return;
    }
    char *errore = NULL;
    Statistiche st;
    if (c->lista) {
        Elenco e;
        int r = kc_elenca(a, ing, &e, &errore);
        fclose(ing);
        if (r) { msg(a, c, 1, "%s: %s", nome, errore); free(errore); esito_errore(c, es, r); return; }
        stampa_elenco(a, nome, &e, (*n_elenco)++ == 0);
        tot->flussi += e.flussi; tot->blocchi += e.blocchi;
        tot->compressi += e.compressi; tot->originali += e.originali;
        return;
    }
    if (c->test) {
        FILE *nulla = apri_nulla();
        int r = nulla ? lavora(a, c, ing, nulla, nome, 0, &st, &errore) : KC_ERR_IO;
        if (nulla) fclose(nulla);
        fclose(ing);
        if (r) {
            msg(a, c, 1, "%s: %s", nome, errore ? errore : strerror(errno));
            free(errore);
            esito_errore(c, es, r);
        } else if (c->verbosita >= 1 && !c->silenzio) {
            fprintf(stderr, "  %s: ok\n", nome);
        }
        return;
    }
    int comp = !c->decomprimi;
    char *dest = NULL;
    if (comp) {
        if (ha_suffisso(nome, c->suffisso) && !c->forza && !c->su_stdout) {
            msg(a, c, 0, c->stile_xz ? "%s: ha gia' il suffisso '%s', salto"
                                     : "il file d'ingresso %s ha gia' il suffisso %s", nome, c->suffisso);
            esito_avviso(c, es);
            fclose(ing);
            return;
        }
        dest = kc_strdup_printf("%s%s", nome, c->suffisso);
    } else if (ha_suffisso(nome, c->suffisso)) {
        dest = strndup(nome, strlen(nome) - strlen(c->suffisso));
    } else if (!c->su_stdout) {
        if (c->stile_xz) {
            msg(a, c, 0, "%s: suffisso sconosciuto, salto", nome);
            esito_avviso(c, es);
            fclose(ing);
            return;
        }
        dest = kc_strdup_printf("%s.out", nome);
        msg(a, c, 0, "non so ricavare il nome originale di %s: uso %s", nome, dest);
    }
    if (c->su_stdout) {
        free(dest);
        int r = lavora(a, c, ing, stdout, nome, comp, &st, &errore);
        fclose(ing);
        if (r) { msg(a, c, 1, "%s: %s", nome, errore); free(errore); esito_errore(c, es, r); return; }
        dettagli(a, c, nome, comp, &st);
        return;
    }
    struct stat sd;
    if (!lstat(dest, &sd)) {
        if (!c->forza) {
            msg(a, c, 1, c->stile_xz ? "%s: il file esiste gia'" : "il file d'uscita %s esiste gia'", dest);
            esito_errore(c, es, KC_ERR_IO);
            free(dest);
            fclose(ing);
            return;
        }
        unlink(dest);
    }
    int fd = open(dest, O_WRONLY | O_CREAT | O_EXCL, 0600);
    FILE *usc = fd >= 0 ? fdopen(fd, "wb") : NULL;
    if (!usc) {
        msg(a, c, 1, "%s: %s", dest, strerror(errno));
        esito_errore(c, es, KC_ERR_IO);
        if (fd >= 0) { close(fd); unlink(dest); }
        free(dest);
        fclose(ing);
        return;
    }
    g_uscita_parziale = dest;
    int r = lavora(a, c, ing, usc, nome, comp, &st, &errore);
    if (!r && fflush(usc)) {
        errore = kc_strdup_printf("errore di scrittura: %s", strerror(errno));
        r = KC_ERR_IO;
    }
    if (!r) copia_attributi(fileno(usc), &s);
    if (fclose(usc) && !r) {
        errore = kc_strdup_printf("errore di scrittura: %s", strerror(errno));
        r = KC_ERR_IO;
    }
    fclose(ing);
    if (r) {
        unlink(dest);
        g_uscita_parziale = NULL;
        msg(a, c, 1, "%s: %s", nome, errore);
        free(errore);
        free(dest);
        esito_errore(c, es, r);
        return;
    }
    g_uscita_parziale = NULL;
    dettagli(a, c, nome, comp, &st);
    if (!c->tieni && unlink(nome)) {
        msg(a, c, 0, "%s: non riesco a cancellare l'ingresso: %s", nome, strerror(errno));
        esito_avviso(c, es);
    }
    free(dest);
}

int kc_esegui_comando(const Algoritmo *a, Comando *c, char **file, int n)
{
    crc_init();
    signal(SIGINT, al_segnale);
    signal(SIGTERM, al_segnale);
    signal(SIGHUP, al_segnale);
    if (!c->suffisso) c->suffisso = a->estensione;
    Esito es = {0, 0};
    int comp = !c->decomprimi && !c->test && !c->lista;
    if (n == 0 || (n == 1 && !strcmp(file[0], "-"))) {
        if (c->lista) {
            msg(a, c, 1, "--list non legge dallo standard input");
            return 1;
        }
        if (comp && isatty(1) && !c->forza) {
            msg(a, c, 1, "non scrivo dati compressi su un terminale (usa -f per farlo comunque)");
            return 1;
        }
        if (!comp && isatty(0) && !c->forza) {
            msg(a, c, 1, "non leggo dati compressi da un terminale (usa -f per farlo comunque)");
            return 1;
        }
        char *errore = NULL;
        Statistiche st;
        FILE *usc = stdout, *nulla = NULL;
        if (c->test) { nulla = apri_nulla(); usc = nulla ? nulla : stdout; }
        int r = lavora(a, c, stdin, usc, "(stdin)", comp, &st, &errore);
        if (nulla) fclose(nulla);
        if (r) { msg(a, c, 1, "(stdin): %s", errore); free(errore); esito_errore(c, &es, r); }
        else if (c->test && c->verbosita >= 1 && !c->silenzio) fprintf(stderr, "  (stdin): ok\n");
        else dettagli(a, c, "(stdin)", comp, &st);
        return es.codice;
    }
    if (comp && c->su_stdout && isatty(1) && !c->forza) {
        msg(a, c, 1, "non scrivo dati compressi su un terminale (usa -f per farlo comunque)");
        return 1;
    }
    Elenco tot = {0};
    int n_elenco = 0;
    for (int i = 0; i < n; i++) un_file(a, c, file[i], &es, &tot, &n_elenco);
    if (c->lista && n_elenco > 1) {
        printf("-------------------------------------------------------------------------\n");
        double r = tot.originali ? (double)tot.compressi / (double)tot.originali : 0.0;
        printf("%6llu %7llu %11llu %10llu  %8.3f  %-9s  %d file\n", (unsigned long long)tot.flussi,
               (unsigned long long)tot.blocchi, (unsigned long long)tot.compressi,
               (unsigned long long)tot.originali, r, "CRC32", n_elenco);
    }
    fflush(stdout);
    return es.codice;
}
