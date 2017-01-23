# -*- coding: utf-8 -*-
"""Multicast chat with impersonation prevention."""

import argparse
import logging
import os
import string
import sys
import time
import traceback


import gcap
import gutil


from . import base
from . import packets


PACKAGE_NAME = 'multicast_chat'
PACKAGE_VERSION = '0.0.0'


CHAR_ESCAPE = chr(27)
# Two options for *NIX/Windows
CHARS_BACKSPACE = ('\b', chr(127))

#
# Time to wait for packet.
#
GCAP_TIMEOUT = 100


class ExitException(Exception):
    pass


class NameRepository(base.Base):
    """Name repository.

    Manages impersonation prevention based on mac address.
    """

    HOUSE_KEEPING_INTERVAL = 5  # In seconds
    NAME_TTL = 60  # In seconds

    _last_housekeeping_time = 0

    @staticmethod
    def _get_display_for_name(name, mac):
        return "'%s'@%s" % (
            name,
            packets.EthernetPacket.mac_to_string(mac),
        )

    def __init__(self):
        """Constructor."""
        super(NameRepository, self).__init__()
        self._registration_repo = {}

    def register_name(
        self,
        name,
        mac,
        should_expire=True,
    ):
        """Register/refresh a name.

        Will be applied only if mac matches or name is not registered.

        Args:
            name (string): name.
            mac (bytearray): mac address.
        """
        entry = self._registration_repo.get(name)

        do_register = False
        if entry is None:
            do_register = True
        elif entry['mac'] != mac:
            self.logger.warning(
                'Attempt to impersonate to %s by %s',
                self._get_display_for_name(entry['name'], entry['mac']),
                packets.EthernetPacket.mac_to_string(mac),
            )
        else:
            do_register = True

        if do_register:
            if entry is not None and entry['expire'] is None:
                self.logger.debug(
                    'Ignoring attempt to refresh non expired %s',
                    self._get_display_for_name(entry['name'], entry['mac']),
                )
            else:
                if entry is None:
                    self.logger.info(
                        'Registering: %s',
                        self._get_display_for_name(name, mac),
                    )
                else:
                    self.logger.debug(
                        'Refreshing: %s',
                        self._get_display_for_name(name, mac),
                    )

                self._registration_repo[name] = {
                    'name': name,
                    'mac': mac,
                    'expire': (
                        time.time() + self.NAME_TTL if should_expire
                        else None
                    ),
                }

    def unregister_name(
        self,
        name,
        mac,
    ):
        """Unregister a name.

        Will be applied only if mac matches.

        Args:
            name (string): name.
            mac (bytearray): mac address.
        """
        entry = self._registration_repo.get(name)
        if entry is None:
            self.logger.debug(
                'Ignoring unregister %s it is not in database',
                self._get_display_for_name(name, mac),
            )
        elif entry['mac'] != mac:
            self.logger.warning(
                'Trying to unregister %s by %s',
                self._get_display_for_name(entry['name'], entry['mac']),
                packets.EthernetPacket.mac_to_string(mac),
            )
        else:
            self.logger.info(
                'Unregistering %s',
                self._get_display_for_name(entry['name'], entry['mac']),
            )
            del self._registration_repo[name]

    def is_name_valid(self, name, mac):
        """Returns True if name can by used by mac.

        Args:
            name (str): subject.
            mac (bytearray): mac addres.

        Returns:
            bool: True if approved.
        """
        return self._registration_repo.get(name, {}).get('mac') == mac

    def housekeeping(self):
        """Perform housekeeping tasks."""
        now = time.time()
        if self._last_housekeeping_time < now - self.HOUSE_KEEPING_INTERVAL:
            self._last_housekeeping_time = now

            self.logger.debug('Housekeeping')

            #
            # Remove expired names.
            #
            to_delete = []
            for entry in self._registration_repo.values():
                if entry['expire'] is not None and entry['expire'] < now:
                    self.logger.debug(
                        "Removing expired %s",
                        self._get_display_for_name(
                            entry['name'],
                            entry['mac'],
                        ),
                    )
                    to_delete.append(entry['name'])
            for name in to_delete:
                del self._registration_repo[name]


