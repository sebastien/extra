RESET = "\033[0m"
GRADIENT = (
    59,
    66,
    108,
    151,
    194,
    231,
    230,
    229,
    228,
    227,
    226,
    220,
    214,
    208,
    202,
    160,
    196,
)


def lerp(a, b, k):
    return a + (b - a) * k


def normal(color):
    return "\033[38;5;%sm" % (color)


def bold(color):
    return "\033[1;38;5;%sm" % (color)


import sys

i = 16
for y in range(40):
    for x in range(6):
        sys.stdout.write(normal(i))
        sys.stdout.write(f"██{i:3d} ")
        i += 1
    sys.stdout.write("\n")


sys.stdout.write("\n")
for i in GRADIENT:
    sys.stdout.write(normal(i))
    sys.stdout.write(f"██")
sys.stdout.write("\n")
