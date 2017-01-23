#!/usr/bin/python


import gutil


with gutil.Char() as char:
    while True:
        c = char.getchar()
        if c:
            print('!%s!' % c)
