"""
Sandbox for agent-written code where bubblewrap cannot rebind the root (ORCD
GPU nodes inside Apptainer: "Can't bind mount /oldroot/ on /newroot/").

Run as   unshare -rnm python ns_sandbox.py <workdir> -- <argv...>
In the new user + mount + network namespace it remounts every mount read-only,
puts empty tmpfs on /tmp, /var/tmp and /dev/shm, binds <workdir> back
read-write, then execs argv. No network (fresh netns), writes only to workdir.
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
    for t in ('/tmp', '/var/tmp', '/dev/shm'):
        if os.path.isdir(t):
            mount('-t', 'tmpfs', 'none', t)
    mount('--bind', work, work)
    mount('-o', 'remount,bind,rw', work)
    os.chdir(work)
    os.execvp(argv[0], argv)


if __name__ == '__main__':
    main()