class Layer(base.Base):
    """Layer abstract base implementation.
    A base class for all layers.
    """

    MODE_NORMAL = 0
    MODE_STOPPING = 1
    MODE_STR = {
        MODE_NORMAL: 'Normal',
        MODE_STOPPING: 'Stopping',
    }

    class QueuedData(base.Base):
        """Data element."""

        def __init__(
            self,
            protocol=None,
            dst=None,
            src=None,
            data=None,
            display='QueuedData',
        ):
            """Constructor.

            Args:
                protocol (object): protocol selection.
                dst (object): destination address.
                src (object): source address.
                data (bytearray): payload.
            """
            super(Layer.QueuedData, self).__init__()
            self.protocol = protocol
            self.dst = dst
            self.src = src
            self.data = data
            self.display = display

        def __repr__(self):
            return Layer.string_to_printable(self.display)

    _mode = MODE_NORMAL

    @property
    def lower_layer(self):
        return self._lower_layer

    @property
    def address(self):
        return self._address

    @property
    def mode(self):
        return self._mode

    def __init__(
        self,
        lower_layer,
        address=None,
    ):
        """Constructor.

        Args:
            lower_layer (Layer): lower layer to register into.
            address (optional, object): address of this layer.
        """
        super(Layer, self).__init__()
        self._lower_layer = lower_layer
        self._address = address

        self._protocols = set()
        self._send_queue = []
        self._receive_queue = []

        self.logger.debug(
            "Initializing layer '%s' with lower '%s' address '%s'",
            self,
            lower_layer,
            self.address_to_string(address),
        )

    def __repr__(self):
        """Representation"""
        return 'Abstract Layer'

    @staticmethod
    def address_to_string(address):
        """Resolve address to string"""
        return address

    @staticmethod
    def string_to_printable(s):
        """Return printable chars only"""
        return ''.join(x for x in s.__repr__() if x in string.printable)

    def register_protocol(self, protocol):
        """Register protocol within this layer.

        Used to filter out unneeded data, so data won't be queueued
        if nobody will ever deque them.

        Args:
            protocol (object): requested protocol.
        """
        self.logger.debug(
            "Layer '%s' registering protocol '%s'",
            self,
            protocol,
        )
        self._protocols.add(protocol)

    def unregister_protocol(self, protocol):
        """Unegister protocol within this layer.

        Args:
            protocol (object): requested protocol.
        """
        self.logger.debug(
            "Layer '%s' unregistering protocol '%s'",
            self,
            protocol,
        )
        self._protocols.remove(protocol)

        # remove all protocol data from queue
        while self.receive(protocol=protocol):
            pass

    def change_mode(self, mode):
        """Change operation mode.

        Args:
            mode (int): operation mode.
        """
        self.logger.debug(
            "Layer '%s' change mode '%s'",
            self,
            self.MODE_STR.get(mode, 'Invalid'),
        )
        self._mode = mode

    def has_work(self):
        return len(self._send_queue) > 0 or len(self._receive_queue) > 0

    def send(self, queued_data):
        """Send data to this layer.

        Args:
            queued_data (self.QueuedData): data to send.
        """
        self.logger.debug(
            "Layer '%s' send '%s'",
            self,
            queued_data.__str__(),
        )
        self._send_queue.append(queued_data)

    def receive(self, protocol=None):
        """Receive data from this layer.

        Args:
            protocol (object): requested protocol.

        Returns:
            self.QueuedData: data or None.
        """
        for i in range(len(self._receive_queue)):
            if self._receive_queue[i].protocol == protocol:
                queued_data = self._receive_queue.pop(i)
                self.logger.debug(
                    "Layer '%s' recieve '%s'",
                    self,
                    queued_data,
                )
                return queued_data

    def queue_receive(self, queued_data):
        """Queue data to be recieved by upper layer.

        Data will be returned to upper layer when it
        calls recieve().

        Args:
            queued_data (QueuedData): data to queue.
        """
        if (
            queued_data.protocol is None or
            queued_data.protocol in self._protocols
        ):
            self.logger.debug(
                "Layer '%s' queue receive '%s'",
                self,
                queued_data,
            )
            self._receive_queue.append(queued_data)

    def dequeue_send(self):
        """Dequeue data sent by upper layer.

        Returns data that was sent to this layer by upper layer
        using send().
        """
        if self._send_queue:
            queued_data = self._send_queue.pop(0)
            self.logger.debug(
                "Layer '%s' dequeue send '%s'",
                self,
                queued_data.__str__(),
            )
            return queued_data
        else:
            return None

    def process(self):
        """Process cycle."""
        pass


