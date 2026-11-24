"""Stamp js/buildinfo.js with the build id '<git short sha>-<YYYYMMDD>' (TASK-190).

Usage: python3 tools/stamp_build.py [--root DIR] [--print]
  --root DIR  the copy to stamp (default: this repo; use a release copy, the repo keeps the line empty)
  --print     only print the build id and the stamped file body, write nothing
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = re.compile(r"^var BUILD_CONFIG = \{build: '[^']*'\}$", re.M)


def build_id(root=ROOT, day=None):
    sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=root, text=True).strip()
    return '%s-%s' % (sha, (day or datetime.date.today()).strftime('%Y%m%d'))


def stamped(body, build):
    if len(LINE.findall(body)) != 1:
        raise ValueError('js/buildinfo.js: expected one BUILD_CONFIG line')
    return LINE.sub("var BUILD_CONFIG = {build: '%s'}" % build, body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--print', action='store_true')
    args = ap.parse_args()
    path = os.path.join(args.root, 'js', 'buildinfo.js')
    build = build_id(ROOT)
    body = stamped(open(path).read(), build)
    if args.print:
        print(build)
        sys.stdout.write(body)
        return 0
    with open(path, 'w') as f:
        f.write(body)
    print(build)
    return 0


if __name__ == '__main__':
    sys.exit(main())
