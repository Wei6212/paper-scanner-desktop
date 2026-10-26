import sys
from pathlib import Path

if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--self-test':
        from paper_scanner.selfcheck import run
        raise SystemExit(run(Path(sys.argv[2]), Path(sys.argv[3])))
    from paper_scanner.ui import main
    raise SystemExit(main())