class PhysicalLayer(Layer):
    """Physical layer implementation.

    Uses gcap to receive/send packets.
    """

    def __init__(
        self,
        cap,
    ):
        """Constructor.

        Args:
            cap (GCap): reference to gcap instance.
        """
        super(PhysicalLayer, self).__init__(
            lower_layer=None,
        )
        self._cap = cap

    def __repr__(self):
        return 'Pysical Layer'

    def process(self):
        super(PhysicalLayer, self).process()

        while True:
            d = self.dequeue_send()
            if d is None:
                break
            self._cap.send_packet(d.data)

        if self.mode == self.MODE_NORMAL:
            cap_packet = self._cap.next_packet()
            if cap_packet:
                self.queue_receive(
                    queued_data=self.QueuedData(
                        data=cap_packet['data'],
                    )
                )


class EthernetLayer(Layer):
    """Ethernet II layer."""

    def __init__(
        self,
        lower_layer,
        address,
        local_loopback_mode,
    ):
        """Constructor.

        Args:
            lower_layer (Layer): lower layer to interact with.
            address (bytearray): local mac address.
            local_loopback_mode (bool): debug only mode process own packets.
        """
        super(EthernetLayer, self).__init__(
            lower_layer=lower_layer,
            address=address,
        )
        self._local_loopback_mode = local_loopback_mode

    def __repr__(self):
        return 'Ethernet Layer'

    @staticmethod
    def address_to_string(address):
        return packets.EthernetPacket.mac_to_string(address)

    def process(self):
        super(EthernetLayer, self).process()

        while True:
            d = self.lower_layer.receive()
            if d is None:
                break
            packet = packets.EthernetPacket.decode(d.data)
            if self._local_loopback_mode or packet.src != self.address:
                self.queue_receive(
                    queued_data=self.QueuedData(
                        protocol=packet.ethertype,
                        dst=packet.dst,
                        src=packet.src,
                        data=packet.data,
                        display=packet,
                    )
                )

        while True:
            d = self.dequeue_send()
            if d is None:
                break
            packet = packets.EthernetPacket(
                ethertype=d.protocol,
                dst=d.dst,
                src=d.src if d.src else self.address,
                data=d.data,
            )
            self.lower_layer.send(
                self.QueuedData(
                    data=packet.encode(),
                    display=packet,
                )
            )


