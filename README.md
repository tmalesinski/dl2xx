This is an unofficial client for the Voltcraft DL-210TH temperature
and humidity logger. You can see this logger at
http://datalogger.voltcraft.com/ConfigBuilder/index.jsp.

> [!WARNING]
> Use at you own risk. The author of this client takes no responsibility
> for any damages resulting from its use.

At the moment only the DL-210TH model is supported. However, other
DL-2 series loggers likely use a similar protocol. Please report an
issue if you'd like to have other loggers supported.

This client has been tested under Debian GNU/Linux 11 with a DL-210TH
running firmware version V1.0.1.170906.

# Dependencies

* Python 3 (tested with Python 3.9.2)
* [cython-hidapi](https://github.com/trezor/cython-hidapi)
  (tested with version 0.9.0.post3)
* [libusb hidapi](https://github.com/libusb/hidapi) (tested with version 0.14.0)

On a Debian GNU/Linux system you can install all required dependencies
by installing the
[`python3-hid`](https://packages.debian.org/bookworm/python3-hid)
package.

# Configuration

Accessing the logger device on Linux requires permissions to the corresponding
USB device. udev can be configured to set the permissions to allow non-root
users to access the logger.

On a Debian GNU/Linux system you can create a file
`/etc/udev/rules.d/99-voltcraft` with the following entry:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="2047", ATTRS{idProduct}=="0301", MODE="0660", GROUP="plugdev"
```
(yes, the device uses the Texas Instruments vendor id. Apparently it
uses a USB library provided by Texas Instruments without changing the
vendor or product id)

# Usage

## Checking the device status

```
$ ./dl210th.py status
Device type:                DL-210TH        
Current time:               2024-03-03 20:53:49
Firmware version:           V1.0.1.170906   
Serial number:              DL_210T123456789
Unknown (battery level?):   100
Unknown (recording state?): 6
```

## Checking current temperature and relative humidity

```
$ ./dl210th.py measure
Temperature: 24.93
Humidity:    22.35%
```

## Checking the logger configuration

```
$ ./dl210th.py config
Sample rate:            120s
Led flashing interval:  5s
Start condition:        Start/Stop time
[...]
```

## Starting recording

```
$ ./dl210th.py record --start-condition circular --sample-rate 60
```

> [!CAUTION]
> The `record` command deletes all previously stored data.

The `record` command updates the configuration based on command line
flags and starts a new recording. It also sets the logger's clock to
the current time. Configuration settings not set with the flags keep
their previous values (see the `config` command above).

## Dumping data

```
$ ./dl210th.py dump
2024-03-03 21:04:44,24.8,22.5
2024-03-03 21:05:44,24.8,22.5
2024-03-03 21:06:44,24.8,22.4
```

The `dump` command dumps stored measurements in a CSV format to the standard
output.
