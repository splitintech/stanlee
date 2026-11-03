"""Owned native subprocess supervisor. Parent pipe EOF terminates our worker tree."""
import ctypes
import os
import signal
import subprocess
import sys
import threading


def _windows_job(process):
    from ctypes import wintypes as w
    class Limits(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',w.DWORD),
                  ('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),('active',w.DWORD),
                  ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Limits),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                  ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];kernel.SetInformationJobObject.restype=w.BOOL
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];kernel.AssignProcessToJobObject.restype=w.BOOL
    kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
    job=kernel.CreateJobObjectW(None,None)
    if not job:raise OSError(ctypes.get_last_error(),'Could not create owned worker Job Object')
    info=Extended();info.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job,int(process._handle)):
        error=ctypes.get_last_error();kernel.CloseHandle(job);raise OSError(error,'Could not contain owned native process')
    close_lock=threading.Lock()
    closed=False
    def close():
        nonlocal closed
        with close_lock:
            if not closed:
                kernel.CloseHandle(job);closed=True
    return close


def main(arguments=None):
    command=list(sys.argv[1:] if arguments is None else arguments)
    if command[:1]==['--']:command=command[1:]
    if not command:return 2
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL)
    close_job=None
    try:
        if os.name=='nt':close_job=_windows_job(child)
        def watch_parent():
            # Export service holds this pipe open for the entire native lifetime.
            try:
                while os.read(sys.stdin.fileno(),4096):pass
            except OSError:pass
            if child.poll() is None:
                if os.name!='nt' and os.getpgrp()==os.getpid():
                    os.killpg(os.getpgrp(),signal.SIGKILL)
                elif close_job:close_job()
                else:child.kill()
        threading.Thread(target=watch_parent,daemon=True).start()
        return child.wait()
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=5)
        if close_job:close_job()


if __name__=='__main__':raise SystemExit(main())
