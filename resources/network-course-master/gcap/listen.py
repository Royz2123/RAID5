#!/usr/bin/python


import sys


import gcap


def binary_to_int(h):
    ret = 0
    for x in bytearray(h):
        ret = (ret << 8) + x
    return ret


def binary_to_hexstring(h, sep=''):
    return sep.join('%02x' % x for x in bytearray(h))


def main():
    if len(sys.argv) > 1:
        iface = sys.argv[1]
    else:
        iface = gcap.GCap.get_interfaces()[0]['name']

    with gcap.GCap(iface=iface) as cap:
        while True:
            packet = cap.next_packet()
            if packet:
                if binary_to_int(packet['data'][12:14]) == 0x1000:
                    print('dst:  %s' % binary_to_hexstring(
                        packet['data'][0:6],
                        sep=':',
                    ))
                    print('src:  %s' % binary_to_hexstring(
                        packet['data'][6:12],
                        sep=':',
                    ))
                    print('type: %04x' % binary_to_int(
                        packet['data'][12:14])
                    )
                    print('data: %s' % packet['data'][14:])


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
