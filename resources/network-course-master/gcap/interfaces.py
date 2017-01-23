#!/usr/bin/python


import gcap


def main():
    for iface in gcap.GCap.get_interfaces():
        print('%(name)-40s %(description)s' % iface)


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
