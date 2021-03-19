def error(channel, *args):
    print("[!]", channel, args)


def warning(channel, *args):
    print("[ ]", channel, args)


def info(channel, *args):
    print("---", channel, args)
