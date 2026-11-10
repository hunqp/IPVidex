"""Console worker executable, launched hidden through QProcess by IPVidex."""

import importlib
import json
import sys
from core.Runtime import CHECK_RUNTIME, WORKER_MODULES, configureVlc


def checkRuntime():
    import vlc

    instance = vlc.Instance("--quiet")
    print(json.dumps({"vlc": vlc.libvlc_get_version().decode(), "available": bool(instance)}))
    if not instance:
        return 1
    instance.release()
    return 0


def main():
    configureVlc()
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == CHECK_RUNTIME:
        return checkRuntime()
    if command not in WORKER_MODULES:
        return 2
    return importlib.import_module(command).main() or 0


if __name__ == "__main__":
    sys.exit(main())
