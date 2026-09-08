import sys

from .pipeline import main

# The guard matters: N-BEATS trains in a spawned child, which re-imports the
# entry module and must not run the CLI a second time.
if __name__ == "__main__":
    sys.exit(main())