class RegistrationLayer(Layer):
    """Registration layer."""

    ANNOUNCE_INTERVAL = 2

    _last_announce_time = 0

    def _announce(self, command):
        """Announce registration status.

        Args:
            command (int): command to send.
        """
        packet = packets.RegistrationPacket(
            command=command,
            name=self._local_name,
        )
        self.lower_layer.send(
            queued_data=self.QueuedData(
                protocol=packets.RegistrationPacket.ETHERTYPE,
                dst=packets.EthernetPacket.MAC_BROADCAST,
                data=packet.encode(),
                display=packet,
            )
        )

    def __init__(
        self,
        lower_layer,
        name_repository,
        local_name,
    ):
        """Constructor.

        Args:
            lower_layer (Layer): lower layer to interact with.
            name_repository (NameRepository): name repository to interact with.
            local_name (str): local name to announce.
        """
        super(RegistrationLayer, self).__init__(
            lower_layer=lower_layer,
        )
        self._local_name = local_name
        self._name_repository = name_repository

        self.lower_layer.register_protocol(
            protocol=packets.RegistrationPacket.ETHERTYPE,
        )

        #
        # Register our own name so nobody can
        # impersonate to us.
        # This entry should not expire.
        #
        self._name_repository.register_name(
            name=self._local_name,
            mac=self.lower_layer.address,
            should_expire=False,
        )

    def __del__(self):
        self._name_repository.unregister_name(
            name=self._local_name,
            mac=self.lower_layer.address,
        )
        self.lower_layer.unregister_protocol(
            protocol=packets.RegistrationPacket.ETHERTYPE,
        )

    def __repr__(self):
        return 'Registration Layer'

    def process(self):
        super(RegistrationLayer, self).process()

        while True:
            d = self.lower_layer.receive(
                protocol=packets.RegistrationPacket.ETHERTYPE,
            )
            if d is None:
                break
            packet = packets.RegistrationPacket.decode(d.data)
            if packet.command == packet.COMMAND_ALLOCATE:
                self._name_repository.register_name(
                    name=packet.name,
                    mac=d.src,
                )
            elif packet.command == packet.COMMAND_RELEASE:
                self._name_repository.unregister_name(
                    name=packet.name,
                    mac=d.src,
                )

        now = time.time()
        if self._last_announce_time < now - self.ANNOUNCE_INTERVAL:
            self._last_announce_time = now
            self._announce(
                command=packets.RegistrationPacket.COMMAND_ALLOCATE,
            )

    def change_mode(self, mode):
        super(RegistrationLayer, self).change_mode(mode)

        if self.mode == self.MODE_STOPPING:
            self._announce(
                command=packets.RegistrationPacket.COMMAND_RELEASE,
            )


