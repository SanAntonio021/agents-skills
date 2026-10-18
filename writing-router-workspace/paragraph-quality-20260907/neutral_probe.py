"""One-turn diagnostic of synthetic framing; excluded from paired acceptance."""
import json

import run_evaluation as replay


original_prompt = replay.initial_prompt


def neutral_prompt(*args, **kwargs):
    text = original_prompt(*args, **kwargs)
    framing = '这是独立的合成中文文稿任务，不对应真实项目。'
    if not text.startswith(framing):
        raise ValueError('Unexpected prompt framing; do not change diagnostic input silently')
    return text[len(framing):]


if __name__ == '__main__':
    cases = json.loads(replay.CASE_FILE.read_text(encoding='utf-8'))['evals']
    case = next(case for case in cases if case['id'] == 'empty-common-sense-report')
    case['id'] += '-neutral-framing-probe'
    replay.initial_prompt = neutral_prompt
    if not replay.run('claude', 'candidate', case, 240, 1, direct=True, native=True):
        raise SystemExit(1)
