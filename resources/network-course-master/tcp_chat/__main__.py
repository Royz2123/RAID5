# -*- coding: utf-8 -*-

import argparse
import contextlib
import logging
import os
import socket
import sys
import traceback


import gutil


from . import base


PACKAGE_NAME = 'tcp_chat'
PACKAGE_VERSION = '0.0.0'


CHAR_ESCAPE = chr(27)
# Two options for *NIX/Windows
CHARS_BACKSPACE = ('\b', chr(127))

TIMEOUT = 0.05
DEFAULT_PORT = 8888
MAX_LINE_SIZE = 70


class DisconnectException(RuntimeError):
    pass


class Util(object):

    # debug only
    debug_one_by_one = False

    @classmethod
    def send_all(clz, s, to_send):
        if to_send['buffer']:
            if clz.debug_one_by_one:
                n = 1
            else:
                n = len(to_send['buffer'])

            sent = s.send(to_send['buffer'][:n].encode('utf-8'))
            to_send['buffer'] = to_send['buffer'][sent:]
            return len(to_send['buffer']) == 0

    @classmethod
    def receive_all(clz, s, to_receive):
        ret = False
        try:
            n = to_receive['required'] - len(to_receive['buffer'])
            if n > 0:
                if Util.debug_one_by_one:
                    n = 1

                buffer = s.recv(n)
                if not buffer:
                    raise DisconnectException('Disconnect')
                to_receive['buffer'] += buffer.decode('utf-8')

            ret = to_receive['required'] == len(to_receive['buffer'])
        except socket.timeout:
            pass
        return ret

    @staticmethod
    def write_console(str):
        sys.stdout.write(str)
        sys.stdout.flush()


class ProtocolString(base.Base):
    (
        _RECEIVE_STATE_INIT,
        _RECEIVE_STATE_LENGTH,
        _RECEIVE_STATE_DATA,
    ) = range(3)

    _state = _RECEIVE_STATE_INIT
    _to_send = {
        'buffer': '',
    }

    def __init__(self, s):
        super(ProtocolString, self).__init__()
        self._s = s

    def receive_string(self):
        """Receive a string.

        Returns (str):
            str: String.
            None: No string.
        """
        ret = None
        if self._state == self._RECEIVE_STATE_INIT:
            self._to_receive = {
                'buffer': '',
                'required': 2,
            }
            self._state = self._RECEIVE_STATE_LENGTH
        elif self._state == self._RECEIVE_STATE_LENGTH:
            if Util.receive_all(self._s, self._to_receive):
                self._to_receive = {
                    'buffer': '',
                    'required': int(self._to_receive['buffer'], 16),
                }
                self._state = self._RECEIVE_STATE_DATA
        elif self._state == self._RECEIVE_STATE_DATA:
            if Util.receive_all(self._s, self._to_receive):
                ret = self._to_receive['buffer']
                self._state = self._RECEIVE_STATE_INIT
        return ret

    def queue_string(self, string):
        """Queue string for send."""
        LEN_BYTES = 2
        MAX = 2 ** (LEN_BYTES * 4) - 1
        if len(string) > MAX:
            self.logger.warn('Message was truncated')
        self._to_send['buffer'] += '%02x%s' % (
            min(MAX, len(string)),
            string[:MAX],
        )

    def send_all(self):
        """Attempt to send as much as possible."""
        return Util.send_all(self._s, self._to_send)


