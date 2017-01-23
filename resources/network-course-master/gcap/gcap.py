import ctypes
import ctypes.util
import datetime
import os
import platform


try:
    from . import winpcapy
except (SystemError, ValueError):
    import winpcapy


class GCap():

    @staticmethod
    def _get_address(iface):
        address = None

        if platform.system() == 'Linux':
            try:
                with open(
                    os.path.join(
                        '/sys/class/net',
                        iface,
                        'address',
                    )
                ) as f:
                    address = f.read().strip()
            except Exception:
                pass

        return address if address else None

    @staticmethod
    def get_interfaces():
        alldevs = ctypes.POINTER(winpcapy.pcap_if_t)()
        errbuf = ctypes.create_string_buffer(winpcapy.PCAP_ERRBUF_SIZE)

        if (winpcapy.pcap_findalldevs(ctypes.byref(alldevs), errbuf) == -1):
            raise RuntimeError('pcap_findalldevs failed: %s' % errbuf.value)

        interfaces = []
        try:
            d = alldevs.contents
            while d:
                interfaces.append({
                    'name': d.name.decode('utf-8'),
                    'description': (
                        d.description.decode('utf-8')
                        if d.description else 'N/A'
                    ),
                    'mac': GCap._get_address(d.name.decode('utf-8')),
                })
                if d.next:
                    d = d.next.contents
                else:
                    d = None
        finally:
            winpcapy.pcap_freealldevs(alldevs)

        return interfaces

    def __init__(self, iface, timeout=10000):
        self._iface = iface
        self._timeout = timeout

    def __enter__(self):
        errbuf = ctypes.create_string_buffer(winpcapy.PCAP_ERRBUF_SIZE)
        self._fp = winpcapy.pcap_open_live(
            self._iface.encode('utf-8'),
            65536,
            1,
            self._timeout,
            errbuf,
        )
        if self._fp is None:
            raise RuntimeError('pcap_open_live failed: %s' % errbuf.value)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._fp is not None:
            winpcapy.pcap_close(self._fp)
            self._fp = None

    def get_address(self):
        self._get_address(self._iface)

    def next_packet(self):
        header = ctypes.POINTER(winpcapy.pcap_pkthdr)()
        pkt_data = ctypes.POINTER(ctypes.c_ubyte)()

        res = winpcapy.pcap_next_ex(
            self._fp,
            ctypes.byref(header),
            ctypes.byref(pkt_data),
        )
        if(res == -1):
            raise RuntimeError(
                'pcap_next_ex failed: ' % winpcapy.pcap_geterr(self._fp)
            )

        if res == 0:
            return None

        return {
            'header': {
                'timestamp': (
                    datetime.datetime.utcfromtimestamp(
                        header.contents.ts.tv_sec
                    ) +
                    datetime.timedelta(
                        microseconds=header.contents.ts.tv_usec,
                    )
                ),
                'caplen': header.contents.caplen,
                'len': header.contents.len,
            },
            'data': bytearray(pkt_data[
                :min(header.contents.caplen, header.contents.len)
            ]),
        }

    def send_packet(self, data):
        b = bytearray(data)
        packet = (ctypes.c_ubyte * len(b))(*b)
        if (winpcapy.pcap_sendpacket(self._fp, packet, len(b)) != 0):
            raise RuntimeError(
                'pcap_sendpacket failed: ' % winpcapy.pcap_geterr(self._fp)
            )


__all__ = ['GCap']


# vim: expandtab tabstop=4 shiftwidth=4
