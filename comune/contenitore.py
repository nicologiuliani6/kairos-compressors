"""Pezzi comuni dei contenitori: varint, bit impacchettati, CRC.

Ogni file compresso termina con due CRC32 di 4 byte: quello dei dati
originali e quello di tutti i byte del file che lo precedono. Il secondo si
controlla prima di avviare la VM: un file alterato viene rifiutato e non
arriva mai all'`uncall`. Il primo si controlla sul risultato.
"""
import zlib


class FileNonValido(Exception):
    pass


def varint(v):
    o = bytearray()
    while True:
        c = v & 0x7F
        v >>= 7
        o.append(c | (0x80 if v else 0))
        if not v:
            return bytes(o)


def leggi_varint(buf, p):
    v = s = 0
    while True:
        if p >= len(buf):
            raise FileNonValido('intestazione troncata')
        c = buf[p]
        p += 1
        v |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return v, p


def impacchetta_bit(bits):
    b = list(bits) + [0] * (-len(bits) % 8)
    return bytes(int(''.join(map(str, b[k:k + 8])), 2) for k in range(0, len(b), 8))


def spacchetta_bit(buf, nbit):
    bits = [int(c) for byte in buf for c in f'{byte:08b}']
    if len(bits) < nbit:
        raise FileNonValido('dati compressi troncati')
    return bits[:nbit]


def chiudi(corpo, originale):
    """corpo + CRC dei dati originali + CRC del file fin li'."""
    c = bytes(corpo) + zlib.crc32(originale).to_bytes(4, 'big')
    return c + zlib.crc32(c).to_bytes(4, 'big')


def apri(buf, magia):
    """Controlla firma e CRC del file; restituisce (corpo, crc dei dati originali)."""
    if len(buf) < len(magia) + 8 or buf[:len(magia)] != magia:
        raise FileNonValido(f'non e\' un file {magia.decode()}')
    if zlib.crc32(buf[:-4]) != int.from_bytes(buf[-4:], 'big'):
        raise FileNonValido('CRC del file errato: il file e\' danneggiato')
    return buf[len(magia):-8], int.from_bytes(buf[-8:-4], 'big')


def verifica(dati, crc):
    if zlib.crc32(dati) != crc:
        raise FileNonValido('CRC dei dati ricostruiti errato')
