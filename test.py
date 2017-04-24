import os

fd = os.open("C:\Users\Royz\Documents\yo_bro.txt", os.O_CREAT | os.O_RDWR, 0o666)
for i in range(100000):
    os.write(fd, str(-i) + ", ")
os.close(fd)