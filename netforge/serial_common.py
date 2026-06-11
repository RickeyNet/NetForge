"""Serial-port plumbing shared by the console dialogs.

Both the IOS config-push dialog and the FTD setup dialog talk to a
console cable the same way; keep the port enumeration and the open
parameters in one place so fixes land in both tools.
"""

BAUD_RATES = ("9600", "19200", "38400", "57600", "115200")


def refresh_com_ports(combobox):
    """Fill a ttk.Combobox with 'COMx - description' entries and select
    the first one if nothing is selected yet."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return
    ports = [f"{p.device} - {p.description}" for p in list_ports.comports()]
    combobox["values"] = ports
    if ports and not combobox.get():
        combobox.set(ports[0])


def open_console_port(port, baud):
    """Open a console serial port with the project-standard settings.

    timeout=0.2 keeps reads short so worker loops stay responsive;
    write_timeout bounds a wedged adapter instead of hanging forever.
    """
    import serial
    return serial.Serial(port=port, baudrate=baud,
                         bytesize=8, parity="N", stopbits=1,
                         timeout=0.2, write_timeout=2.0)
