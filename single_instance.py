import ctypes
import os
import sys
from pathlib import Path

MUTEX_NAME = "TypeBuffer_SingleInstance_Mutex"


class SingleInstance:
    """
    Ensures that only one instance of the application runs at any time.
    Uses a Windows Named Mutex on Windows, and fcntl lockfile on Linux/macOS.
    """

    def __init__(self, name: str = MUTEX_NAME):
        self.name = name
        self.mutex = None
        self.lock_file = None
        self._already_running = False
        self.acquire()

    def acquire(self):
        if sys.platform == "win32":
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.windll.kernel32
            # CreateMutexW(security_attributes, initial_owner, name)
            self.mutex = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                self._already_running = True
                kernel32.CloseHandle(self.mutex)
                self.mutex = None
        else:
            lock_dir = Path(os.environ.get("XDG_RUNTIME_DIR") or Path.home() / ".cache") / "TypeBuffer"
            lock_dir.mkdir(parents=True, exist_ok=True)
            self.lock_path = lock_dir / f"{self.name}.lock"
            try:
                import fcntl
                self.lock_file = open(self.lock_path, "w")
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError, ImportError):
                self._already_running = True

    def is_running(self) -> bool:
        return self._already_running

    def release(self):
        if sys.platform == "win32" and self.mutex:
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex)
            except Exception:
                pass
            self.mutex = None
        elif self.lock_file:
            try:
                self.lock_file.close()
                if hasattr(self, "lock_path") and self.lock_path.exists():
                    self.lock_path.unlink()
            except Exception:
                pass
            self.lock_file = None