class Chat(base.Base):

    def __init__(self, s, name):
        super(Chat, self).__init__()
        self._s = s
        self._local_name = name

    def chat(self):
        self._s.settimeout(TIMEOUT)

        prot = ProtocolString(self._s)

        try:
            self.logger.debug('Sending my name')
            prot.queue_string(self._local_name)
            self.logger.debug('Waiting for peer name')
            peer_name = None
            while peer_name is None:
                prot.send_all()
                peer_name = prot.receive_string()
            self.logger.debug('Peer name is %s', peer_name)

            with gutil.Char() as char:
                local_message = ''
                print_local_line = True
                keep_running = True
                while keep_running:
                    if print_local_line:
                        print_local_line = False
                        Util.write_console(
                            '%-15s: %s' % (
                                self._local_name,
                                local_message,
                            )
                        )

                    prot.send_all()
                    peer_message = prot.receive_string()
                    if peer_message is not None:
                        self.logger.debug(
                            "Got peer message: '%s'",
                            peer_message,
                        )
                        Util.write_console(
                            (
                                '\r%s\r'
                                '%-15s: %s\n'
                            ) % (
                                ' ' * MAX_LINE_SIZE,
                                peer_name,
                                peer_message,
                            )
                        )
                        print_local_line = True

                    c = char.getchar()
                    if c is None:
                        pass
                    elif c in CHARS_BACKSPACE:
                        if local_message:
                            local_message = local_message[:-1]
                            Util.write_console('\b \b')
                    elif c == CHAR_ESCAPE:
                        self.logger.debug('Exiting')
                        Util.write_console('\n')
                        keep_running = False
                    elif c == '\r':
                        self.logger.debug(
                            "Sending message to peer '%s'",
                            local_message,
                        )
                        Util.write_console('\n')
                        prot.queue_string(local_message)
                        local_message = ''
                        print_local_line = True
                    else:
                        local_message += c
                        Util.write_console(c)
        except DisconnectException:
            self.logger.debug('Disconnect')
            Util.write_console('\n')


def parse_args():
    """Parse program argument."""

    LOG_STR_LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    MODE_STR = {
        'active': True,
        'passive': False,
    }

    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description=(
            'TCP chat'
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
        '--bind-address',
        dest='bind_address',
        metavar='ADDRESS',
        default='0.0.0.0',
        help='Bind address, default: %(default)s',
    )
    parser.add_argument(
        '--bind-port',
        dest='bind_port',
        metavar='PORT',
        default=0,
        type=int,
        help='Bind port, default for listen %s' % DEFAULT_PORT,
    )
    parser.add_argument(
        '--destination-address',
        dest='destination_address',
        metavar='ADDRESS',
        default=None,
        help='Destination address',
    )
    parser.add_argument(
        '--destination-port',
        dest='destination_port',
        metavar='PORT',
        default=DEFAULT_PORT,
        type=int,
        help='Destination port, default %(default)s',
    )
    parser.add_argument(
        '--name',
        dest='name',
        required=True,
        help='Chat user name',
    )
    parser.add_argument(
        '--mode',
        dest='mode_str',
        default='active',
        choices=MODE_STR.keys(),
        help='Mode to use, default: %(default)s',
    )
    parser.add_argument(
        '--debug-one-by-one',
        dest='debug_one_by_one',
        default=False,
        action='store_true',
        help='Enable on-by-one debug',
    )
    args = parser.parse_args()
    args.log_level = LOG_STR_LEVELS[args.log_level_str]
    args.mode_active = MODE_STR[args.mode_str]
    if args.mode_active:
        if args.destination_address is None:
            raise RuntimeError('Please specify destination address')
    else:
        if args.bind_port == 0:
            args.bind_port = DEFAULT_PORT
    return args


def main():
    """Main implementation."""

    args = parse_args()

    logger = base.setup_logging(
        stream=open(args.log_file, 'a'),
        level=args.log_level,
    )

    try:
        logger.info('Startup %s-%s', PACKAGE_NAME, PACKAGE_VERSION)
        logger.debug('Args: %s', args)

        if args.debug_one_by_one:
            Util.debug_one_by_one = True

        with contextlib.closing(
            socket.socket(
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
            )
        ) as s:
            logger.debug('Binding')
            s.bind((args.bind_address, args.bind_port))
            if args.mode_active:
                logger.debug('Connecting')
                s.connect((args.destination_address, args.destination_port))
                logger.debug('Connected')
                Chat(s=s, name=args.name).chat()
            else:
                s.listen(1)
                while True:
                    logger.debug('Accepting')
                    print('Waiting for client')
                    accepted, addr = s.accept()
                    logger.debug('Accepted')
                    with contextlib.closing(accepted):
                        Chat(s=accepted, name=args.name).chat()

        logger.debug('Exit')
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
