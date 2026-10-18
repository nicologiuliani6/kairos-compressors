/* kc: il driver nativo comune a kgzip2 e klzma.
 *
 * Legge i dati a blocchi, scrive per ogni gruppo di blocchi il programma
 * Kairos (libreria tradotta in fase di build + un main generato qui, con i
 * dati come istruzioni di bytecode), lo esegue nella VM di Kairos linkata nel
 * binario e scrive i frame. Il formato e' quello di comune/contenitore.py.
 */
#ifndef KC_H
#define KC_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define KC_MAX_BLOCCO (1u << 20)
#define KC_MAX_CONT 8

/* --- testo che cresce ---------------------------------------------------- */
typedef struct { char *s; size_t n, cap; } Testo;
void t_add(Testo *t, const char *s, size_t n);
void t_str(Testo *t, const char *s);
void t_fmt(Testo *t, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
void t_libera(Testo *t);

/* --- la VM ---------------------------------------------------------------- */
typedef struct { char *nome; int lista; int64_t val; int64_t *v; size_t n; } Valore;
typedef struct { Valore *v; size_t n; } Valori;
/* Esegue il bytecode in un processo figlio. 0 se tutto bene; altrimenti -1 e
 * in *errore il messaggio della VM (da liberare). */
int kc_esegui(const char *bytecode, Valori *out, char **errore);
const Valore *kc_valore(const Valori *v, const char *nome);
void kc_libera_valori(Valori *v);

/* --- un algoritmo ---------------------------------------------------------- */
typedef struct {
    const uint8_t *dati; size_t n;           /* ingresso del blocco */
    int kairos;                              /* in uscita: 1 se va in un frame Kairos */
    int64_t conti[KC_MAX_CONT];              /* contatori; l'ultimo e' il numero di bit */
    uint8_t *bit; size_t nbit;               /* bit compressi, 0/1 */
} Blocco;

typedef struct {
    size_t n; int64_t conti[KC_MAX_CONT];
    uint8_t *bit; size_t nbit;               /* ingresso */
    uint8_t *usc;                            /* in uscita: n byte */
} Frame;

typedef struct Algoritmo {
    const char *nome, *estensione, *magia;
    int nparam, ncont;
    /* comprime un gruppo: imposta kairos/conti/bit dei blocchi che vanno alla VM */
    int (*comprimi)(const struct Algoritmo *a, Blocco *b, int k, const int64_t *param, char **errore);
    int (*decomprimi)(const struct Algoritmo *a, Frame *f, int k, const int64_t *param, char **errore);
} Algoritmo;

/* Bytecode della libreria (da genera.py) e chiusura del programma */
void kc_inizio_programma(Testo *t, const char *libreria);
void kc_fine_programma(Testo *t);
void kc_istr(Testo *t, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
/* bit come istruzioni: PUSHEQ t_i 1 / PUSH t_i <stack>_i */
void kc_istr_bit(Testo *t, int i, const char *stack, const uint8_t *bit, size_t nbit);
/* uscita di scarica: lo stack uscita_i come byte */
int kc_prendi_uscita(const Valori *v, int i, Frame *f, char **errore);

/* --- streaming ------------------------------------------------------------- */
typedef struct {
    uint64_t ingresso, uscita, blocchi, gruppi;
} Statistiche;

typedef struct {
    int gruppo;                  /* blocchi per esecuzione della VM */
    void (*avanzamento)(const Statistiche *st, void *dato);
    void *dato;
} Opzioni_flusso;

enum { KC_OK = 0, KC_ERR_IO = 1, KC_ERR_DATI = 2, KC_ERR_INTERNO = 3 };

int kc_comprimi(const Algoritmo *a, FILE *ing, FILE *usc, size_t dim, const int64_t *param,
                const Opzioni_flusso *o, Statistiche *st, char **errore);
int kc_decomprimi(const Algoritmo *a, FILE *ing, FILE *usc, const Opzioni_flusso *o,
                  Statistiche *st, char **errore);

/* Elenco (-l): flussi, frame, byte compressi e originali, senza la VM */
typedef struct { uint64_t flussi, blocchi, compressi, originali; int64_t param0; } Elenco;
int kc_elenca(const Algoritmo *a, FILE *ing, Elenco *e, char **errore);

int kc_core(void);
char *kc_strdup_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* --- la riga di comando ----------------------------------------------------- */
typedef struct {
    int decomprimi, test, lista, tieni, forza, su_stdout;
    int verbosita;               /* -v ripetibile */
    int silenzio;                /* -q ripetibile */
    int gruppo;                  /* 0 = i core */
    size_t dim_blocco;
    int64_t param[2];
    int stile_xz;                /* messaggi e codici d'uscita come xz invece che bzip2 */
    const char *suffisso;        /* estensione dei file compressi */
} Comando;

/* Esegue il comando su `file` (n nomi; n == 0: stdin -> stdout). Restituisce
 * il codice d'uscita. */
int kc_esegui_comando(const Algoritmo *a, Comando *c, char **file, int n);

#endif
