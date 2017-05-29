import os

fd = os.open(
    "C:\Users\Royz\Documents\_test_file.txt",
    os.O_CREAT | os.O_RDWR | os.O_BINARY,
    0o666
)
for i in range(100000):
    os.write(fd, str(-i) + ", ")
os.close(fd)
