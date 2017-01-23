#!/usr/bin/python


import re
import sys


import gcap


def hexstring_to_binary(h, sep=''):
    return bytearray(int(x, 16) for x in re.findall('..', h.replace(sep, '')))


def int_to_binary(i, n):
    l = []
    for x in range(n):
        l.append(i & 0xff)
        i >>= 8
    return bytearray(l[::-1])


def main():
    if len(sys.argv) > 1:
        iface = sys.argv[1]
    else:
        iface = gcap.GCap.get_interfaces()[0]['name']

    with gcap.GCap(iface=iface) as cap:
        dst = '52:54:00:12:34:50'
        src = '52:54:00:12:34:56'
        type = 0x1000
        cap.send_packet(
            hexstring_to_binary(dst, sep=':') +
            hexstring_to_binary(src, sep=':') +
            int_to_binary(type, 2) +
            'testing 1 2 3'.encode('ascii')
        )


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
