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

LOGGING_GRADIENT = [
    # Debug
    31,
    # Info
    75,
    # Checkpoint
    81,
    # Warning
    202,
    # Error
    160,
    # Exception
    124,
    # Alert
    89,
    # Critical
    163,
]


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


gradients = [GRADIENT, LOGGING_GRADIENT]
for g in gradients:
    sys.stdout.write("\n")
    for i in g:
        sys.stdout.write(normal(i))
        sys.stdout.write(f"██")
    sys.stdout.write("\n")
