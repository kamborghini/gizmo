import sys

# BEFORE .pipeline, which imports numpy and pandas, and long before LightGBM:
# each maths library reads its thread variable once, when it loads. Setting
# them afterwards has no effect at all.
from .cpu import apply_thread_limits

apply_thread_limits()

from .pipeline import main

# The guard matters: N-BEATS trains in a spawned child, which re-imports the
# entry module and must not run the CLI a second time.
if __name__ == "__main__":
    sys.exit(main())
