"""Compatibility entry point: retry missing fulltexts without replacing reviews."""
import sys
from manage import main
if __name__ == '__main__':
    raise SystemExit(main(['fetch', *sys.argv[1:]]))
