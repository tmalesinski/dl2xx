#!/usr/bin/python3

import datetime, os, hid

_TIMEOUT = 1000

class DlError(Exception):
    pass


class _Field(object):
    def __init__(self, name):
        self.name = name

    def parse(self, data, i):
        sl = self.serialized_length()
        if i + sl > len(data):
            raise DlError("record too short")
        return self._parse_internal(data, i), i + sl


class _Byte(_Field):
    def initial_value(self):
        return 0

    def serialized_length(self):
        return 1

    def _parse_internal(self, data, i):
        return data[i]

    def serialize(self, v):
        return bytes([v])


class _Word(_Field):
    def initial_value(self):
        return 0

    def serialized_length(self):
        return 2

    def _parse_internal(self, data, i):
        return data[i] + (data[i + 1] << 8)

    def serialize(self, v):
        return bytes([v & 0xff, v >> 8])


class _Long(_Field):
    def initial_value(self):
        return 0

    def serialized_length(self):
        return 4

    def _parse_internal(self, data, i):
        v = 0
        for j in range(4):
            v = v + (data[i + j] << (j * 8))
        return v

    def serialize(self, v):
        return bytes([(v >> (i * 8)) & 0xff for i in range(4)])


class _String(_Field):
    def __init__(self, name, length):
        super().__init__(name)
        self.length = length

    def initial_value(self):
        return bytes()

    def serialized_length(self):
        return self.length

    def _parse_internal(self, data, i):
        return data[i:i + self.length]

    def serialize(self, v):
        return v + bytes(max(0, self.length - len(v)))


class _Subrecord(_Field):
    def __init__(self, name, cls):
        super().__init__(name)
        self.cls = cls

    def initial_value(self):
        return self.cls()

    def serialized_length(self):
        return self.cls.serialized_length()

    def _parse_internal(self, data, i):
        return self.cls._parse_internal(data, i)[1]

    def serialize(self, v):
        return v.serialize()


class _BinaryRecord(object):
    def __init__(self, **kwargs):
        for f in self._fields:
            v = kwargs[f.name] if f.name in kwargs else f.initial_value()
            setattr(self, f.name, v)

    @classmethod
    def _parse_internal(cls, data, i):
        record = cls()
        for f in cls._fields:
            v, i1 = f.parse(data, i)
            setattr(record, f.name, v)
            i = i1
        return i1, record
        
    @classmethod
    def parse(cls, data):
        i, record = cls._parse_internal(data, 0)
        if i < len(data):
            raise DlError("record too long")
        return record
        
    def serialize(self): 
        res = bytes()
        for f in self._fields:
            res += f.serialize(getattr(self, f.name))
        return res

    @classmethod
    def serialized_length(cls):
        res = 0
        for f in cls._fields:
            res += f.serialized_length()
        return res

    def __repr__(self):
        res = "<%s " % self.__class__.__name__
        res += ", ".join(
            ["%s=%s" % (f.name, repr(getattr(self, f.name)))
             for f in self._fields])
        res += ">"
        return res


def open_hid_dev():
    h = hid.device()
    h.open(0x2047, 0x0301)
    return h

class _DlHidConnection:
    def __init__(self, dev):
        self._dev = dev

    def send_command(self, command, payload=bytes()):
        # TODO: check if payload not too long?
        buf = bytes([0x3f, len(payload) + 1, command]) + payload
        self._dev.write(buf)

    def read_response(self):
        return bytes(self._dev.read(64, _TIMEOUT))

    def run_command(self, command, payload=bytes()):
        self.send_command(command, payload)
        response = self.read_response()
        # TODO: what is returned on error, timeout?
        if len(response) < 2:
            raise DlError("response too short (%d bytes)", len(response))
        if response[0] != 0x3f:
            raise DlError("invalid first byte (0x%02x)", response[0])
        if response[1] + 2 > len(response):
            raise DlError("response length too large (%d)", response[1])
        return response[2:response[1] + 2]


def _get_string(bytes):
    return bytes.decode("ascii")


class DateTimeRecord(_BinaryRecord):
    _fields = [
        _Word("year"),
        _Byte("month"),
        _Byte("day"),
        _Byte("hour"),
        _Byte("minute"),
        _Byte("second")]

        
# 59 bytes when read
class Settings33Record(_BinaryRecord):
    _fields = [
        _Byte("unk0"),
        _Byte("unk1"),
        _Byte("unk2"),
        _Byte("unk3"),
        _Word("data_count"),
        _Byte("unk6"),
        _Byte("unk7"),
        _Long("sample_rate"),
        _Byte("led_flashing_interval_secs"),
        _Byte("start_condition"),
        _Byte("led_alarm"),
        _Word("temp_low_alarm_100"),
        _Word("temp_high_alarm_100"),
        _Word("hum_low_alarm_100"),
        _Word("hum_high_alarm_100"),
        _Byte("unk10"),
        _Byte("unk11"),
        _Byte("unk12"),
        _Byte("unk13"),
        _Byte("unk14"),
        _Byte("unk15"),
        _Byte("unk16"),
        _Subrecord("unk_time1", DateTimeRecord),
        _Byte("unk17"),
        _Byte("unk18"),
        _Byte("enable_display"),
        _Byte("stop_style"),
        _Subrecord("unk_time2", DateTimeRecord),
        _Subrecord("unk_time3", DateTimeRecord),
        _Byte("start_delay_mins"),
        _Word("logger_id"),
        _Byte("unk19")]

