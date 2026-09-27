"""Real child processes for crash recovery and OS lock tests."""
import importlib.util
import os
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location(
    "graph_storage_child", Path(__file__).resolve().parents[2] / "tools/graph_refresh/storage.py")
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
mode, root = sys.argv[1:3]
workspace = storage.Workspace(Path(root))

if mode == "recover":
    try:
        with workspace.locked():
            workspace.recover()
    except (OSError, ValueError) as exc:
        print(str(exc), flush=True)
        sys.exit(24)
elif mode == "try-lock":
    try:
        with workspace.locked():
            print("acquired", flush=True)
    except OSError:
        print("locked", flush=True)
        sys.exit(23)
elif mode == "hold":
    with workspace.locked():
        print("held", flush=True)
        sys.stdin.buffer.read(1)
elif mode == "crash":
    write = storage.tx.write
    count = 0
    stop = sys.argv[3]

    def crashing(path, data, permissions=0o644):
        global count
        write(path, data, permissions)
        path = Path(path)
        if workspace.work not in path.parents:
            count += 1
            if str(count) == stop:
                os._exit(77)
        elif stop == path.name:
            os._exit(77)

    with workspace.locked():
        expected = workspace.snapshot()
        storage.tx.write = crashing
        stage = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(root) / "stage"
        workspace.publish(stage, expected, lambda: None)
    raise AssertionError("requested crash point was never reached")
else:
    raise ValueError("unknown storage child mode")
