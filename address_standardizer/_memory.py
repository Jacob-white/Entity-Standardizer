"""Process memory helpers shared by tests and benchmarks (stdlib `resource` on POSIX, psutil elsewhere)."""

import sys

try:
    import resource
except ImportError:  # Windows has no `resource` module
    resource = None


def peak_rss_kb() -> float:
    """Peak resident set size of this process in KB."""
    if resource is not None:
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss is KB on Linux but bytes on macOS.
        return maxrss / 1024.0 if sys.platform == "darwin" else float(maxrss)
    import psutil

    info = psutil.Process().memory_info()
    return getattr(info, "peak_wset", info.rss) / 1024.0


def current_rss_mb() -> float:
    """Current resident set size of this process in MB."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except (OSError, IndexError, ValueError):
        pass
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024.0 * 1024.0)
    except ImportError:
        return peak_rss_kb() / 1024.0
