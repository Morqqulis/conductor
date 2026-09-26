"""Own one process, stream bytes to disk, and never infer success from output text."""
import hashlib
import os
from pathlib import Path
import subprocess
import time

from .contract import ProcessResult
from .pipe_io import read_ready


def capture_process(argv: tuple[str, ...], cwd: Path, env: dict[str, str], directory: Path,
                    timeout_seconds: float, limit_bytes: int = 67108864) -> ProcessResult:
    started = time.monotonic()
    deadline = started + timeout_seconds
    files, counts = {}, {"stdout": 0, "stderr": 0}
    hashes = {name: hashlib.sha256() for name in counts}
    errors, open_pipes = [], {}
    child = None
    exit_code = None
    interrupted = False

    def error(code):
        if code not in errors:
            errors.append(code)

    def cancel():
        if child is not None and child.poll() is None:
            try:
                child.kill()
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                error("termination_unconfirmed")

    try:
        for name in counts:
            files[name] = os.open(directory / (name + ".bin"),
                                  os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                                  0o600)
        child = subprocess.Popen(argv, cwd=cwd, env=env, shell=False,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, bufsize=0)
        open_pipes = {"stdout": child.stdout, "stderr": child.stderr}
        drain_deadline = None
        while open_pipes or child.poll() is None:
            now = time.monotonic()
            if now >= deadline and child.poll() is None:
                interrupted = True
                error("timeout")
                cancel()
            if child.poll() is not None and drain_deadline is None:
                drain_deadline = time.monotonic() + 2
            if drain_deadline is not None and now >= drain_deadline and open_pipes:
                error("open_descendant_pipe")
                break
            progress = False
            for name, stream in list(open_pipes.items()):
                try:
                    data = read_ready(stream, 65536)
                except OSError:
                    error("pipe_read_failed")
                    data = b""
                if data is None:
                    continue
                progress = True
                if not data:
                    stream.close()
                    del open_pipes[name]
                    continue
                remaining = max(0, limit_bytes - sum(counts.values()))
                if len(data) >= remaining:
                    error("output_limit")
                kept = data[:remaining]
                if "output_write_failed" not in errors:
                    try:
                        while kept:
                            written = os.write(files[name], kept)
                            if written <= 0:
                                raise OSError("No output write progress")
                            hashes[name].update(kept[:written])
                            counts[name] += written
                            kept = kept[written:]
                    except OSError:
                        error("output_write_failed")
            if not progress:
                time.sleep(0.01)
        exit_code = child.poll()
    except KeyboardInterrupt:
        interrupted = True
        error("interrupt")
        cancel()
        if child is not None:
            exit_code = child.poll()
    except (OSError, ValueError):
        error("launch_or_capture_failed")
        cancel()
        if child is not None:
            exit_code = child.poll()
    finally:
        for stream in open_pipes.values():
            stream.close()
        for descriptor in files.values():
            try:
                os.fsync(descriptor)
            except OSError:
                error("output_sync_failed")
            finally:
                os.close(descriptor)
    output_complete = not errors
    if interrupted:
        execution = "interrupted"
    elif errors:
        execution = "recording_error"
    else:
        execution = "succeeded" if exit_code == 0 else "failed"
    return ProcessResult(execution, exit_code, int((time.monotonic() - started) * 1000),
                         counts["stdout"], counts["stderr"], hashes["stdout"].hexdigest(),
                         hashes["stderr"].hexdigest(), output_complete, errors)
