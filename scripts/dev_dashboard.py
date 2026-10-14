"""Start the local API and existing Next.js dashboard; Ctrl-C stops both."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    for port in (8000, 3000):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Port {port} is already in use. Stop the existing server before starting this launcher.')
    processes = []
    def stop(*args):
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'aster.api:app', '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT, start_new_session=True))
        processes.append(subprocess.Popen(['npm', 'run', 'dev', '--', '--hostname', '127.0.0.1', '--port', '3000'], cwd=ROOT/'apps/web', start_new_session=True))
        print('Aster dashboard: http://127.0.0.1:3000/dashboard\nAPI: http://127.0.0.1:8000/docs\nCtrl-C stops both services.', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(.5)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == '__main__':
    main()
