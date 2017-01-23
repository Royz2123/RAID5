# -*- coding: utf-8 -*-
"""Packets encoding/decoding."""


import re


from . import base


class EncodeDecodeUtils(object):
    """Utilities for encoding/decoding."""

    @staticmethod
    def decode_binary(buf, n):
        """Decode octet string at n length.

        Args:
            buf (bytearray): buffer to decode.
            n (int): number of octets.

        Returns:
            tuple: first is parsed entry second is remaining.
        """
        return buf[:n], buf[n:]

    @staticmethod
    def decode_string(buf, n, encoding='ascii'):
        """Decode ascii string at n length.

        Args:
            buf (bytearray): buffer to decode.
            n (int): number of octets.

        Returns:
            tuple: first is parsed entry second is remaining.
        """
        return buf[:n].decode(encoding), buf[n:]

    @staticmethod
    def decode_integer(buf, n):
        """Decode integer at n length big endian.

        Args:
            buf (bytearray): buffer to decode.
            n (int): number of octets.

        Returns:
            tuple: first is parsed entry second is remaining.
        """
        ret = 0
        for x in buf[:n]:
            ret = (ret << 8) + x
        return ret, buf[n:]

    @staticmethod
    def decode_binary_as_hexstring(buf, n, sep=''):
        """Decode binary as hex string.

        Args:
            buf (bytearray): buffer to decode.
            n (int): number of octets.
            sep (optional, str): octet separator.

        Returns:
            tuple: first is parsed entry second is remaining.
        """
        return sep.join('%02x' % x for x in buf[:n]), buf[n:]

    @staticmethod
    def encode_binary(x, n):
        """Encode binary.

        Args:
            x (bytearray): data to encode.

        Returns:
            bytearray: data.
        """
        return x[:n]

    @staticmethod
    def encode_string(s):
        """Encode ascii string.

        Args:
            s (str): data to encode.

        Returns:
            bytearray: data.
        """
        return s.encode('ascii')

    @staticmethod
    def encode_integer(i, n):
        """Encode big endian integer.

        Args:
            i (int): integer to encode.
            n (int): octet length.

        Returns:
            bytearray: data.
        """
        l = []
        for x in range(n):
            l.append(i & 0xff)
            i >>= 8
        return bytearray(l[::-1])

    @staticmethod
    def encode_binary_from_hexstring(h, sep=''):
        """Encode binary out of hex string.

        Arguments:
            h (str): hex string.
            sep (optional, str): octet separator.

        Returns:
            bytearray: data.
        """
        return bytearray(
            int(x, 16) for x in re.findall('..', h.replace(sep, ''))
        )


class Packet(base.Base):
    """Base for packet decoding/encoding."""

    def __init__(self):
        super(Packet, self).__init__()

    def __repr__(self):
        """Representation operator."""
        return ''

    def encode(self):
        """Encode as bytearray.

        Raises:
            RuntimeError: If packet is incomplete.
        """
        return bytearray()

    @staticmethod
    def decode(buf):
        """Decode buffer to packet.

        Args:
            buf (bytebuffer): buffer to decode.

        Returns:
            EthernetPacket: packet.

        Raises:
            RuntimeError: if buffer cannot b parsed.
        """
        pass


