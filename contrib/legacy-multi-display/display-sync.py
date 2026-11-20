#!/usr/bin/python3
"""Confirm a guest display switch before the host forwards tablet coordinates."""

import argparse
import os
from pathlib import Path
import re
import select
import socket
import subprocess
import time


class Guest:
    def __init__(self, ssh):
        self.ssh = ssh
        self.process = None
        self.started = 0.0
        self.ready = False
        self.pending = bytearray()

    def close(self):
        if self.process is not None:
            self.process.kill()
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None
        self.pending.clear()
        self.ready = False

    def read_line(self, deadline):
        while b'\n' not in self.pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select(
                [self.process.stdout], [], [], remaining
            )[0]:
                raise TimeoutError('guest display acknowledgement timed out')
            data = os.read(self.process.stdout.fileno(), 4096)
            if not data:
                raise EOFError('guest display connection closed')
            self.pending.extend(data)
        line, _, remainder = self.pending.partition(b'\n')
        self.pending = remainder
        return line

    def select_display(self, request):
        if self.process is not None and self.process.poll() is not None:
            self.close()
        if self.process is None:
            self.started = time.monotonic()
            self.process = subprocess.Popen(
                self.ssh,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0,
            )
            return False
        # Keep SDL responsive in firmware and while SSH is warming up.
        if not self.ready:
            try:
                self.ready = self.read_line(time.monotonic() + .001) == b'READY'
            except TimeoutError:
                if time.monotonic() - self.started > 2:
                    self.close()
                return False
            if not self.ready:
                self.close()
                return False
        # Let prior USB tablet reports drain before the guest changes screens.
        time.sleep(.014)
        self.process.stdin.write(request)
        response = self.read_line(time.monotonic() + .045)
        port = request.split()[0]
        return response.startswith(b'PORT ' + port + b' STATUS 0 AT ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guest', required=True, help='SSH destination or configuration alias')
    parser.add_argument('--port', type=int, help='SSH port, overriding the SSH configuration')
    parser.add_argument('--host-key-alias', help='Override the name looked up in known_hosts')
    parser.add_argument('--socket', required=True, type=Path)
    args = parser.parse_args()
    ssh = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'ConnectTimeout=2', '-o', 'ServerAliveInterval=5',
           '-o', 'ServerAliveCountMax=2']
    if args.port is not None:
        ssh += ['-p', str(args.port)]
    if args.host_key_alias:
        ssh += ['-o', f'HostKeyAlias={args.host_key_alias}']
    ssh += ['--', args.guest,
            'exec "$HOME/Library/Application Support/Reims/reims-display-focus"']
    guest = Guest(ssh)
    os.umask(0o077)
    path = args.socket
    path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        server.listen(1)
        try:
            while True:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(.05)
                    try:
                        with connection.makefile('rb') as stream:
                            request = stream.readline(64)
                        if not re.fullmatch(rb'[0-7] [01]\.\d{6} [01]\.\d{6}\n', request):
                            continue
                        ok = guest.select_display(request)
                        try:
                            connection.sendall(b'1' if ok else b'0')
                        except BrokenPipeError:
                            pass
                    except (OSError, EOFError):
                        guest.close()
        finally:
            guest.close()
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
