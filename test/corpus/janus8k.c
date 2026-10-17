#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

/* ── ordine di inclusione importante ── */
#define DEFINE_VM_DEBUG_PANIC
#include "vm_panic.h"   // ← deve venire prima di tutti gli altri
#include "vm_types.h"
#include "vm_helpers.h"
#include "vm_channel.h"
#include "vm_frames.h"
#include "vm_ops.h"
#include "vm_par.h"      /* deve venire prima: definisce ParBlock, scan_par_block, exec_par_threads */
#include "vm_invert.h"   /* usa ParBlock e exec_par_threads definiti sopra */
#include "vm_debug.h"    /* debug hook, dump JSON, breakpoint management  */
#include "Kairos_core.h"


/* Puntatore alla VM corrente — usato da vm_printf in DAP_MODE */
VM *g_current_vm = NULL;
void vm_print_stats(VM *vm);          /* fwd: --vm-stats (def più sotto) */
static int g_vm_stats_enabled;        /* tentative decl (def con =0 più sotto) */
/* ── thread-local state (dichiarate extern in vm_types.h) ── */
__thread ThreadArgs *current_thread_args = NULL;
__thread char       *strtok_saveptr      = NULL;
__thread uint        thread_val_IF       = 0;

pthread_mutex_t var_indexer_mtx = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t char_id_map_ins_mtx = PTHREAD_MUTEX_INITIALIZER;   /* char_id_map.h */
CharIdMap       FrameIndexer;

/* ======================================================================
 *  Macro DEBUG_HOOK — inserita prima di ogni istruzione in vm_run_BT.
 *
 *  Estrae il numero di riga dalla stringa corrente (i primi 4 caratteri
 *  del formato "NNNN  OP ...") e chiama dbg_hook se il debugger è attivo.
 *
 *  ptr punta all'inizio della riga (prima che venga modificata con \0).
 *  instr_text è lb (la copia della riga già disponibile).
 * ====================================================================== */

static inline int extract_lineno(const char *raw_line)
{
    /* Estrae il numero fisico di riga: tutte le cifre iniziali ("%04u" ne
       scrive almeno 4, oltre la riga 9999 di più). */
    return atoi(raw_line);
}

static inline int extract_srcline(const char *raw_line)
{
    /* Formato: "NNNN  @SRC   OP" — cerca '@' e legge il numero sorgente */
    const char *at = strchr(raw_line, '@');
    if (!at) return extract_lineno(raw_line); /* fallback al fisico */
    return atoi(at + 1);
}

/* Annidamento di vm_run_BT nel thread: 1 = l'esecuzione del programma; di
 * piu' solo dentro un'inversione (uncall eseguite in avanti mentre si inverte),
 * dove il passo indietro del debugger non si applica. */
static __thread int g_run_bt_depth = 0;

/* ======================================================================
 *  vm_run_BT — loop principale di esecuzione
 * ====================================================================== */

void vm_stats_sample(VM *vm);

/* Nome del frame corrente di vm_run_BT, e nome del chiamante salvato in un
 * CallRecord: buffer che crescono solo quando il nome nuovo non ci sta. Nessuna
 * lunghezza massima e nessuna allocazione per chiamata a regime. */
static inline void vm_buf_set(char **buf, size_t *cap, const char *src)
{
    size_t l = strlen(src) + 1;
    if (l > *cap) {
        size_t nc = *cap ? *cap : 32;
        while (nc < l) nc *= 2;
        char *n = (char *)realloc(*buf, nc);
        if (!n) vm_debug_panic("[VM] frame name: out of memory\n");
        *buf = n; *cap = nc;
    }
    memcpy(*buf, src, l);
}

