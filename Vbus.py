import ssl
import socket


MODE_COMMAND = 0
MODE_DATA = 1

DEBUG_HEXDUMP = 0b0001
DEBUG_COMMAND = 0b0010
DEBUG_PROTOCOL = 0b0100

_FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])
_PAYLOADMAP = {
    'temp1': (0, 1), 'temp2': (2, 3),
    'temp3': (4, 5), 'temp4': (6, 7),
    'pump1': (8, 8), 'pump2': (9, 9),
    'relais': (10, 10), 'errors': (11, 11),
    'time': (12, 13), 'scheme': (14, 14),
    'flags': (15, 15), 'r1time': (16, 17),
    'r2time': (18, 19), 'version': (26, 27)
}


def _hexdump(src, length=16):
    result = []
    for i in xrange(0, len(src), length):
        s = src[i:i+length]
        hexa = ' '.join(["%02X" % ord(x) for x in s])
        printable = s.translate(_FILTER)
        result.append("%04X   %-*s   %s\n" % (i, length*3, hexa, printable))
    return "Len %iB\n%s" % (len(src), ''.join(result))


class VBUSException(Exception):
    def __init__(self, *args):
        super.__init__(*args)


class VBUSResponse(object):
    def __init__(self, line):
        assert len(line) > 2
        self.positive = line[0] == "+"
        spl = line[1:].split(":", 1)
        self.type = spl[0]
        self.message = None if len(spl) == 1 else spl[1][:1]


class VBUSPayload(object):
    def __init__(self, raw):
        pass


class VBUSConnection(object):
    def __init__(self, host, port=7053, password="", debugmode=0b0000):
        assert isinstance(port, int)
        assert isinstance(host, str)
        assert isinstance(password, str)
        assert isinstance(debugmode, int)
        self.host = host
        self.port = port
        self.password = password or False
        self.debugmode = debugmode

        self._mode = MODE_COMMAND
        self._sock = None
        self._buffer = []

    def connect(self, sslsock=False):
        assert not self._sock
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sslsock:  # Unlikely that we'll ever connect to the VBUS using an ssl socket but "why not?"
            self._sock = ssl.wrap_socket(self._sock)
        self._sock.connect((self.host, self.port))
        assert VBUSResponse(self._lrecv()).type == "HELLO"
        if self.password:
            self.authenticate()

    def authenticate(self):
        assert self.password
        assert self._mode == MODE_COMMAND
        self._lsend("PASS %s" % self.password)
        resp = VBUSResponse(self._lrecv())
        if not resp.positive:
            raise VBUSException("Could not authenticate: %s" % resp.message)

    def data(self):
        assert self._sock
        if self._mode is not MODE_DATA:
            self._lsend("DATA")

            resp = VBUSResponse(self._lrecv())
            if not resp.positive:
                raise VBUSException("Could create a data stream: %s" % resp.message)
            self._mode = MODE_DATA

        # Wait till we get the correct protocol
        for d in self._brecv().split(chr(0xAA)):
            # Check the protocol
            if self._getbytes(d, 4, 5) is not 0x10:
                continue

            # Are we getting a payload?
            if self._getbytes(d, 5, 7) is not 0x100:
                continue

            # Is the checksum valid?
            if self._checksum(d[0:8]) is not self._getbytes(d, 8, 9):
                if self.debugmode & DEBUG_PROTOCOL:
                    print "Invalid checksum: got %02X expected %02X" % \
                          (self._checksum(d[0:8]), self._getbytes(d, 8, 9))
                continue

            frames = self._getbytes(d, 7, 8)
            payload = d[9:9 + (6*frames)]
            # Check payload length
            if len(payload) is not 6*frames:
                if self.debugmode & DEBUG_PROTOCOL:
                    print "Unexpected payload length: %i != %i" % \
                          (len(payload), 6*frames)
                continue





    def getmode(self):
        return self._mode

    @staticmethod
    def _checksum(data):
        c = 0x7F
        for b in data:
            c = ((c - ord(b)) % 0x100) & 0x7F
        return c

    @staticmethod
    def _getbytes(data, begin, end):
        return sum([ord(b) << (i*8) for i, b in enumerate(data[begin:end])])

    def _lrecv(self):
        c, s = '', ''
        while c != '\n':
            c = self._sock.recv(1)
            if c == '':
                break
            s += c
        s = s.strip('\r\n')
        if self.debugmode & DEBUG_COMMAND:
            print "< " + s
        return s

    def _brecv(self, n=1024):
        d = self._sock.recv(n)
        if self.debugmode & DEBUG_HEXDUMP:
            print _hexdump(d)
        return d

    def _lsend(self, s):
        if self.debugmode & DEBUG_COMMAND:
            print "> " + s
        self._sock.send(s + "\r\n")

    def _bsend(self, s):
        if self.debugmode & DEBUG_HEXDUMP:
            print _hexdump(s)
        self._sock.send(s)