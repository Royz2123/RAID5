# -*- coding: utf-8 -*-
"""Unit tests for packets."""

import unittest


from . import packets


class EthernetPacketTest(unittest.TestCase):

    TEST_MAC_DST_STRING = '12:34:56:12:12:13'
    TEST_MAC_DST = packets.EthernetPacket.mac_from_string(
        TEST_MAC_DST_STRING,
    )
    TEST_MAC_SRC = packets.EthernetPacket.mac_from_string(
        '12:34:56:12:12:12',
    )
    TEST_ETH_TYPE = 0x1234
    TEST_ETH_DATA = bytearray((0x01, 0x02, 0x03, 0x04))

    def test_encode(self):
        self.assertEqual(
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ).encode(),
            bytearray((
                    0x12, 0x34, 0x56, 0x12, 0x12, 0x13,  # dst
                    0x12, 0x34, 0x56, 0x12, 0x12, 0x12,  # src
                    0x12, 0x34,  # type
                    0x01, 0x02, 0x03, 0x04  # data
            )),
        )

    def test_decode(self):
        base = packets.EthernetPacket(
            dst=self.TEST_MAC_DST,
            src=self.TEST_MAC_SRC,
            ethertype=self.TEST_ETH_TYPE,
            data=self.TEST_ETH_DATA,
        )
        self.assertEqual(
            base,
            packets.EthernetPacket.decode(base.encode()),
        )

    def test_decode_fail(self):
        # too short
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket.decode(bytearray((0x01, 0x02)))
        # too long
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket.decode(bytearray(3000))

    def test_encode_fail(self):
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket(
                dst=bytearray((0x02, 0x02)),
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ).encode()
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=bytearray((0x02, 0x02)),
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ).encode()
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=-1,
                data=self.TEST_ETH_DATA,
            ).encode()
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=0x12345,
                data=self.TEST_ETH_DATA,
            ).encode()
        with self.assertRaises(RuntimeError):
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=bytearray(3000),
            ).encode()

    def test_mac_string(self):
        self.assertEqual(
            self.TEST_MAC_DST,
            packets.EthernetPacket.mac_from_string(
                self.TEST_MAC_DST_STRING,
            ),
        )
        self.assertEqual(
            self.TEST_MAC_DST_STRING,
            packets.EthernetPacket.mac_to_string(
                self.TEST_MAC_DST,
            ),
        )

    def test_mac_multicast(self):
        self.assertFalse(
            packets.EthernetPacket.mac_is_multicast(
                packets.EthernetPacket.mac_from_string(
                    '22:22:22:22:22:22',
                )
            )
        )
        self.assertTrue(
            packets.EthernetPacket.mac_is_multicast(
                packets.EthernetPacket.mac_from_string(
                    '21:22:22:22:22:22',
                )
            )
        )
        self.assertTrue(
            packets.EthernetPacket.mac_is_multicast(
                packets.EthernetPacket.MAC_BROADCAST,
            )
        )

    def test_eq(self):
        self.assertNotEqual(
            packets.EthernetPacket(),
            None,
        )
        self.assertNotEqual(
            packets.EthernetPacket(),
            [],
        )
        self.assertEqual(
            packets.EthernetPacket(),
            packets.EthernetPacket(),
        )
        self.assertEqual(
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ),
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ),
        )
        self.assertNotEqual(
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ),
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE+1,
                data=self.TEST_ETH_DATA,
            ),
        )
        self.assertNotEqual(
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ),
            packets.EthernetPacket(
                dst=self.TEST_MAC_SRC,
                src=self.TEST_MAC_DST,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ),
        )
        self.assertNotEqual(
            packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            ),
            packets.EthernetPacket(
                dst=self.TEST_MAC_SRC,
                src=self.TEST_MAC_DST,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA + bytearray((0x01,)),
            ),
        )

    def test_repr(self):
        # human eye catcher, no failure
        print(
            '%s' % packets.EthernetPacket(
                dst=self.TEST_MAC_DST,
                src=self.TEST_MAC_SRC,
                ethertype=self.TEST_ETH_TYPE,
                data=self.TEST_ETH_DATA,
            )
        )


