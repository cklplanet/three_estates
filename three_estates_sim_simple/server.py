import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent / "backend_server"
sys.path.insert(0, str(BACKEND_ROOT))

from server import ThreeEstatesServer


if __name__ == "__main__":
    server = ThreeEstatesServer()
    server.server_loop()