class EthernetPacket(Packet):
    """Ethernet packet decoding/encoding."""

    @staticmethod
    def mac_to_string(mac, sep=':'):
        """Return string representation of a mac address.

        Args:
            mac (bytearray): a mac.
            sep (optional, str): octet separator.

        Retruns:
            str: String representation.
        """
        return (
            None if mac is None
            else EncodeDecodeUtils.decode_binary_as_hexstring(
                mac,
                EthernetPacket.MAC_SIZE,
                sep=sep,
            )[0]
        )

    @staticmethod
    def mac_from_string(s, sep=':'):
        """Returns mac out of string representation.

        Args:
            s (str): string.
            sep (optional, str): octet separator.

        Returns:
            bytearray: mac address.
        """
        return EncodeDecodeUtils.encode_binary_from_hexstring(s, sep)

    @staticmethod
    def mac_is_multicast(mac):
        """Returns True if mac address is a multicast address

        Args:
            mac (bytearray): mac address.

        Returns:
            bool: True if multicast address.
        """
        return (mac[0] & 0x01) != 0

    MAC_SIZE = 6
    ETHERTYPE_SIZE = 2
    MAX_SIZE = 1518
    MAC_BROADCAST = bytearray((0xff,) * MAC_SIZE)

    def __init__(
        self,
        dst=None,
        src=None,
        ethertype=None,
        data=None,
    ):
        """Constructor.

        Args:
            dst (bytearray): destination address.
            src (bytearray): source address.
            ethertype (int): ethertype.
            data (bytearray): payload.
        """
        super(EthernetPacket, self).__init__()
        self.dst = dst
        self.src = src
        self.ethertype = ethertype
        self.data = None if data is None else bytearray(data)

    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented

        return all((
            self.dst == other.dst,
            self.src == other.src,
            self.ethertype == other.ethertype,
            self.data == other.data,
        ))

    def __repr__(self):
        return (
            '{{'
            '{super} '
            'EthernetPacket: '
            'dst: {dst}, '
            'src: {src}, '
            'ethertype: {ethertype} '
            'data: {data} '
            '}}'
        ).format(
            super=super(EthernetPacket, self).__repr__(),
            self=self,
            dst=self.mac_to_string(self.dst),
            src=self.mac_to_string(self.src),
            ethertype=(
                'N/A' if self.ethertype is None
                else '{0:04x}'.format(self.ethertype)
            ),
            data=(
                'N/A' if self.data is None
                else EncodeDecodeUtils.decode_binary_as_hexstring(
                    self.data,
                    None,
                )[0]
            ),
        )

    def encode(self):
        if None in (
            self.dst,
            self.src,
            self.ethertype,
            self.data,
        ):
            raise RuntimeError('Incomplete ethernet packet')

        if len(self.dst) != self.MAC_SIZE:
            raise RuntimeError('Invalid destination MAC address')
        if len(self.src) != self.MAC_SIZE:
            raise RuntimeError('Invalid source MAC address')
        if (
            self.ethertype < 0 or
            self.ethertype >= 2 ** (8 * self.ETHERTYPE_SIZE)
        ):
            raise RuntimeError('Invalid ethertype value %s', self.ethertype)

        encoded = (
            EncodeDecodeUtils.encode_binary(
                self.dst,
                self.MAC_SIZE,
            ) +
            EncodeDecodeUtils.encode_binary(
                self.src,
                self.MAC_SIZE,
            ) +
            EncodeDecodeUtils.encode_integer(
                self.ethertype,
                self.ETHERTYPE_SIZE
            ) +
            self.data
        )

        if len(encoded) > self.MAX_SIZE:
            raise RuntimeError('Too large ethernet packet')

        return encoded

    @staticmethod
    def decode(buf):
        packet = EthernetPacket()

        if len(buf) < packet.MAC_SIZE * 2 + packet.ETHERTYPE_SIZE:
            raise RuntimeError('Too small ethernet packet')
        if len(buf) > packet.MAX_SIZE:
            raise RuntimeError(
                (
                    'Too large ethernet packet at size {actual} '
                    'expected {expected}'
                ).format(
                    actual=len(buf),
                    expected=packet.MAX_SIZE,
                )
            )

        packet.dst, buf = EncodeDecodeUtils.decode_binary(
            buf,
            packet.MAC_SIZE,
        )
        packet.src, buf = EncodeDecodeUtils.decode_binary(
            buf,
            packet.MAC_SIZE,
        )
        packet.ethertype, buf = EncodeDecodeUtils.decode_integer(
            buf,
            packet.ETHERTYPE_SIZE,
        )
        packet.data, buf = EncodeDecodeUtils.decode_binary(
            buf,
            None
        )
        return packet


