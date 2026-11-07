import sys

from demo import demo
from shell import shell

if __name__ == "__main__":
    if sys.argv[1:] == ["--demo"]:
        demo()
    else:
        shell()