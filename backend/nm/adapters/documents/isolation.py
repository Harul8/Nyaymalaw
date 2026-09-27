"""Hard process memory bounds for untrusted local document parsers.

An unavailable sandbox is a capability failure, not permission to parse inside
the web process. The parent separately enforces a deadline and terminates work.
"""
from __future__ import annotations

import os


class SandboxUnavailable(RuntimeError):
    pass


def memory_limit(maximum: int):
    """Return an open resource handle, or refuse before parsing any input."""
    if os.name != "nt":
        try:
            import resource
        except ImportError as exc:
            raise SandboxUnavailable("hard parser memory limits are unavailable") from exc
        try:
            resource.setrlimit(resource.RLIMIT_AS, (maximum, maximum))
        except (OSError, ValueError) as exc:
            raise SandboxUnavailable("the hard parser memory limit could not be set") from exc
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimit(ctypes.Structure):
        _fields_ = [("per_process_time", ctypes.c_longlong),
                    ("per_job_time", ctypes.c_longlong), ("flags", wintypes.DWORD),
                    ("minimum_working_set", ctypes.c_size_t),
                    ("maximum_working_set", ctypes.c_size_t),
                    ("active_process_limit", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "read_operations", "write_operations", "other_operations",
            "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [("basic", BasicLimit), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t),
                    ("peak_job_memory", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise SandboxUnavailable("the parser memory job could not be created")
    limit = ExtendedLimit()
    limit.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY, not a working-set hint.
    limit.process_memory = maximum
    if not (kernel.SetInformationJobObject(handle, 9, ctypes.byref(limit),
                                            ctypes.sizeof(limit))
            and kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())):
        kernel.CloseHandle(handle)
        raise SandboxUnavailable("the parser could not enter its hard memory job")
    # Keep the job alive until this child exits. Closing it would remove the
    # containment that was just established; the OS closes the handle on exit.
    return handle