class RegistrationPacket(Packet):
    """Registration packet decoder/encoder."""

    ETHERTYPE = 0x1002
    COMMAND_SIZE = 1
    NAME_SIZE = 10

    COMMAND_ALLOCATE = 0
    COMMAND_RELEASE = 1
    COMMAND_DESC = {
        COMMAND_ALLOCATE: 'allocate',
        COMMAND_RELEASE: 'release',
    }

    def __init__(
        self,
        command=None,
        name=None,
    ):
        """Constructor.

        Args:
            command (int): registration command.
            name (str): annoynce name.
        """
        super(RegistrationPacket, self).__init__()
        self.command = command
        self.name = name

    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented

        return all((
            self.command == other.command,
            self.name == other.name,
        ))

    def __repr__(self):
        return (
            '{{'
            '{super} '
            'RegistrationPacket: '
            'command: {command}, '
            'name: {self.name} '
            '}}'
        ).format(
            super=super(RegistrationPacket, self).__repr__(),
            self=self,
            command=self.COMMAND_DESC.get(
                self.command,
                'Invalid',
            ),
        )

    def encode(self):
        if None in (
            self.command,
            self.name,
        ):
            raise RuntimeError('Incomplete registration packet')

        if self.command < 0 or self.command >= 2 ** (self.COMMAND_SIZE * 8):
            raise RuntimeError(
                (
                    'Invalid registration packet, '
                    'command {command} too large'
                ).format(
                    command=self.command,
                )
            )

        if self.command not in (
            self.COMMAND_ALLOCATE,
            self.COMMAND_RELEASE,
        ):
            raise RuntimeError(
                'Invalid registration packet, invalid command=%s',
                self.command,
            )

        return (
            EncodeDecodeUtils.encode_integer(
                self.command,
                self.COMMAND_SIZE,
            ) +
            EncodeDecodeUtils.encode_string(
                self.name[:self.NAME_SIZE].ljust(
                    self.NAME_SIZE
                )
            )
        )

    @staticmethod
    def decode(buf):
        packet = RegistrationPacket()

        if len(buf) < packet.NAME_SIZE:
            raise RuntimeError('Invalid registration packet')

        packet.command, buf = EncodeDecodeUtils.decode_integer(
            buf,
            packet.COMMAND_SIZE,
        )
        packet.name, buf = EncodeDecodeUtils.decode_string(
            buf,
            packet.NAME_SIZE,
        )
        packet.name = packet.name.strip()
        return packet


class ChatPacket(Packet):
    """Chat packet decoder/encoder."""

    ETHERTYPE = 0x1001
    NAME_SIZE = 10

    def __init__(
        self,
        name=None,
        message=None,
    ):
        """Constructor.

        Args:
            name (str): chatter's name.
            message (str): message.
        """
        super(ChatPacket, self).__init__()
        self.name = name
        self.message = message

    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented

        return all((
            self.name == other.name,
            self.message == other.message,
        ))

    def __repr__(self):
        return (
            '{{'
            '{super} '
            'ChatPacket: '
            'name: {self.name}, '
            'message: {self.message} '
            '}}'
        ).format(
            super=super(ChatPacket, self).__repr__(),
            self=self,
        )

    def encode(self):
        if None in (self.name, self.message):
            raise RuntimeError('Incomplete chat packet')

        return (
            EncodeDecodeUtils.encode_string(
                self.name[:self.NAME_SIZE].ljust(
                    self.NAME_SIZE
                )
            ) +
            EncodeDecodeUtils.encode_string(self.message)
        )

    @staticmethod
    def decode(buf):
        packet = ChatPacket()

        if len(buf) < packet.NAME_SIZE:
            raise RuntimeError('Invalid chat packet')

        packet.name, buf = EncodeDecodeUtils.decode_string(
            buf,
            packet.NAME_SIZE,
        )
        packet.name = packet.name.strip()
        packet.message, buf = EncodeDecodeUtils.decode_string(buf, None)
        return packet


# vim: expandtab tabstop=4 shiftwidth=4
