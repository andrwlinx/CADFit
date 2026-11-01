#!/usr/bin/env python3
"""
Per-part wall times of pipeline runs, keyed by run and part, with retry information.

  python bench/analysis/timing_export.py --manifest bench/cadbench/fresh2/manifest.json \
      --runs h2s0_d0 h2s0_dx h2s0_v2 h2s0_v3 ... --logs 'bench/runs/arms_logs/h2s*.log' \
      [--trim h2s0_v3=bench/runs/h2s0_v3_trim.json ...] --out results/h2_timing.json

seconds        final_iou.json "duration" of the attempt that delivered (successful-attempt
               deployment latency under the run's concurrency; not total compute)
attempts       how many times the part was started in that run (job logs: "start <arm>/<part>");
               attempts > 1 means a preempted or OOM-killed attempt was retried, whose time
               is not in `seconds`
parallel       JOBS of the job that delivered it (job log header "jobs=N"), when found
trim_seconds   the trim stage (silhouettes + replay + judge) for --trim runs
"""
import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.path.join(ROOT, 'bench', 'runs')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--runs', nargs='+', required=True, help='<tag>_<arm> run names')
    ap.add_argument('--logs', default=os.path.join(RUNS, 'arms_logs', '*.log'), help='glob of arms job logs')
    ap.add_argument('--trim', nargs='*', default=[], help='run=trim_posthoc output')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    parts = sorted(m['file_id'] for m in json.load(open(a.manifest)))
    # Job logs are named <job name>_<array job>_<task>.log and the job name is the run
    # tag (bench/h2_submit.sh: -J h2s0 ...), so <tag>_<arm> identifies the run.
    starts, jobs_of = {}, {}
    for log in glob.glob(a.logs):
        tag = os.path.basename(log).split('_')[0]
        txt = open(log, errors='replace').read()
        m = re.search(r'jobs=(\d+)', txt)
        jobs = int(m.group(1)) if m else None
        for arm, part in re.findall(r'\] start (\w+)/(\S+)', txt):
            starts[(f'{tag}_{arm}', part)] = starts.get((f'{tag}_{arm}', part), 0) + 1
        for arm, part in re.findall(r'\] done  (\w+)/(\S+) exit 0', txt):
            jobs_of[(f'{tag}_{arm}', part)] = jobs
    trims = {r: json.load(open(p)) for r, p in (s.split('=') for s in a.trim)}
    out = {}
    for run in a.runs:
        rec = {}
        for p in parts:
            f = os.path.join(RUNS, run, p, 'final_iou.json')
            d = json.load(open(f)) if os.path.exists(f) else {}
            r = {'seconds': d.get('duration'), 'attempts': starts.get((run, p), 0),
                 'parallel': jobs_of.get((run, p))}
            if run in trims:
                t = (trims[run].get(p) or {}).get('trim_record') or {}
                r['trim_seconds'] = t.get('stage_seconds')
            rec[p] = r
        out[run] = rec
    json.dump(out, open(a.out, 'w'), indent=1)
    for run, rec in out.items():
        s = [r['seconds'] for r in rec.values() if r['seconds']]
        print(f"{run:<14} parts with time {len(s)}/{len(parts)}  retried {sum(r['attempts'] > 1 for r in rec.values())}")


if __name__ == '__main__':
    main()
