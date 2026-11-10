"""The outgoing-data log: one file a day, kept a year (plan AN.48, owner decision D169, 10 Nov 2026).

Every reach of NM's to a destination - an outside service or its own stores - leaves one content-free line, the gate's audit line
(nm.shared.egress_contracts.audit_line), after its UTC time. The lines of each UTC day go to a file of that day,
egress-YYYY-MM-DD.log, in the log's folder (the application's audit root).

SWEPT AT EACH START AND ONCE A DAY AFTER (keep): a day over COMPRESS_AFTER_DAYS (90) days old is compressed - gzip, read back
whole and compared before the plain file goes - and a day over the kept period is deleted. The kept period is KEEP_DAYS (365),
the year the Digital Personal Data Protection Rules 2025 (rule 6(1)(e)) ask logs of personal-data processing to be kept;
NM_EGRESS_LOG_KEEP_DAYS may set another, never under FLOOR_DAYS (180), the period the CERT-In directions of 28 April 2022 ask
logs to be kept for. The single file kept until now (egress.log) is taken in whole as the file of the last day it holds - by the
first line a process writes, and by every sweep.

TWO PROCESSES AT ONCE (48f4: a web server and its step worker): each line is one write at the end of its day's file, whole,
whichever process writes it - O_APPEND on POSIX; on Windows a handle that may only append, which the system writes at the end as
one piece. One sweep works at a time, under a lock file only one can make; a sweep that finds the lock held passes on, its work
being done by the other. (On Windows, without the lock, two sweeps at once were measured renaming one file twice and refusing
each other's replacement of one compressed day.)
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KEEP_DAYS = 365
FLOOR_DAYS = 180
COMPRESS_AFTER_DAYS = 90
SINGLE_FILE = 'egress.log'
LOCK = 'egress-sweep.lock'
#: A lock older than this, in seconds, was left by a sweep that stopped: it is cleared, and the next sweep works.
LEFT_FOR = 3600

_DAY = re.compile(r'egress-(\d{4}-\d{2}-\d{2})\.log(\.gz)?')
_PART = re.compile(r'egress-\d{4}-\d{2}-\d{2}\.log\.gz\.\d+-[0-9a-f]+\.part')
_CLAIM = re.compile(r'egress\.log\.\d+-[0-9a-f]+\.taking')
_STAMP = re.compile(rb'\d{4}-\d{2}-\d{2}')
_BLOCK = 1 << 20
_log = logging.getLogger('nm.egress_log')


def keep_days_from(setting) -> int:
    """How many days the log is kept, from NM_EGRESS_LOG_KEEP_DAYS: a whole number of days, never under FLOOR_DAYS; unset or
    anything else, KEEP_DAYS."""
    try:
        days = int(str(setting).strip())
    except (TypeError, ValueError):
        return KEEP_DAYS
    return max(days, FLOOR_DAYS)


class EgressLog:
    """The outgoing-data log in its folder (see the module's words)."""

    def __init__(self, folder, *, keep_days: int = KEEP_DAYS):
        self.folder = Path(folder)
        self.keep_days = max(int(keep_days), FLOOR_DAYS)
        self._first = threading.Lock()
        self._taken_in = False

    def day_file(self, day: date) -> Path:
        return self.folder / f'egress-{day.isoformat()}.log'

    def write(self, line: str, now: datetime | None = None) -> None:
        """One line, after its UTC time, at the end of its day's file. The first line this log writes takes in the single file
        of before first, so that the day it ends on keeps it whole."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.folder.mkdir(parents=True, exist_ok=True)
        if not self._taken_in:
            with self._first:
                if not self._taken_in:
                    self._taken_in = True
                    try:
                        self.take_in_the_single_file()
                    except OSError as exc:  # the line is still written; a sweep takes the file in
                        _log.warning('The single outgoing-data log could not be taken in yet (%s).', type(exc).__name__)
        _append(self.day_file(now.date()), (now.isoformat(timespec='seconds') + '\t' + line + '\n').encode('utf8'))

    def take_in_the_single_file(self) -> bool:
        """The single file kept until now (egress.log), taken in whole as the file of the last day it holds, by this sweep alone.
        True when this call took it in."""
        if not (self.folder / SINGLE_FILE).exists():
            return False
        with _alone(self.folder / LOCK) as alone:
            return alone and self._take_in(self.folder / SINGLE_FILE)

    def sweep(self, today: date | None = None) -> dict:
        """Take in the single file of before, compress each day over COMPRESS_AFTER_DAYS old, delete each day over the kept
        period, and finish or clear what a stopped sweep left half made. Returns how many of each it did - nothing, where another
        sweep holds the lock and does this work."""
        today = today or datetime.now(timezone.utc).date()
        done = {'taken_in': 0, 'compressed': 0, 'deleted': 0}
        if not self.folder.is_dir():
            return done
        with _alone(self.folder / LOCK) as alone:
            if not alone:
                return done
            done['taken_in'] = int(self._take_in(self.folder / SINGLE_FILE))
            for path in sorted(self.folder.glob('egress*')):
                day = _DAY.fullmatch(path.name)
                if day is None:
                    self._finish_half_made(path)
                    continue
                try:
                    age = (today - date.fromisoformat(day[1])).days
                except ValueError:
                    continue
                if age > self.keep_days:
                    done['deleted'] += _remove(path)
                elif age > COMPRESS_AFTER_DAYS and day[2] is None:
                    done['compressed'] += _compress(path)
        return done

    def _take_in(self, source: Path) -> bool:
        """(Holding the lock.) `source` claimed under a name of this sweep's own - so that a process of the earlier code, still
        writing the single file by its name, starts a new one rather than adding to what is being taken in - and then renamed to
        its last day's name or, where that day's file has begun already, its lines added to the end of it whole (each line
        carries its own time)."""
        claimed = self.folder / f'{SINGLE_FILE}.{os.getpid()}-{secrets.token_hex(4)}.taking'
        try:
            os.rename(source, claimed)
        except FileNotFoundError:
            return False
        except OSError as exc:  # held open this moment by a process of the earlier code: a later sweep takes it in
            _log.warning('The single outgoing-data log could not be taken in yet (%s).', type(exc).__name__)
            return False
        try:
            target = self.day_file(_last_day(claimed))
            try:
                _rename_unless_there(claimed, target)
            except FileExistsError:
                _append_whole_lines(claimed, target)
                claimed.unlink()
        except OSError as exc:  # left claimed: the next sweep takes it in
            _log.warning('The single outgoing-data log was not taken in whole yet (%s).', type(exc).__name__)
            return False
        return True

    def _finish_half_made(self, path: Path) -> None:
        """(Holding the lock, so no other sweep is at work.) A compressed copy a stopped sweep left is deleted - its plain day file
        is still there, for this or the next compression - and a claimed single file it left is taken in."""
        if _PART.fullmatch(path.name):
            _remove(path)
        elif _CLAIM.fullmatch(path.name):
            self._take_in(path)


def keep(log: EgressLog, *, stop=None, clock=None) -> threading.Thread:
    """Sweep the log now and once a day after - a minute after each UTC midnight - in a daemon thread of its own, until `stop`
    (a threading.Event) is set. clock: the time now, aware (tests stand one in)."""
    stop = stop if stop is not None else threading.Event()
    clock = clock or (lambda: datetime.now(timezone.utc))

    def run():
        while True:
            try:
                log.sweep(clock().date())
            except OSError as exc:  # the log is still written; the next sweep tries again
                _log.warning('The outgoing-data log could not be swept (%s).', type(exc).__name__)
            except Exception:  # noqa: BLE001 -- a programming error, reported as one; the server goes on
                _log.exception('Sweeping the outgoing-data log failed with a programming error.')
            now = clock()
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), timezone.utc)
            if stop.wait((midnight - now).total_seconds() + 60):
                return

    thread = threading.Thread(target=run, name='egress-log-sweep', daemon=True)
    thread.start()
    return thread


@contextmanager
def _alone(lock: Path):
    """True while this sweep alone holds the folder's lock - a file made only where none is - and False where another holds it.
    A lock left LEFT_FOR or more ago by a sweep that stopped is cleared, for the next sweep to take."""
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640))
    except (FileExistsError, PermissionError):  # held, or (Windows) being let go by its sweep this moment
        try:
            if time.time() - lock.stat().st_mtime >= LEFT_FOR:
                lock.unlink()
        except OSError:
            pass
        yield False
        return
    try:
        yield True
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _append(path: Path, data: bytes) -> None:
    """`data` written at the end of `path` as one piece, whichever process writes."""
    fd = _open_to_append(path)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


if os.name == 'nt':
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                             wintypes.DWORD, wintypes.HANDLE)
    _CreateFileW.restype = wintypes.HANDLE
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = (wintypes.HANDLE,)
    # FILE_APPEND_DATA without FILE_WRITE_DATA: every write goes to the end of the file, as one piece. Shared for reading,
    # writing and deleting, so that the other process, a reader and the sweep are never refused.
    _APPEND_ONLY, _SHARE_ALL, _OPEN_ALWAYS, _NORMAL = 0x0004 | 0x00100000, 0x7, 4, 0x80
    _INVALID = ctypes.c_void_p(-1).value

    def _open_to_append(path: Path) -> int:
        handle = _CreateFileW(str(path), _APPEND_ONLY, _SHARE_ALL, None, _OPEN_ALWAYS, _NORMAL, None)
        if handle is None or handle == _INVALID:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return msvcrt.open_osfhandle(handle, 0)
        except OSError:
            _CloseHandle(handle)
            raise
else:
    def _open_to_append(path: Path) -> int:
        return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)


def _last_day(path: Path) -> date:
    """The UTC day of the last line a log file holds (each line begins with its time), or, where none says, of its last change."""
    with path.open('rb') as source:
        source.seek(0, os.SEEK_END)
        source.seek(max(0, source.tell() - 65536))
        tail = source.read()
    for line in reversed(tail.splitlines()):
        if _STAMP.fullmatch(line[:10]):
            try:
                return date.fromisoformat(line[:10].decode('ascii'))
            except ValueError:
                continue
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date()


def _rename_unless_there(source: Path, target: Path) -> None:
    """`source` renamed to `target`, or FileExistsError where `target` is there already - never replacing it."""
    if os.name == 'nt':
        os.rename(source, target)  # Windows refuses a name that is there
        return
    try:
        os.link(source, target)  # so does a link, where POSIX rename would replace
    except FileExistsError:
        raise
    except OSError:  # a file system without links
        if target.exists():
            raise FileExistsError(str(target)) from None
        os.rename(source, target)
        return
    os.unlink(source)


def _append_whole_lines(source: Path, target: Path) -> None:
    """Every line of `source` added at the end of `target`, a block of whole lines at a time: a line a process writes meanwhile
    lands between two of them, never inside one."""
    carry = b''
    with source.open('rb') as handle:
        for block in iter(lambda: handle.read(_BLOCK), b''):
            block = carry + block
            cut = block.rfind(b'\n') + 1
            if cut:
                _append(target, block[:cut])
            carry = block[cut:]
    if carry:
        _append(target, carry + b'\n')


def _compress(path: Path) -> int:
    """(Holding the lock.) A day's plain file compressed beside it, read back whole and compared, and only then the plain file
    deleted. 1 when compressed; 0 when the copy could not be made and checked - the plain file then stays for the next sweep."""
    final = path.with_name(path.name + '.gz')
    part = path.with_name(f'{final.name}.{os.getpid()}-{secrets.token_hex(4)}.part')
    try:
        plain, size = hashlib.sha256(), 0
        with path.open('rb') as source, gzip.open(part, 'wb', compresslevel=6) as sink:
            for block in iter(lambda: source.read(_BLOCK), b''):
                plain.update(block)
                size += len(block)
                sink.write(block)
        if _read_back(part) != plain.digest():
            raise OSError('the compressed copy did not read back as the day it was made from')
        os.replace(part, final)
        if path.stat().st_size != size:  # written to meanwhile: it stays, and the next sweep compresses it again
            return 0
        path.unlink()
        return 1
    except OSError as exc:
        _log.warning('A day of the outgoing-data log could not be compressed (%s); it stays as it is.', type(exc).__name__)
        return 0
    finally:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass


def _read_back(part: Path) -> bytes:
    """What a compressed copy holds, as the digest of its bytes read back whole."""
    digest = hashlib.sha256()
    with gzip.open(part, 'rb') as check:
        for block in iter(lambda: check.read(_BLOCK), b''):
            digest.update(block)
    return digest.digest()


def _remove(path: Path) -> int:
    try:
        path.unlink()
        return 1
    except FileNotFoundError:
        return 0
    except OSError as exc:
        _log.warning('A file of the outgoing-data log could not be deleted (%s).', type(exc).__name__)
        return 0