class RegistrationPacketTest(unittest.TestCase):

    TEST_NAME = 'name1'

    def test_encode(self):
        packet = packets.RegistrationPacket(
            command=(
                packets.RegistrationPacket.COMMAND_ALLOCATE
            ),
            name=self.TEST_NAME,
        )
        self.assertEqual(
            packet.encode(),
            (
                bytearray((0,)) +  # command
                'name1     '.encode('ascii')  # name
            ),
        )

    def test_decode(self):
        base = packets.RegistrationPacket(
            command=(
                packets.RegistrationPacket.COMMAND_ALLOCATE
            ),
            name=self.TEST_NAME,
        )
        self.assertEqual(
            base,
            packets.RegistrationPacket.decode(base.encode()),
        )

    def test_encode_fail(self):
        with self.assertRaises(RuntimeError):
            packets.RegistrationPacket(
                command=-1,
                name=self.TEST_NAME,
            ).encode()
        with self.assertRaises(RuntimeError):
            packets.RegistrationPacket(
                command=256,
                name=self.TEST_NAME,
            ).encode()

    def test_eq(self):
        self.assertNotEqual(
            packets.RegistrationPacket(),
            None,
        )
        self.assertNotEqual(
            packets.RegistrationPacket(),
            [],
        )
        self.assertEqual(
            packets.RegistrationPacket(),
            packets.RegistrationPacket(),
        )
        self.assertEqual(
            packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_ALLOCATE
                ),
                name=self.TEST_NAME,
            ),
            packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_ALLOCATE
                ),
                name=self.TEST_NAME,
            ),
        )
        self.assertNotEqual(
            packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_ALLOCATE
                ),
                name=self.TEST_NAME,
            ),
            packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_RELEASE
                ),
                name=self.TEST_NAME,
            ),
        )
        self.assertNotEqual(
            packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_ALLOCATE
                ),
                name=self.TEST_NAME,
            ),
            packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_ALLOCATE
                ),
                name=self.TEST_NAME+'a',
            ),
        )

    def test_repr(self):
        # human eye catcher, no failure
        print(
            '%s' % packets.RegistrationPacket(
                command=(
                    packets.RegistrationPacket.COMMAND_ALLOCATE
                ),
                name=self.TEST_NAME,
            )
        )


class ChatPacketTest(unittest.TestCase):

    TEST_NAME = 'name1'
    TEST_MESSAGE = 'hello'

    def test_encode(self):

        packet = packets.ChatPacket(
            name=self.TEST_NAME,
            message=self.TEST_MESSAGE,
        )
        self.assertEqual(
            packet.encode(),
            (
                'name1     '.encode('ascii') +  # name
                self.TEST_MESSAGE.encode('ascii')  # message
            ),
        )

    def test_decode(self):
        base = packets.ChatPacket(
            name=self.TEST_NAME,
            message=self.TEST_MESSAGE,
        )
        self.assertEqual(
            base,
            packets.ChatPacket.decode(base.encode()),
        )

    def test_eq(self):
        self.assertNotEqual(
            packets.ChatPacket(),
            None,
        )
        self.assertNotEqual(
            packets.ChatPacket(),
            [],
        )
        self.assertEqual(
            packets.ChatPacket(),
            packets.ChatPacket(),
        )
        self.assertEqual(
            packets.ChatPacket(
                name=self.TEST_NAME,
                message=self.TEST_MESSAGE,
            ),
            packets.ChatPacket(
                name=self.TEST_NAME,
                message=self.TEST_MESSAGE,
            ),
        )
        self.assertNotEqual(
            packets.ChatPacket(
                name=self.TEST_NAME,
                message=self.TEST_MESSAGE,
            ),
            packets.ChatPacket(
                name=self.TEST_NAME + 'a',
                message=self.TEST_MESSAGE,
            ),
        )
        self.assertNotEqual(
            packets.ChatPacket(
                name=self.TEST_NAME,
                message=self.TEST_MESSAGE,
            ),
            packets.ChatPacket(
                name=self.TEST_NAME,
                message=self.TEST_MESSAGE + 'a',
            ),
        )

    def test_repr(self):
        # human eye catcher, no failure
        print(
            '%s' % packets.ChatPacket(
                name=self.TEST_NAME,
                message=self.TEST_MESSAGE,
            )
        )


# vim: expandtab tabstop=4 shiftwidth=4
