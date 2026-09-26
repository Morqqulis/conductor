"""Acquire committed source as data; never run checkout hooks or fetched programs."""
import io
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time


OFFICIAL_URL = "https://github.com/Morqqulis/conductor.git"
_TIMEOUT_SECONDS = 60
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_REF = re.compile(r"main|[0-9a-fA-F]{40}|v[0-9]+\.[0-9]+\.[0-9]+"
                  r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
                  r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")
_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:[ .]|$)",
                     re.IGNORECASE)


def _failure(stage, cause):
    logging.getLogger(__name__).warning(
        "source acquisition failed", extra={"component": "updater.source", "stage": stage,
                                           "cause": cause})
    return ValueError(f"source {stage}: {cause}")


def _safe_name(name, spellings):
    parts = name.split("/")
    for index, part in enumerate(parts):
        if (part in ("", ".", "..") or part.casefold() == ".git" or
                part.endswith((".", " ")) or _DEVICE.match(part) or
                re.search(r'[\x00-\x1f\x7f\\:<>"|?*]', part)):
            raise _failure("inspect", "source contains an unsafe path")
        prefix = "/".join(parts[:index + 1])
        if spellings.setdefault(prefix.casefold(), prefix) != prefix:
            raise _failure("inspect", "source contains colliding paths")


def _stop(child):
    try:
        if os.name == "nt":
            killer = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe"
            subprocess.run([str(killer), "/PID", str(child.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(child.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        logging.getLogger(__name__).warning("source process-tree termination unconfirmed",
                                            extra={"component": "updater.source", "stage": "cancel"})
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def fetch(destination: Path, ref: str = "main", *, remote: str = OFFICIAL_URL) -> dict:
    """Return a plain source directory and the exact commit in a caller-owned empty directory."""
    if not isinstance(ref, str) or len(ref) > 128 or _REF.fullmatch(ref) is None:
        raise _failure("ref", "expected main, a version tag, or a full commit identifier")
    if (not isinstance(remote, str) or "\0" in remote or
            (remote != OFFICIAL_URL and not Path(remote).is_absolute())):
        raise _failure("remote", "expected the official URL or an absolute local fixture path")
    stage = "prepare"
    try:
        destination = Path(destination).absolute()
        for part in (destination, *destination.parents):
            metadata = part.lstat()
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
                raise _failure(stage, "linked destination is not allowed")
        destination = destination.resolve()
        if not destination.is_dir() or any(destination.iterdir()):
            raise _failure(stage, "destination must be an existing empty directory")
        git = shutil.which("git")
        if git is None:
            raise _failure(stage, "Git executable is unavailable")
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith("GIT_") and key not in ("BASH_ENV", "ENV")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
        base = [git, "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false",
                "-c", "core.attributesFile=" + os.devnull, "-c", "credential.helper=",
                "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                "-c", "protocol.file.allow=always", "-c", "http.followRedirects=false"]
        deadline = time.monotonic() + _TIMEOUT_SECONDS

        def run(label, *args, data=None):
            nonlocal stage
            stage = label
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _failure(stage, "time limit exceeded")
            with tempfile.TemporaryFile(dir=destination) as output:
                child = subprocess.Popen(
                    [*base, *map(str, args)], cwd=destination, env=env,
                    stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.DEVNULL, start_new_session=os.name != "nt",
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
                    if os.name == "nt" else 0)
                try:
                    child.communicate(data, timeout=remaining)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    _stop(child)
                    raise _failure(stage, "time limit exceeded or operation interrupted") from None
                if child.returncode:
                    raise _failure(stage, f"Git exited with status {child.returncode}")
                if output.tell() > _MAX_SOURCE_BYTES + 4 * 1024 * 1024:
                    raise _failure(stage, "Git output exceeds the size limit")
                output.seek(0)
                return output.read()

        repository = destination / "repository.git"
        run("initialize", "init", "--bare", "--template=", "--", repository)
        wanted = "refs/heads/main" if ref == "main" else (
            "refs/tags/" + ref if ref.startswith("v") else ref)
        run("fetch", "--git-dir", repository, "fetch", "--no-tags", "--depth=1", "--", remote, wanted)
        commit = run("resolve", "--git-dir", repository, "rev-parse", "--verify",
                     "FETCH_HEAD^{commit}").decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise _failure("resolve", "Git did not return a full commit identifier")
        tree = run("inspect", "--git-dir", repository, "ls-tree", "-rlz", "--full-tree", commit)
        entries, spellings, names = [], {}, set()
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            metadata, name = entry.split(b"\t", 1)
            mode, kind, oid, size = metadata.split()
            if mode not in (b"100644", b"100755") or kind != b"blob":
                raise _failure("inspect", "source contains a non-regular file")
            name = name.decode("utf-8")
            _safe_name(name, spellings)
            if name in names:
                raise _failure("inspect", "source contains duplicate paths")
            names.add(name)
            entries.append((name, mode, oid, int(size)))
        if sum(entry[3] for entry in entries) > _MAX_SOURCE_BYTES:
            raise _failure("inspect", "source exceeds the size limit")
        objects = io.BytesIO(run("read", "--git-dir", repository, "cat-file", "--batch",
                                data=b"".join(entry[2] + b"\n" for entry in entries)))
        stage = "extract"
        source = destination / "source"
        source.mkdir()
        for name, mode, oid, size in entries:
            if objects.readline() != oid + b" blob " + str(size).encode("ascii") + b"\n":
                raise _failure(stage, "unexpected Git object header")
            content = objects.read(size)
            if len(content) != size or objects.read(1) != b"\n":
                raise _failure(stage, "incomplete Git object")
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(content)
            target.chmod(int(mode, 8) & 0o777)
        if objects.read(1):
            raise _failure(stage, "unexpected trailing Git output")
        return {"source": source, "commit": commit, "ref": ref, "remote": remote}
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise _failure(stage, "filesystem or process operation failed") from None