class Status48(_BinaryRecord):
    _fields = [
        _String("device_type", 16),
        _Subrecord("time", DateTimeRecord),
        _Byte("unknown1"),
        _String("firmware_version", 16),
        _String("serial_number", 16),
        _Byte("unknown2"),
        _String("unset", 2)]


class Settings4(_BinaryRecord):
    _fields = [
        _Byte("unk1"),
        _Byte("unk2"),
        _Word("data_count"),
        _Long("sample_rate"),
        _Byte("led_flashing_interval_secs"),
        _Byte("start_condition"),
        _Byte("led_alarm"),
        _Word("temp_low_alarm_100"),
        _Word("temp_high_alarm_100"),
        _Word("hum_low_alarm_100"),
        _Word("hum_high_alarm_100"),
        _Byte("temp_unit"),
        _Subrecord("time", DateTimeRecord),
        _Byte("date_format")]


class Measurement(_BinaryRecord):
    _fields = [
        _Word("temperature100"),
        _Word("humidity100")]


class OwnerStartTime(_BinaryRecord):
    _fields = [
        _String("owner", 32),
        _Subrecord("start_time", DateTimeRecord)]


def _check_response(response, length=None, prefix=None):
    if length is not None and len(response) != length:
        raise DlError("expected %d bytes, got %d" % (length, len(response)))
    if prefix is not None and not response.startswith(bytes(prefix)):
        raise DlError("invalid response start: %s" % response[0:len(prefix)])


class Dl210Th(object):
    def __init__(self, c):
        self._connection = c

    def status48(self):
        response = self._connection.run_command(48)
        if len(response) != 60:
            raise DlError("expected 60 bytes, got %d" % len(response))
        if response[0] != 48:
            raise DlError("expected first reponse byte to be 0x30, got 0x%02x",
                          response[0])
        return Status48.parse(response[1:])

    def cmd3(self, settings4):
        response = self._connection.run_command(3, settings4.serialize())
        if len(response) != 3:
            raise DlError("expected 3 bytes, got %d" % len(response))
        if response[0:3] != bytes([0, 0, 3]):
            raise DlError("invalid three first bytes: %s" % response[0:3])

    def cmd4(self):
        response = self._connection.run_command(4)
        if len(response) != 31:
            raise DlError("expected 31 bytes, got %d" % len(response))
        if response[0:3] != bytes([0, 0, 4]):
            raise DlError("invalid three first bytes: %s" % response[0:3])
        return Settings4.parse(response[3:])

    def read_sensors(self):
        response = self._connection.run_command(6)
        _check_response(response, length=7, prefix=[0, 0, 6])
        return Measurement.parse(response[3:])

    def get_serial_id(self):
        response = self._connection.run_command(12)
        _check_response(response, length=16)
        return response

    def get_settings33(self):
        response = self._connection.run_command(33)
        _check_response(response, length=60, prefix=[33])
        return Settings33Record.parse(response[1:])
        
    def get_settings34(self):
        response = self._connection.run_command(34)
        if len(response) != 56:
            raise DlError("expected 56 bytes, got %d" % len(response))
        if response[0] != 34:
            raise DlError("invalid first bytes: %d" % response[0])
        return response[1:]
        
    def get_owner_start_time(self):
        response = self._connection.run_command(35)
        _check_response(response, length=40, prefix=[35])
        return OwnerStartTime.parse(response[1:])

    def get_location(self):
        response = self._connection.run_command(36)
        _check_response(response, length=33, prefix=[36])
        return response[1:]

    def get_string37(self):
        response = self._connection.run_command(37)
        _check_response(response, length=41, prefix=[37])
        return response[1:]

    def get_string38(self):
        response = self._connection.run_command(38)
        _check_response(response, length=51, prefix=[38])
        return response[1:]

    def _decode_measurements(self, encoded):
        data = []
        for n in range(15):
            i = 4 * n
            data.append(Measurement.parse(encoded[i:i + 4]))
        return data

    def get_data_block(self, n):
        # TODO: check that n fits in 16 bits?
        req = bytes([n >> 8, n & 0xff])
        response = self._connection.run_command(2, payload=req)
        _check_response(response, length=62, prefix=req)
        # TODO: do incomplete blocks work?
        return self._decode_measurements(response[2:])

    def dump_data(self):
        # TODO: flush any incoming data first? in all commands?
        # maybe in send_command?
        self._connection.send_command(1)
        n = 1
        data = []
        while True:
            r = self._connection.read_response()
            if not r: break
            l = r[1]
            if l < 2: raise DlError("too short block")
            if l == 2: continue
            if l == 3: print(list(r))
            # TODO: check how incomplete blocks are sent
            if l != 62:
                print("Expected 62 bytes: %d" % l)
            block_n = (r[2] << 8) + r[3]
            if n != block_n:
                print("Unexpected block num: %d vs %d" % (block_n, n))
            n = block_n + 1
            data.extend(self._decode_measurements(r[4:]))
            print(r[1], (r[2] << 8) + r[3])
        return data

def set_time(dl):
    s = dl.cmd4()
    t = datetime.datetime.now()
    s.time = DateTimeRecord(year=t.year, month=t.month, day=t.day,
                            hour=t.hour, minute=t.minute, second=t.second)
    dl.cmd3(s)

def main():
    dev = open_hid_dev()
    try:
        c = _DlHidConnection(dev)
        dl = Dl210Th(c)
        print(dl.status48())
    finally:
        dev.close()

if __name__ == "__main__":
    main()
