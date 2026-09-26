"""Bounded, read-only access to active lesson files. No index or archive dependency."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

FILE_LIMIT = 1024 * 1024
TOTAL_LIMIT = 32 * FILE_LIMIT
PATH_LIMIT = 10000


@dataclass(frozen=True)
class Entry:
    source: str
    line: int
    title: str
    text: str


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400)


class Corpus:
    def __init__(self):
        self.entries = []
        self.issues = []
        self.bytes_read = 0
        self.paths_seen = 0

    def issue(self, path, reason):
        self.issues.append({"component": "lesson-recall", "source": str(path), "reason": reason})

    def read(self, path):
        """Reject links/special files before opening; verify the opened file too."""
        try:
            info = path.lstat()
            if linked(info) or not stat.S_ISREG(info.st_mode):
                self.issue(path, "not a regular, unlinked file")
                return None
            if info.st_size > FILE_LIMIT or self.bytes_read + info.st_size > TOTAL_LIMIT:
                self.issue(path, "memory read budget exceeded")
                return None
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            flags |= getattr(os, "O_BINARY", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or (info.st_dev, info.st_ino) != (
                        opened.st_dev, opened.st_ino):
                    self.issue(path, "source changed while opening")
                    return None
                data = stream.read(min(FILE_LIMIT, TOTAL_LIMIT - self.bytes_read) + 1)
                self.bytes_read += len(data)
                if len(data) > FILE_LIMIT or self.bytes_read > TOTAL_LIMIT:
                    self.issue(path, "memory read budget exceeded")
                    return None
                after = os.fstat(stream.fileno())
                if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    self.issue(path, "source changed while reading; retry")
                    return None
            return data.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            self.issue(path, "cannot read source: " + type(exc).__name__)
            return None

    def curated(self, directory):
        """Walk visible Markdown only, without following directory links."""
        try:
            info = directory.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            self.issue(directory, "cannot inspect store: " + type(exc).__name__)
            return
        if linked(info) or not stat.S_ISDIR(info.st_mode):
            self.issue(directory, "store is not an unlinked directory")
            return
        pending = [directory]
        while pending:
            current = pending.pop()
            try:
                with os.scandir(current) as children:
                    for child in children:
                        self.paths_seen += 1
                        if self.paths_seen > PATH_LIMIT:
                            self.issue(directory, "memory path budget exceeded")
                            return
                        if child.name.startswith(".") or child.name.casefold() == "index.md":
                            continue
                        path = Path(child.path)
                        info = child.stat(follow_symlinks=False)
                        if linked(info):
                            self.issue(path, "linked source skipped")
                        elif stat.S_ISDIR(info.st_mode):
                            pending.append(path)
                        elif path.suffix.casefold() == ".md":
                            text = self.read(path)
                            if text is not None:
                                self.add_curated(path, text)
            except OSError as exc:
                self.issue(current, "cannot enumerate store: " + type(exc).__name__)

    def add_curated(self, path, text):
        # Legacy consolidated stores may hold several lessons in one document.
        lines = text.splitlines()
        starts = [i for i, line in enumerate(lines) if re.match(r"^#{1,2}\s+", line)]
        if not starts or starts[0] != 0:
            starts.insert(0, 0)
        for start, end in zip(starts, starts[1:] + [len(lines)]):
            body = "\n".join(lines[start:end])
            if body.strip():
                title = lines[start].lstrip("# ") if lines[start].startswith("#") else path.stem
                self.entries.append(Entry(str(path), start + 1, title, body))

    def load(self, ledger, store):
        try:
            ledger.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            self.issue(ledger, "cannot inspect inbox: " + type(exc).__name__)
        else:
            text = self.read(ledger)
            if text is not None:
                for number, line in enumerate(text.splitlines(), 1):
                    if line.strip() and not line.lstrip().startswith("#"):
                        parts = line.split("|", 2)
                        title = parts[1].strip() if len(parts) == 3 else "Inbox observation"
                        self.entries.append(Entry(str(ledger), number, title, line))
        self.curated(store)
        return self