class ChatLayer(Layer):
    """Chat layer."""

    PROMPT_EDIT = '>'
    PROMPT_STANDARD = ':'

    _current_message = ''

    def _send_string(self, s):
        """Send a string to higher layer.

        Args:
            s (str): string.
        """
        self.queue_receive(
            queued_data=self.QueuedData(
                data=s.encode('utf-8'),
                display=s,
            ),
        )

    def _send_chat_line(
        self,
        name,
        message,
        prompt=None,
        valid=True,
        permanent=False,
    ):
        """Send a chat line.

        Erase current line, write name and message, with optional markers.

        Args:
            name (str): chatter's name.
            message (str): message.
            prompt (optional, str): prompt to use before message.
            valid (optional, bool): is chatter's name valid.
            permanent (optional, bool): print new line at end of line.
        """
        inner = '{name:14}{valid}{prompt} {message}'.format(
            name=name,
            message=message,
            prompt=prompt if prompt is not None else self.PROMPT_STANDARD,
            valid=' ' if valid else 'X',
        )
        self._send_string(
            (
                '\r{empty}\r'
                '{inner}{permanent}'
            ).format(
                empty=' ' * 79,
                inner=inner,
                permanent='\r\n' if permanent else '',
            )
        )
        if permanent:
            self.logger.info('Message: %s', inner)

    def _refresh_prompt(self):
        """Refresh current prompt.

        Prints local chatter's line, handy when previous was overwritten.
        """
        self._send_chat_line(
            name=self._local_name,
            message=self._current_message,
            prompt=self.PROMPT_EDIT,
        )

    def __init__(
        self,
        lower_layer,
        mac_multicast,
        name_repository,
        local_name,
    ):
        """Constructor.

        Args:
            lower_layer (Layer): lower layer to interact with.
            mac_multicast (bytearray): mac to use as destination.
            name_repository (NameRepository): name repository to interact with.
            local_name (str): local name to announce.
        """
        super(ChatLayer, self).__init__(
            lower_layer=lower_layer,
        )
        self._mac_multicast = mac_multicast
        self._name_repository = name_repository
        self._local_name = local_name

        self.lower_layer.register_protocol(
            protocol=packets.ChatPacket.ETHERTYPE,
        )
        self._refresh_prompt()

    def __del__(self):
        self.lower_layer.unregister_protocol(
            protocol=packets.ChatPacket.ETHERTYPE,
        )

    def __repr__(self):
        return 'Chat Layer'

    def process(self):
        super(ChatLayer, self).process()

        while True:
            d = self.lower_layer.receive(
                protocol=packets.ChatPacket.ETHERTYPE,
            )
            if d is None or d.dst != self._mac_multicast:
                break
            packet = packets.ChatPacket.decode(d.data)
            self._send_chat_line(
                name=packet.name,
                message=packet.message,
                prompt=':',
                valid=self._name_repository.is_name_valid(
                    name=packet.name,
                    mac=d.src,
                ),
                permanent=True,
            )
            self._refresh_prompt()

        while True:
            d = self.dequeue_send()
            if d is None:
                break

            for c in d.data.decode('utf-8'):
                if c == '\r':
                    packet = packets.ChatPacket(
                        name=self._local_name,
                        message=self._current_message,
                    )
                    self.lower_layer.send(
                        queued_data=self.QueuedData(
                            protocol=packets.ChatPacket.ETHERTYPE,
                            dst=self._mac_multicast,
                            data=packet.encode(),
                            display=packet,
                        )
                    )
                    self._send_chat_line(
                        name=self._local_name,
                        message=self._current_message,
                        permanent=True,
                    )
                    self._current_message = ''
                    self._refresh_prompt()
                elif c in CHARS_BACKSPACE:
                    if self._current_message:
                        self._send_string('\b \b')
                        self._current_message = self._current_message[:-1]
                else:
                    self._send_string(c)
                    self._current_message += c

    def change_mode(self, mode):
        super(ChatLayer, self).change_mode(mode)

        if self.mode == self.MODE_STOPPING:
            self._send_string('\r\n')


class TerminalLayer(Layer):
    """Terminal layer.

    Interacts with terminal.
    """

    def __init__(
        self,
        lower_layer,
        input_char,
        output_stream,
    ):
        """Constructor.

        Args:
            lower_layer (Layer): lower layer to interact with.
            input_char (gutil.Char): Char instance ot interact with.
            output_stream (file): stream to send output to.
        """
        super(TerminalLayer, self).__init__(
            lower_layer=lower_layer,
        )
        self._input_char = input_char
        self._output_stream = output_stream

    def __repr__(self):
        return 'Terminal Layer'

    def process(self):
        super(TerminalLayer, self).process()

        while True:
            d = self.lower_layer.receive()
            if d is None:
                break

            self._output_stream.write(d.data.decode('utf-8'))
            self._output_stream.flush()

        while self.mode == self.MODE_NORMAL:
            c = self._input_char.getchar()
            if c is None:
                break
            if c == CHAR_ESCAPE:
                raise ExitException()

            self.lower_layer.send(
                queued_data=self.QueuedData(
                    data=c.encode('utf-8'),
                    display=c,
                )
            )


