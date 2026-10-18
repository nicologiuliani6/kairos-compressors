"""Il formato dei file compressi, comune a kgzip2 e klzma.

    MAGIA, poi i parametri dell'algoritmo (varint)
    un frame per blocco, in ordine:
        tipo        varint: modo + 2 * ultimo  (modo 0 Kairos, 1 memorizzato)
        n           varint: byte originali del blocco
        modo 0      i contatori dell'algoritmo in varint (l'ultimo e' il
                    numero di bit), poi i bit impacchettati
        modo 1      gli n byte
        se ultimo   CRC32 di tutti i dati originali (4 byte)
        CRC32 del file dal primo byte fino a qui (4 byte)

Il formato si scrive e si legge frame per frame, senza conoscere in anticipo
la lunghezza dei dati. Il CRC di un frame copre tutto il file fino a quel
punto: si controlla appena il frame e' letto, prima di passarlo alla VM, quindi
un file alterato si ferma al primo frame danneggiato e non arriva mai
all'`uncall`. Il CRC dei dati originali si controlla alla fine. Piu' flussi
concatenati (`cat a.klz b.klz`) si decomprimono nella concatenazione dei dati,
come in gzip e xz.
"""
import zlib
from collections import namedtuple

MAX_BLOCCO = 1 << 20          # limite di lettura di n, contro i file alterati
MAX_VARINT = 10


class FileNonValido(Exception):
    pass


DANNEGGIATO = 'il file e\' danneggiato'


def varint(v):
    o = bytearray()
    while True:
        c = v & 0x7F
        v >>= 7
        o.append(c | (0x80 if v else 0))
        if not v:
            return bytes(o)


def impacchetta_bit(bits):
    b = list(bits) + [0] * (-len(bits) % 8)
    return bytes(int(''.join(map(str, b[k:k + 8])), 2) for k in range(0, len(b), 8))


def spacchetta_bit(buf, nbit):
    bits = [int(c) for byte in buf for c in f'{byte:08b}']
    if len(bits) < nbit:
        raise FileNonValido('dati compressi troncati')
    return bits[:nbit]


def leggi_pieno(f, k):
    """Fino a k byte da f: meno solo se f e' finito (le pipe danno letture corte)."""
    b = bytearray()
    while len(b) < k:
        c = f.read(k - len(b))
        if not c:
            break
        b += c
    return bytes(b)


class Scrittore:
    """Scrive un flusso frame per frame, tenendo i due CRC."""

    def __init__(self, uscita, magia, parametri=()):
        self.uscita = uscita
        self.crc = 0              # del file fin qui
        self.crc_dati = 0         # dei dati originali fin qui
        self.scritti = 0
        self._scrivi(magia + b''.join(varint(p) for p in parametri))

    def _scrivi(self, b):
        self.uscita.write(b)
        self.crc = zlib.crc32(b, self.crc)
        self.scritti += len(b)

    def frame(self, dati, conti, bits, ultimo):
        """conti None: il blocco si memorizza; si memorizza anche quando i bit
        non sono piu' corti dei dati. Restituisce True se il frame e' in modo 0."""
        self.crc_dati = zlib.crc32(dati, self.crc_dati)
        testa = b''.join(varint(v) for v in conti) if conti is not None else b''
        kairos = conti is not None and (len(bits) + 7) // 8 + len(testa) < len(dati)
        f = varint((0 if kairos else 1) + 2 * bool(ultimo)) + varint(len(dati))
        f += (testa + impacchetta_bit(bits)) if kairos else bytes(dati)
        if ultimo:
            f += self.crc_dati.to_bytes(4, 'big')
        self._scrivi(f)
        self._scrivi(self.crc.to_bytes(4, 'big'))
        return kairos


Frame = namedtuple('Frame', 'modo n conti carico ultimo crc_dati')


class Lettore:
    """Legge un flusso frame per frame: un frame esce solo se il suo CRC torna."""

    def __init__(self, ingresso, magia, nparametri, ncontatori, controlla_crc=True):
        self.controlla_crc = controlla_crc     # False solo per gli esperimenti (--salta-crc)
        self.ingresso = ingresso
        self.magia = magia
        self.nparametri = nparametri
        self.ncontatori = ncontatori
        self.crc = 0
        self.letti = 0

    def inizia(self, primo=True):
        """Firma e parametri di un flusso. None se l'ingresso e' finito dopo un
        flusso completo."""
        m = leggi_pieno(self.ingresso, len(self.magia))
        self.letti += len(m)
        if not m and not primo:
            return None
        if m != self.magia:
            raise FileNonValido(f'non e\' un file {self.magia.decode()}' if primo
                                else 'dati non validi dopo la fine del flusso')
        self.crc = zlib.crc32(m)
        return [self._varint() for _ in range(self.nparametri)]

    def _leggi(self, k):
        b = leggi_pieno(self.ingresso, k)
        if len(b) < k:
            raise FileNonValido('fine inattesa: il file e\' troncato o danneggiato')
        self.crc = zlib.crc32(b, self.crc)
        self.letti += k
        return b

    def _varint(self):
        v = s = 0
        for _ in range(MAX_VARINT):
            c = self._leggi(1)[0]
            v |= (c & 0x7F) << s
            s += 7
            if not c & 0x80:
                return v
        raise FileNonValido('intestazione di frame non valida: ' + DANNEGGIATO)

    def frame(self):
        tipo = self._varint()
        n = self._varint()
        if tipo > 3 or n > MAX_BLOCCO:
            raise FileNonValido('intestazione di frame non valida: ' + DANNEGGIATO)
        modo, ultimo = tipo & 1, bool(tipo >> 1)
        conti = None
        if modo == 0:
            conti = tuple(self._varint() for _ in range(self.ncontatori))
            if conti[-1] >= 8 * n:            # il modo 0 si sceglie solo se i bit sono meno
                raise FileNonValido('intestazione di frame non valida: ' + DANNEGGIATO)
            corpo = self._leggi((conti[-1] + 7) // 8)
        else:
            corpo = self._leggi(n)
        crc_dati = int.from_bytes(self._leggi(4), 'big') if ultimo else None
        atteso = self.crc
        if int.from_bytes(self._leggi(4), 'big') != atteso and self.controlla_crc:
            raise FileNonValido('CRC del file errato: ' + DANNEGGIATO)
        carico = spacchetta_bit(corpo, conti[-1]) if modo == 0 else corpo
        return Frame(modo, n, conti, carico, ultimo, crc_dati)
