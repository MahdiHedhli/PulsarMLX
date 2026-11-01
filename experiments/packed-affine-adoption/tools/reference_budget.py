"""Bounded-reference accounting and watchdog; not a physical memory sandbox."""
import resource
import signal
import sys
import tracemalloc
LIMIT=256*1024*1024
def check():
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes=rss if sys.platform=='darwin' else rss*1024
    current,peak=tracemalloc.get_traced_memory()
    if peak>LIMIT or rss_bytes>LIMIT:raise MemoryError('reference observed memory exceeded 256 MiB; no acceptance')
    return {'working_data_budget':LIMIT,'traced_current_bytes':current,'traced_peak_bytes':peak,'process_peak_rss_bytes':rss_bytes,'deadline_seconds':900,'accounting':'fixed geometry/input bounds plus traced Python allocations and observed process peak; not an OS physical cap'}
def start():
    tracemalloc.start()
    def expired(_signum,_frame):raise TimeoutError('reference process exceeded 900 seconds')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,900)
    return check()
