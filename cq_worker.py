#!/usr/bin/env python3
"""
Persistent CadQuery script executor.

Stock `execute_cadquery_script` launches a fresh interpreter per candidate, and
~1.4 s of each ~1.5 s call is `import cadquery` (OCP). This keeps one
interpreter per calling process alive and runs each script in it with exec(),
in a fresh namespace, so the generated scripts and their STL output are
unchanged. The script still writes its own STL via cq.exporters.export.

Protocol: the parent owns one end of a socketpair; the child gets the other as
argv[1]. Requests are {'script': str}; replies are {'ok': bool, 'err': str}.
The child points fds 1/2 at /dev/null so OCP's C++ output cannot interleave
with anything.

Timeouts: the parent polls for the reply; if it does not arrive in time the
whole child process group is killed and a new child is started on next use,
which matches the stock subprocess timeout semantics (return False).

Enabled by CADFIT_CQ_WORKER=1 (run_pipeline.py --persistent-cq).
"""
import os
import signal
import socket
import subprocess
import sys
import traceback

_RECYCLE_AFTER = 200   # restart the child after this many scripts to bound memory growth


def enabled():
    return os.environ.get('CADFIT_CQ_WORKER') == '1'


def _serve(fd):
    from multiprocessing.connection import Connection
    conn = Connection(fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    import cadquery  # noqa: F401  (the whole point: import once)
    while True:
        try:
            req = conn.recv()
        except EOFError:
            return
        try:
            code = compile(req['script'], req.get('path') or '<cadquery-script>', 'exec')
            exec(code, {'__name__': '__main__', '__file__': req.get('path')})
            conn.send({'ok': True, 'err': ''})
        except SystemExit as e:
            conn.send({'ok': e.code in (0, None), 'err': f'SystemExit({e.code})'})
        except BaseException:
            conn.send({'ok': False, 'err': traceback.format_exc(limit=5)})


class _Client:
    def __init__(self):
        self.proc = None
        self.conn = None
        self.owner = None
        self.count = 0

    def _start(self):
        from multiprocessing.connection import Connection
        parent, child = socket.socketpair()
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), str(child.fileno())],
                                     pass_fds=(child.fileno(),), stdin=subprocess.DEVNULL,
                                     start_new_session=True)
        child.close()
        self.conn = Connection(os.dup(parent.fileno()))
        parent.close()
        self.owner = os.getpid()
        self.count = 0

    def kill(self):
        if self.proc is not None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.proc = self.conn = None

    def run(self, script, path=None, timeout=60.0):
        """Returns (ok, err). Raises subprocess.TimeoutExpired on timeout, like stock."""
        # A forked pool worker inherits the parent's client object; never share a child.
        if self.proc is not None and (self.owner != os.getpid() or self.proc.poll() is not None
                                      or self.count >= _RECYCLE_AFTER):
            if self.owner == os.getpid():
                self.kill()
            else:
                self.proc = self.conn = None
        if self.proc is None:
            self._start()
        self.count += 1
        try:
            self.conn.send({'script': script, 'path': path})
            if not self.conn.poll(timeout):
                self.kill()
                raise subprocess.TimeoutExpired(cmd='cq_worker', timeout=timeout)
            rep = self.conn.recv()
        except subprocess.TimeoutExpired:
            raise
        except (EOFError, OSError, BrokenPipeError):
            # Child died mid-script (segfault in OCP): same as a failed subprocess.
            self.kill()
            return False, 'cq_worker died'
        except BaseException:
            # e.g. the caller's SIGALRM watchdog fired while we waited: the child
            # is mid-script, so it cannot be reused.
            self.kill()
            raise
        return rep['ok'], rep['err']


_client = _Client()


def run_script(script, path=None, timeout=60.0):
    return _client.run(script, path, timeout)


if __name__ == '__main__':
    _serve(int(sys.argv[1]))