void vm_run_BT(VM *vm, char *buffer, char *frame_name_init)
{
    g_current_vm = vm;
    /* Il bytecode si legge soltanto: nessuna copia, lo stesso testo per tutti. */
    char *orig = buffer;
    char  *fname = NULL;
    size_t fname_cap = 0;
    vm_buf_set(&fname, &fname_cap, frame_name_init);

    /* Un record per chiamata attiva. I parametri salvati e il nome del chiamante
     * sono buffer del record, riusati dalle chiamate successive alla stessa
     * profondità: crescono quando servono, nessun numero massimo di parametri
     * né lunghezza massima del nome. */
    typedef struct {
        char  *return_ptr;
        char  *caller_frame;
        size_t caller_frame_cap;
        Var  **saved_params;
        int    saved_params_cap;
        int    saved_param_count, callee_findex;
        Stack  saved_local_vars;
        int    is_recursive_clone;
        int    base_findex;   /* frame-base della proc chiamata: per decremento `active` a END_PROC */
        int    hist_at_call;  /* debugger: indice nella storia della riga CALL */
    } CallRecord;
    /* Call stack dinamico: cresce on-demand (raddoppia). Nessun hard cap.
     * Gli slot nuovi sono azzerati: i loro buffer partono vuoti. */
    uint cs_cap = 64;
    CallRecord *cs = calloc(cs_cap, sizeof(CallRecord));
    if (!cs) vm_debug_panic("[VM] call stack: out of memory\n");
    int cs_top = -1;
#define VM_CS_ENSURE(needed) do { \
    if ((uint)(needed) >= cs_cap) { \
        uint _nc = cs_cap; while (_nc <= (uint)(needed)) _nc *= 2; \
        CallRecord *_nb = (CallRecord *)realloc(cs, sizeof(CallRecord) * _nc); \
        if (!_nb) vm_debug_panic("[VM] CALL: realloc(%u) failed\n", _nc); \
        memset(_nb + cs_cap, 0, sizeof(CallRecord) * (_nc - cs_cap)); \
        cs = _nb; cs_cap = _nc; \
    } \
} while (0)
    g_run_bt_depth++;
    uint  si  = char_id_map_get(&FrameIndexer, fname);
    char *ptr = go_to_line(orig, vm->frames[si]->addr + 1);
    if (!ptr) { fprintf(stderr, "ERROR: '%s' not found\n", fname); goto done; }

    while (*ptr) {
        char *nl = strchr(ptr, '\n'); if (!nl) break;
        VM_LINE_DUP(lb, ptr, nl);
        char *fw = strtok(skip_lineno(lb), " \t");

        if (!fw) { ptr = nl + 1; continue; }

        /* ── DEBUG HOOK ── chiamato prima di ogni istruzione breakpointable ── */
        if (strcmp(fw, "PROC") != 0 && strcmp(fw, "PARAM") != 0 &&
            strcmp(fw, "HALT") != 0) {
            if (vm->dbg && vm->dbg->initialized) {
                VM_LINE_DUP(raw, ptr, nl);    /* riga intatta, per il debugger */
                int can = (g_run_bt_depth == 1 && !current_thread_args);
                int back = dbg_hook(vm->dbg, extract_srcline(raw), fname, raw, can);
                if (vm->dbg->mode == VM_MODE_DONE && g_inversion_depth == 0) goto done;
                if (back) {
                    /* Passo indietro: l'inversa dell'istruzione precedente, poi
                     * l'esecuzione riparte da quella istruzione. */
                    ptr = dbg_step_back_here(vm, orig, fname, ptr,
                                             cs_top >= 0 ? cs[cs_top].hist_at_call : -1);
                    continue;
                }
            }
            vm_stats_sample(vm);
        }

        if (!strcmp(fw, "END_PROC")) {
            uint fi = get_findex(fname);
            if (stack_size(&vm->frames[fi]->LocalVariables) > -1) {
                vm_debug_panic("[VM] END_PROC: LOCAL variables not closed\n");
            }
            if (cs_top >= 0) {
                int cfi = cs[cs_top].callee_findex;
                if (vm->frames[cs[cs_top].base_findex]->active > 0)
                    vm->frames[cs[cs_top].base_findex]->active--;
                for (int k = 0; k < cs[cs_top].saved_param_count; k++)
                    vm->frames[cfi]->vars[vm->frames[cfi]->param_indices[k]] = cs[cs_top].saved_params[k];
                stack_restore(&vm->frames[cfi]->LocalVariables, cs[cs_top].saved_local_vars);
                /* Non liberare i Var PARAM dei cloni ricorsivi qui: sono guscio allocato
                 * in init_clone_frame; free() tra restore e ripresa del chiamante può
                 * corrompere l'heap o interferire con alias ancora attivi. vm_free() a
                 * fine esecuzione deduplica i Var* condivisi. */
                ptr = cs[cs_top].return_ptr;
                vm_buf_set(&fname, &fname_cap, cs[cs_top].caller_frame);
                cs_top--;
            } else break;
            continue;
        }
        else if (!strcmp(fw, "CALL")) {
            char *pn      = strtok(NULL, " \t");
            uint  cfi_cur = get_findex(fname);
            int   is_rec    = vm_base_eq(fname, pn);
            int   new_depth = 0;
            if (is_rec) {
                char *at2 = strchr(fname, '@');
       