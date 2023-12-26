#!/usr/bin/python

import datetime, os

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


class _DlConnection(object):
    def __init__(self, dev_path):
        self._fd = os.open(dev_path, os.O_RDWR)
        # TODO: what exceptions can be raised?
        # TODO: context manager
        # TODO: check if this is the right device (minor/major)?
        # TODO: check if vendor/product are correct?

    def run_command(self, command, payload=bytes()):
        # TODO: check if payload not too long?
        os.write(self._fd, bytes([0x3f, len(payload) + 1, command]) + payload)
        # TODO: check how many bytes written?
        result = os.read(self._fd, 64)
        if len(result) < 2:
            raise DlError("result too short (%d bytes)", len(result))
        if result[0] != 0x3f:
            raise DlError("invalid first byte (0x%02x)", result[0])
        if result[1] + 2 > len(result):
            raise DlError("response length too large (%d)", result[1])
        return result[2:result[1] + 2]

    def close(self):
        os.close(self._fd)
        self._fd = None


def _endpoint_is_out(e):
    return (usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)


def _endpoint_is_in(e):
    return (usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)


class _DlUsbConnection:
    def __init__(self, dev):
        self._dev = dev
        # TODO: set configuration
        cfg = dev.get_active_configuration()
        intf = usb.util.find_descriptor(cfg, bInterfaceClass=3)
        # TODO: claim interface? or have methods to claim when needed?
        if intf is None:
            raise DlError("Could not find HID interface")

        self._out = usb.util.find_descriptor(
            intf, custom_match=_endpoint_is_out)
        self._in = usb.util.find_descriptor(
            intf, custom_match=_endpoint_is_in)

    def run_command(self, command, payload=bytes()):
        # TODO: check if payload not too long?
        buf = bytes([0x3f, len(payload) + 1, command]) + payload
        written = self._dev.write(self._out, buf, _TIMEOUT)
        print(written)
        response = self._dev.read(self._in, 64, _TIMEOUT)
        if len(response) < 2:
            raise DlError("response too short (%d bytes)", len(response))
        if response[0] != 0x3f:
            raise DlError("invalid first byte (0x%02x)", response[0])
        if response[1] + 2 > len(response):
            raise DlError("response length too large (%d)", response[1])
        return response[2:response[1] + 2]

        
def open_hid_dev():
    h = hid.device()
    h.open(0x2047, 0x0301)
    return h

class _DlHidConnection:
    def __init__(self, dev):
        self._dev = dev

    def run_command(self, command, payload=bytes()):
        # TODO: check if payload not too long?
        buf = bytes([0x3f, len(payload) + 1, command]) + payload
        self._dev.write(buf)
        response = self._dev.read(64, _TIMEOUT)
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


class DlDateTime(object):
    def __init__(self, serialized):
        self.year = serialized[0] + serialized[1] * 256
        self.month = serialized[2]
        self.day = serialized[3]
        self.hour = serialized[4]
        self.minute = serialized[5]
        self.second = serialized[6]
        
    def __repr__(self):
        return ("<DlDateTime %04d-%02d-%02d %02d:%02d:%02d>" %
                (self.year, self.month, self.day,
                 self.hour, self.minute, self.second))


class Settings33(object):
    def __init__(self, response):
        self.data = response
        self.some_time1 = DlDateTime(response[30:37])
        self.some_time2 = DlDateTime(response[41:48])
        self.some_time3 = DlDateTime(response[48:56])

    def __repr__(self):
        return ("<Settings4 %s, %s, %s, %s>" %
                (self.some_time1, self.some_time2, self.some_time3,
                 list(self.data)))


class DateTimeRecord(_BinaryRecord):
    _fields = [
        _Word("year"),
        _Byte("month"),
        _Byte("day"),
        _Byte("hour"),
        _Byte("minute"),
        _Byte("second")]

        
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
        _Byte("unk5"),
        _Byte("unk6"),
        _Word("unk7"),
        _Byte("unk8"),
        _Byte("unk9"),
        _Byte("unk10"),
        _Byte("unk11"),
        _Byte("unk12"),
        _Byte("unk13"),
        _Byte("unk14"),
        _Byte("unk15"),
        _Byte("unk16"),
        _Byte("unk17"),
        _Byte("unk18"),
        _Byte("unk19"),
        _Subrecord("time", DateTimeRecord),
        _Byte("unk27")]


class Dl210Th(object):
    def __init__(self, dev_path):
        self._connection = _DlConnection(dev_path)

    def close(self):
        self._connection.close()
        self._connection = None

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

    def get_settings33(self):
        response = self._connection.run_command(33)
        if len(response) != 60:
            raise DlError("expected 60 bytes, got %d" % len(response))
        if response[0] != 33:
            raise DlError("invalid first bytes: %d" % response[0])
        return Settings33(response[1:])
        
    def get_settings34(self):
        response = self._connection.run_command(34)
        if len(response) != 56:
            raise DlError("expected 56 bytes, got %d" % len(response))
        if response[0] != 34:
            raise DlError("invalid first bytes: %d" % response[0])
        return response[1:]
        
        
def set_time(dl):
    s = dl.cmd4()
    t = datetime.datetime.now()
    s.time = DateTimeRecord(year=t.year, month=t.month, day=t.day,
                            hour=t.hour, minute=t.minute, second=t.second)
    dl.cmd3(s)

# unbind?
# echo 1-7.4:1.1 >/sys/bus/usb/drivers/usbhid/unbind 

def main():
    dev = usb.core.find(idVendor=0x2047, idProduct=0x0301)
    interface = dev.configurations()[0].interfaces()[1]
    # TODO: fails if a device is already configured which it is
    # probably because it is a mass storage device
    # dev.set_configuration()
    # TODO: find the endpoint?
    print(dev.write(0x02, msg, 1000))
    
