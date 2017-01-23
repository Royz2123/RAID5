import os
import platform
import sys


if platform.system() == 'Windows':
    import msvcrt
else:
    import select
    import termios
    import tty


if platform.system() == 'Windows':
    class Char():

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            pass

        def getchar(self):
            if msvcrt.kbhit():
                c = msvcrt.getch().decode('utf-8', 'ignore')
                if len(c) == 0:  # utf-8 error
                    return None
                return c
            else:
                return None
else:
    class Char():

        def __enter__(self):
            self._attr = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            new = termios.tcgetattr(sys.stdin)
            new[0] &= ~termios.ICRNL
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, new)
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._attr)

        def getchar(self):
            if select.select([sys.stdin], [], [], 0) != ([], [], []):
                c = os.read(sys.stdin.fileno(), 1).decode('utf-8', 'ignore')
                if len(c) == 0:  # utf-8 error
                    return None
                return c
            else:
                return None


def main():
    with Char() as char:
        while True:
            c = char.getchar()
            if c:
                sys.stdout.write(c)
                sys.stdout.flush()


if __name__ == '__main__':
    main()
