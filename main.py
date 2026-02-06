"""Entry point - launches client or server via CLI args.

Usage:
    python main.py                     # Launch client (connects to localhost)
    python main.py server              # Launch server on localhost:8765
    python main.py server 0.0.0.0 9000 # Launch server on custom host/port
    python main.py client host port    # Launch client connecting to custom host/port
"""

import sys
import asyncio


def run_server(host: str = "localhost", port: int = 8765):
    from server.server import main as server_main
    print(f"Starting Impetus server on {host}:{port}")
    asyncio.run(server_main(host, port))


def run_client(host: str = "localhost", port: int = 8765):
    from client.app import App
    app = App(server_host=host, server_port=port)
    app.run()


def main():
    args = sys.argv[1:]

    if not args or args[0] == "client":
        host = args[1] if len(args) > 1 else "localhost"
        port = int(args[2]) if len(args) > 2 else 8765
        run_client(host, port)
    elif args[0] == "server":
        host = args[1] if len(args) > 1 else "localhost"
        port = int(args[2]) if len(args) > 2 else 8765
        run_server(host, port)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
