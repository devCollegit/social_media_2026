"""검증된 전체 LLM 묶음을 하나의 결과로 합친다. 누락 결과를 임의로 채우지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from analysis.llm_results import _read_predictions, _check_predictions, _ids

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def merge_batches(input_dir, run_dir, output):
    input_dir, run_dir, output = map(Path, (input_dir, run_dir, output))
    if not output.resolve().is_relative_to(ROOT / 'state') or output.resolve() == ROOT / 'state':
        raise ValueError('출력은 state 하위 새 폴더')
    if output.exists():
        raise ValueError('기존 결과를 덮어쓰지 않습니다')
    manifest = json.loads((input_dir / 'manifest.json').read_text())
    run_manifest = json.loads((run_dir / 'manifest.json').read_text())
    if 'source' in manifest and sha(manifest['source']['path']) != manifest['source']['sha256']:
        raise ValueError('원본 clean 입력 SHA 불일치')
    if sha(input_dir / 'manifest.json') != run_manifest['input_manifest_sha256']:
        raise ValueError('실행 시작 후 입력 manifest 변경')
    if sha(run_dir / 'prompt.md') != run_manifest['prompt_sha256']:
        raise ValueError('고정 prompt 변경')
    expected = [entry['file'] for entry in manifest['batches']]
    if len(expected) != len(set(expected)):
        raise ValueError('중복 입력 batch 이름')
    files = list(run_dir.glob('worker_*/batch-*.jsonl'))
    found = {}
    for path in files:
        if path.name in found:
            raise ValueError('중복 결과 batch')
        found[path.name] = path
    if set(found) != set(expected):
        raise ValueError(f'결과 batch 집합 불일치: 누락 {len(set(expected)-set(found))}, 추가 {len(set(found)-set(expected))}')
    sources, results, proofs = [], [], []
    for entry in manifest['batches']:
        source_path = input_dir / entry['file']
        if sha(source_path) != entry['sha256']:
            raise ValueError('입력 batch SHA 불일치')
        source = pd.DataFrame([json.loads(line) for line in source_path.read_text().splitlines()])
        if len(source) != entry['rows']:
            raise ValueError('입력 batch 행 수 불일치')
        result_path = found[entry['file']]
        result = _read_predictions(result_path)
        _check_predictions(source, result)
        sources.append(source)
        results.append(result)
        proofs.append(dict(batch=entry['file'], worker=result_path.parent.name, rows=len(result), input_sha256=entry['sha256'],
                           result_sha256=sha(result_path)))
    source = pd.concat(sources, ignore_index=True)
    result = pd.concat(results, ignore_index=True)
    _ids(source, '전체 source')
    _ids(result, '전체 result')
    if len(source) != manifest['rows'] or len(source) != run_manifest['rows_expected']:
        raise ValueError('전체 기대 행 수 불일치')
    output.mkdir(parents=True, exist_ok=False)
    source.to_csv(output / 'source.csv', index=False, encoding='utf-8-sig')
    result.to_json(output / 'predictions.jsonl', orient='records', lines=True, force_ascii=False)
    proof = dict(rows=len(result), batches=len(proofs), model=run_manifest['model'],
                 reasoning_effort=run_manifest['reasoning_effort'],
                 prompt_sha256=run_manifest['prompt_sha256'],
                 predictions_sha256=sha(output / 'predictions.jsonl'),
                 source_sha256=sha(output / 'source.csv'), batch_proofs=proofs,
                 status='complete; schema/IDs/exact evidence checked; semantic accuracy not guaranteed')
    (output / 'manifest.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    return {key: value for key, value in proof.items() if key != 'batch_proofs'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir', type=Path, required=True)
    ap.add_argument('--run-dir', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(merge_batches(args.input_dir, args.run_dir, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
