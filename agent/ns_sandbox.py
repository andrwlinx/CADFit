"""
Sandbox for agent-written code where bubblewrap cannot rebind the root (ORCD
GPU nodes inside Apptainer: "Can't bind mount /oldroot/ on /newroot/").

Run as   unshare -rnm python ns_sandbox.py <workdir> -- <argv...>
In the new user + mount + network namespace it remounts every mount outside
/proc, /sys and /dev read-only (and refuses to run if one stays writable), puts
empty tmpfs on /tmp, /var/tmp and /dev/shm, binds <workdir> back read-write,
then execs argv with all capabilities dropped and no_new_privs set, so the
code cannot undo the mounts. No network (fresh netns), writes only to workdir.
"""
import os
import subprocess
import sys

SKIP = ('/proc', '/sys', '/dev')


def mount(*args):
    subprocess.run(['mount', *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    sep = sys.argv.index('--')
    work, argv = os.path.realpath(sys.argv[1]), sys.argv[sep + 1:]
    points = []
    for line in open('/proc/self/mountinfo'):
        mp = line.split()[4].replace('\\040', ' ')
        if not any(mp == s or mp.startswith(s + '/') for s in SKIP):
            points.append(mp)
    for mp in sorted(set(points), key=len):
        try:
            mount('-o', 'remount,bind,ro', mp)
        except subprocess.CalledProcessError:
            pass  # already read-only and locked, or not remountable: it stays as it was
    # The workdir may lie under a path about to get an empty tmpfs (e.g. /tmp/...):
    # keep a handle on it, recreate the path afterwards, bind from the handle.
    fd = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    tmp = [t for t in ('/tmp', '/var/tmp', '/dev/shm') if os.path.isdir(t)]
    for t in tmp:
        mount('-t', 'tmpfs', 'none', t)
    os.makedirs(work, exist_ok=True)
    # -c: mount(8) must not canonicalize the source (that resolves to the new, empty path).
    mount('-c', '--bind', f'/proc/{os.getpid()}/fd/{fd}', work)
    mount('-o', 'remount,bind,rw', work)
    os.close(fd)
    # Fail closed: every other mount must now be read-only.
    writable = []
    for line in open('/proc/self/mountinfo'):
        f = line.split()
        mp, opts = f[4].replace('\\040', ' '), f[5].split(',')
        if mp == work or mp in tmp or any(mp == s or mp.startswith(s + '/') for s in SKIP):
            continue
        if 'ro' not in opts:
            writable.append(mp)
    if writable:
        sys.exit(f'ns_sandbox: could not make read-only: {writable[:5]}')
    os.chdir(work)
    # Drop every capability (namespace root could otherwise remount rw) and forbid regaining them.
    os.execvp('setpriv', ['setpriv', '--no-new-privs', '--bounding-set=-all', '--inh-caps=-all',
                          '--ambient-caps=-all', '--', *argv])


if __name__ == '__main__':
    main()
