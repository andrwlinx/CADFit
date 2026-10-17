#!/usr/bin/env python3
"""
Report for the agent-skills study: bench/runs/agentsk_scores.json (bench/agentsk_score.py)
and the episode transcripts -> bench/AGENT_SKILLS_RESULTS.md (+ a figure).

  .venv/bin/python bench/agent_skills_report.py [--scores ...] [--runs bench/runs/agentsk]
"""
import argparse
import collections
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = ('detect_directions', 'extract_sketch', 'fit_extrude', 'fit_revolve', 'section_extrude')


def mean(v):
    return sum(v) / len(v) if v else float('nan')


def paired_ci(a, b, n=10000, seed=0):
    """Mean of a-b over parts with a 95% bootstrap interval (resampling parts)."""
    d = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    boots = sorted(mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(n))
    return mean(d), boots[int(0.025 * n)], boots[int(0.975 * n) - 1]


def tool_stats(ep_dir):
    """Tool calls by name and how many returned an error, from transcript.jsonl."""
    calls, errors = collections.Counter(), collections.Counter()
    path = os.path.join(ep_dir, 'transcript.jsonl')
    if not os.path.exists(path):
        return calls, errors
    for line in open(path):
        m = json.loads(line)
        if m.get('role') == 'tool':
            calls[m.get('name')] += 1
            try:
                if 'error' in json.loads(m['content']):
                    errors[m.get('name')] += 1
            except (json.JSONDecodeError, TypeError):
                pass
    return calls, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scores', default=os.path.join(ROOT, 'bench', 'runs', 'agentsk_scores.json'))
    ap.add_argument('--runs', default=os.path.join(ROOT, 'bench', 'runs', 'agentsk'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'bench', 'AGENT_SKILLS_RESULTS.md'))
    a = ap.parse_args()
    S = json.load(open(a.scores))
    parts, C = S['parts'], S['conditions']
    col = lambda c, k: [C[c][p].get(k) or 0.0 for p in parts]  # noqa: E731

    agents = sorted(c for c in C if not c.startswith('pipeline/'))
    refs = [c for c in C if c.startswith('pipeline/')]
    L = ['# Open models as CAD agents with CADFit skills', '',
         f'{len(parts)} fresh-cohort parts (ledger A-005); budget 40 tool calls / 30 min per episode (A-006); '
         'episode answer = best model seen by agent-visible IoU (A-007). IoU = corrected judge on the mesh; '
         'IoU(CAD) = judge on the solid rebuilt by running the final CadQuery program (A-008, headline). '
         'Failed or missing episodes score 0.', '',
         '## Results', '',
         '| condition | IoU | IoU(CAD) | CAD invalid (of models) | episodes with a model | tool calls / episode | GT trial evals / episode | stops |',
         '|---|---|---|---|---|---|---|---|']
    for c in agents + refs:
        rec = [C[c][p] for p in parts]
        calls = [r['tool_calls'] for r in rec if r.get('tool_calls') is not None]  # episodes with a result
        trials = [r['trial_evaluations'] for r in rec if r.get('trial_evaluations') is not None]
        stops = collections.Counter((r['stop'][:9] if str(r['stop']).startswith('api error') else r['stop'])
                                    for r in rec if 'stop' in r)
        known = lambda k: all(k in r for r in rec)  # noqa: E731  (references may not record it)
        L.append(f'| {c} | {mean(col(c, "iou")):.4f} | {mean(col(c, "iou_cad")):.4f} | '
                 f'{sum(not r["cad_valid"] for r in rec if r.get("valid", True)) if known("cad_valid") else "n/a"} | '
                 f'{(str(sum(r["valid"] for r in rec)) + "/" + str(len(rec))) if known("valid") else "n/a"} | '
                 f'{mean(calls):.1f} (n={len(calls)}) | {f"{mean(trials):.0f}" if trials else "0"} | {", ".join(f"{k} {v}" for k, v in stops.most_common()) or "—"} |')

    L += ['', '## Skills vs code-only, paired over parts (IoU(CAD))', '',
          '| model | skills | code | skills − code [95% CI] | skills better / worse (±0.01) |', '|---|---|---|---|---|']
    models = sorted({c.split('/')[0] for c in agents if c.endswith('/skills')} &
                    {c.split('/')[0] for c in agents if c.endswith('/code')})
    for m in models:
        s, k = col(f'{m}/skills', 'iou_cad'), col(f'{m}/code', 'iou_cad')
        d, lo, hi = paired_ci(s, k)
        L.append(f'| {m} | {mean(s):.4f} | {mean(k):.4f} | {d:+.4f} [{lo:+.4f}, {hi:+.4f}] | '
                 f'{sum(x > y + 0.01 for x, y in zip(s, k))} / {sum(x < y - 0.01 for x, y in zip(s, k))} |')

    if 'pipeline/best_of_beam_section' in C:
        L += ['', '## Against the deterministic pipeline (IoU(CAD), paired)', '',
              '| condition | vs pipeline/beamsec [95% CI] | vs best-of beam+section [95% CI] |', '|---|---|---|']
        for c in agents:
            row = [c]
            for ref in ('pipeline/beamsec', 'pipeline/best_of_beam_section'):
                d, lo, hi = paired_ci(col(c, 'iou_cad'), col(ref, 'iou_cad'))
                row.append(f'{d:+.4f} [{lo:+.4f}, {hi:+.4f}]')
            L.append('| ' + ' | '.join(row) + ' |')

    L += ['', '## How the models used the skills (skills toolset)', '',
          'Per episode with a transcript (n shown), same denominator as the table above.', '',
          '| model | n | calls/episode | ' + ' | '.join(SKILLS) + ' | add_code | add_candidate | tool errors |',
          '|---|---|---|' + '---|' * (len(SKILLS) + 3)]
    for m in models:
        tot, err, n = collections.Counter(), collections.Counter(), 0
        for p in parts:
            ep = os.path.join(a.runs, m, 'skills', p)
            if not os.path.exists(os.path.join(ep, 'transcript.jsonl')):
                continue
            c_, e_ = tool_stats(ep)
            tot += c_
            err += e_
            n += 1
        if not n:
            L.append(f'| {m} | 0 | — |' + ' — |' * (len(SKILLS) + 3))
            continue
        L.append(f'| {m} | {n} | {sum(tot.values()) / n:.1f} | ' +
                 ' | '.join(f'{tot[s] / n:.1f}' for s in SKILLS) +
                 f' | {tot["add_code"] / n:.1f} | {tot["add_candidate"] / n:.1f} | '
                 f'{sum(err.values())}/{sum(tot.values())} |')

    L += ['', '## Caveats', '',
          '- One episode per (model, toolset, part); no repeat variance (deferred). Confidence intervals: paired '
          'percentile bootstrap over parts (10,000 resamples, seed 0) — part sampling only (A-028). '
          '"Better/worse" counts need |Δ IoU(CAD)| > 0.01 (A-029).',
          '- The no-LLM policy also scores every candidate union/cut against the GT without spending tool calls '
          '("GT trial evals" column, A-026): a ceiling-style control with more oracle access than an agent.',
          '- Answer selection uses ground-truth IoU (A-007), as does every condition and the best-of control.',
          '- The agent fit_revolve carries a revolve-split bug fix the frozen pipeline arms do not (A-016).',
          '- Pipeline references are the frozen fresh-cohort runs (bench/runs/fresh_scores.json), not rerun.', '']
    open(a.out, 'w').write('\n'.join(L))
    print('\n'.join(L))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 0.35 * len(agents + refs) + 1))
        names = agents + refs
        ax.barh(range(len(names)), [mean(col(c, 'iou_cad')) for c in names], color='#4a7bb7')
        ax.set_yticks(range(len(names)), names, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel(f'mean IoU(CAD) over {len(parts)} parts')
        ax.set_xlim(0, 1)
        fig.tight_layout()
        fig.savefig(os.path.join(ROOT, 'bench', 'figures', 'agent_skills_iou_cad.png'), dpi=150)
    except Exception as e:  # the report itself does not need the figure
        print(f'(no figure: {e})')


if __name__ == '__main__':
    main()
