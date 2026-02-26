"""Entry point - launches client or server via CLI args.

Usage:
    python main.py                     # Launch client (connects to localhost)
    python main.py server              # Launch server on localhost:8765
    python main.py server 0.0.0.0 9000 # Launch server on custom host/port
    python main.py client host port    # Launch client connecting to custom host/port
"""

import sys
import asyncio
import pygame  # noqa: F401 — must be top-level so Pygbag pre-loads pygame-wasm


async def main():
    args = sys.argv[1:]

    if not args or args[0] == "client":
        host = args[1] if len(args) > 1 else "localhost"
        port = int(args[2]) if len(args) > 2 else 8765
        try:
            print("[main] importing App")
            from client.app import App
            print("[main] creating App")
            app = App(server_host=host, server_port=port)
            print("[main] starting run loop")
            await app.run()
            print("[main] run loop ended")
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print(tb)
            # In WASM, show error as a browser alert so it's always visible
            if sys.platform == "emscripten":
                try:
                    import js
                    js.alert("Impetus error:\n" + tb[-800:])
                except Exception:
                    pass
    elif args[0] == "server":
        from server.server import main as server_main
        host = args[1] if len(args) > 1 else "localhost"
        port = int(args[2]) if len(args) > 2 else 8765
        print(f"Starting Impetus server on {host}:{port}")
        await server_main(host, port)
    else:
        print(__doc__)
        sys.exit(1)


asyncio.run(main())
