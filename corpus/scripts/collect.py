"""Compatibility entry point: incrementally import supplied records or files."""
import sys
from manage import main
if __name__ == '__main__':
    raise SystemExit(main(['import', *sys.argv[1:]]))
