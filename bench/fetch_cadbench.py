#!/usr/bin/env python3
"""
Fetch a seeded subset of CADBench (DeCoDELab/CADBench on Hugging Face).

Only the columns we need (file_id, label, step, stl) are read, and only from
the row groups that hold selected rows, so a 60-shape dev set costs a few
hundred MB instead of the 15 GB split.

Split name -> file prefix is NOT the obvious one (see the dataset README):
  benchB=bench0  benchF=bench0F  benchE=bench1A  benchA=bench1B  benchM=bench2  benchO=bench3
`label` holds the face-count tier (easy / medium / hard).

Selection is by seeded shuffle of the (split, tier) index, then partitioned in
a fixed order: test first, then dev, then smoke. The test set never overlaps
dev/smoke and does not change when dev size changes.

Usage:
  python bench/fetch_cadbench.py --index                 # build bench/cadbench/index.json
  python bench/fetch_cadbench.py --set dev --set test    # download STL+STEP for those sets
"""
import argparse
import hashlib
import json
import os
import random
import sys

REPO = 'datasets/DeCoDELab/CADBench'
PREFIX = {'benchB': 'bench0', 'benchF': 'bench0F', 'benchE': 'bench1A',
          'benchA': 'bench1B', 'benchM': 'bench2', 'benchO': 'bench3'}
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cadbench')

# (set name, split, tier, count). Order matters: earlier sets take rows first.
SETS = [
    ('test', 'benchA', 'hard', 100),
    ('dev', 'benchA', 'hard', 30),
    ('dev', 'benchE', 'hard', 30),
    ('smoke', 'benchA', 'hard', 5),
]


def _fs():
    from huggingface_hub import HfFileSystem
    return HfFileSystem()


def build_index(splits, workers=8):
    """Map every row of the given splits to (file, row_group, row, file_id, label)."""
    import pyarrow.parquet as pq
    from concurrent.futures import ThreadPoolExecutor
    fs = _fs()

    def one(path):
        pf = pq.ParquetFile(fs.open(path))
        rows = []
        for g in range(pf.metadata.num_row_groups):
            t = pf.read_row_group(g, columns=['file_id', 'label']).to_pydict()
            for i, (fid, lab) in enumerate(zip(t['file_id'], t['label'])):
                rows.append({'file': path.split('/')[-1], 'rg': g, 'row': i, 'file_id': fid, 'label': lab})
        return rows

    index = {}
    for split in splits:
        files = sorted(fs.glob(f'{REPO}/data/{PREFIX[split]}-*.parquet'))
        with ThreadPoolExecutor(workers) as ex:
            index[split] = [r for rows in ex.map(one, files) for r in rows]
        print(f'{split}: {len(index[split])} rows in {len(files)} files', file=sys.stderr)
    return index


def select(index, seed):
    taken, out = set(), {}
    for name, split, tier, n in SETS:
        pool = sorted((r for r in index[split] if r['label'] == tier), key=lambda r: r['file_id'])
        random.Random(f'{seed}:{split}:{tier}').shuffle(pool)
        picked = [r for r in pool if (split, r['file_id']) not in taken][:n]
        taken.update((split, r['file_id']) for r in picked)
        out.setdefault(name, []).extend(dict(r, split=split) for r in picked)
    return out


def count_brep_faces(step_bytes):
    return step_bytes.count(b'ADVANCED_FACE')


def download(selection, names):
    import pyarrow.parquet as pq
    fs = _fs()
    want = {}
    for name in names:
        for r in selection[name]:
            want.setdefault((r['split'], r['file'], r['rg']), []).append((name, r))
    for (split, fname, rg), rows in sorted(want.items()):
        todo = [(n, r) for n, r in rows
                if not os.path.exists(os.path.join(ROOT, n, r['file_id'] + '.stl'))]
        if not todo:
            continue
        pf = pq.ParquetFile(fs.open(f'{REPO}/data/{fname}'))
        t = pf.read_row_group(rg, columns=['file_id', 'step', 'stl']).to_pydict()
        for n, r in todo:
            assert t['file_id'][r['row']] == r['file_id'], (fname, rg, r)
            d = os.path.join(ROOT, n)
            os.makedirs(d, exist_ok=True)
            stl, step = t['stl'][r['row']], t['step'][r['row']]
            open(os.path.join(d, r['file_id'] + '.stl'), 'wb').write(stl)
            if step:
                open(os.path.join(d, r['file_id'] + '.step'), 'wb').write(step)
            r['brep_faces'] = count_brep_faces(step) if step else None
            r['sha1'] = hashlib.sha1(stl).hexdigest()
            print(f'{n:<6} {split} {r["file_id"]} faces={r["brep_faces"]}', file=sys.stderr)
    for name in names:
        man = os.path.join(ROOT, name, 'manifest.json')
        old = {m['file_id']: m for m in json.load(open(man))} if os.path.exists(man) else {}
        rows = [dict(old.get(r['file_id'], {}), **r) for r in selection[name]]
        json.dump(rows, open(man, 'w'), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--index', action='store_true', help='(re)build the label index')
    ap.add_argument('--set', action='append', default=[], help='set(s) to download: dev, test, smoke')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    os.makedirs(ROOT, exist_ok=True)
    idx_path = os.path.join(ROOT, 'index.json')
    if args.index or not os.path.exists(idx_path):
        json.dump(build_index(sorted({s for _, s, _, _ in SETS})), open(idx_path, 'w'))
    index = json.load(open(idx_path))
    for split, rows in index.items():
        from collections import Counter
        print(split, dict(Counter(r['label'] for r in rows)), file=sys.stderr)
    selection = select(index, args.seed)
    if args.set:
        download(selection, args.set)


if __name__ == '__main__':
    main()