def parse_args():
    """Parse program argument."""

    LOG_STR_LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }

    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description=(
            'multicast chat with impersonation prevention'
        ),
    )
    parser.add_argument(
        '--version',
        action='version',
        version=PACKAGE_VERSION,
    )
    parser.add_argument(
        '--log-level',
        dest='log_level_str',
        default='INFO',
        choices=LOG_STR_LEVELS.keys(),
        help='Log level',
    )
    parser.add_argument(
        '--log-file',
        dest='log_file',
        metavar='FILE',
        default=os.devnull,
        help='Logfile to write to, default: %(default)s',
    )
    parser.add_argument(
        '--interface',
        dest='interface',
        help='Interface name, default is first',
    )
    parser.add_argument(
        '--name',
        dest='name',
        required=True,
        help='Chat user name',
    )
    parser.add_argument(
        '--mac-local',
        dest='mac_local_string',
        required=True,
        metavar='MAC',
        help='Local Ethernet MAC address xx:xx:xx:xx:xx:xx',
    )
    parser.add_argument(
        '--mac-multicast',
        dest='mac_multicast_string',
        default=packets.EthernetPacket.mac_to_string(
            packets.EthernetPacket.MAC_BROADCAST,
        ),
        metavar='MAC',
        help=(
            'Multicast Ethernet MAC address xx:xx:xx:xx:xx:xx, '
            'default broadcast'
        ),
    )
    parser.add_argument(
        '--local-loopback-mode',
        dest='local_loopback_mode',
        default=False,
        action='store_true',
        help=(
            'Allows to run on same computer, debug only.'
        ),
    )
    args = parser.parse_args()
    args.log_level = LOG_STR_LEVELS[args.log_level_str]
    args.mac_local = packets.EthernetPacket.mac_from_string(
        args.mac_local_string,
    )
    args.mac_multicast = packets.EthernetPacket.mac_from_string(
        args.mac_multicast_string,
    )
    if args.interface is None:
        args.interface = gcap.GCap.get_interfaces()[0]['name']
    return args


def main():
    """Main implementation."""

    args = parse_args()

    logger = base.setup_logging(
        stream=open(args.log_file, 'a'),
        level=args.log_level,
    )
    logger.info('Startup %s-%s', PACKAGE_NAME, PACKAGE_VERSION)
    logger.debug('Args: %s', args)

    try:
        with gcap.GCap(iface=args.interface, timeout=GCAP_TIMEOUT) as cap:
            with gutil.Char() as char:
                name_repository = NameRepository()

                #
                # Construct layer hierarchy.
                #
                #   Terminal
                #       |
                #       |
                #       V
                #      Chat     Registration
                #        \        /
                #         |      |
                #         V      V
                #         Ethernet
                #            |
                #            |
                #            V
                #         Physical
                #

                logger.debug('Constructing layers')
                layers = []

                def _register_layer(e):
                    "Tiny local helper."
                    layers.append(e)
                    return e

                physical_layer = _register_layer(
                    PhysicalLayer(
                        cap=cap,
                    )
                )
                ethernet_layer = _register_layer(
                    EthernetLayer(
                        lower_layer=physical_layer,
                        address=args.mac_local,
                        local_loopback_mode=args.local_loopback_mode,
                    )
                )
                _register_layer(
                    RegistrationLayer(
                        lower_layer=ethernet_layer,
                        name_repository=name_repository,
                        local_name=args.name,
                    )
                )
                chat_layer = _register_layer(
                    ChatLayer(
                        lower_layer=ethernet_layer,
                        mac_multicast=args.mac_multicast,
                        name_repository=name_repository,
                        local_name=args.name,
                    )
                )
                _register_layer(
                    TerminalLayer(
                        lower_layer=chat_layer,
                        input_char=char,
                        output_stream=sys.stdout,
                    )
                )

                logger.debug('Procssing layers')
                try:
                    while True:
                        for layer in layers:
                            layer.process()
                        name_repository.housekeeping()
                except ExitException:
                    pass

                logger.debug('Notify stop')
                for layer in layers:
                    layer.change_mode(layer.MODE_STOPPING)

                logger.debug('Wait as long as processing')
                pending = True
                while pending:
                    pending = False
                    for layer in layers:
                        layer.process()
                        pending = pending or layer.has_work()
    except Exception as e:
        logger.error('Unexpected exception %s', e)
        logger.debug('Exception', exc_info=True)

        # this is how we format exceptions manually
        # can be simpler using traceback.print_exc()
        print("Unexpected exception %s" % e)
        exc_type, exc_value, exc_traceback = sys.exc_info()
        print("%s" % ''.join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        ))


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
