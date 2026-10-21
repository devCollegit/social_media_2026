import hashlib
import json
from pathlib import Path

import pytest

import integration.merge_llm_batches as module


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    inputs=tmp_path/'inputs'; run=tmp_path/'run'; worker=run/'worker_1'
    inputs.mkdir();worker.mkdir(parents=True)
    src={'stock_id':'001','post_id':'1','text_norm':'상승 기대','parent_text':'','context_status':'top_level'}
    source=inputs/'batch-0001.jsonl';source.write_text(json.dumps(src,ensure_ascii=False)+'\n')
    m={'rows':1,'batches':[{'file':source.name,'rows':1,'sha256':module.sha(source)}]}
    (inputs/'manifest.json').write_text(json.dumps(m))
    (run/'prompt.md').write_text('fixed')
    (run/'manifest.json').write_text(json.dumps({'rows_expected':1,'model':'test','reasoning_effort':'medium',
        'input_manifest_sha256':module.sha(inputs/'manifest.json'),'prompt_sha256':module.sha(run/'prompt.md')}))
    result=dict(stock_id='001',post_id='1',relevance='related',sentiment='긍정',reason='상승 기대',evidence='상승',context_used=False)
    (worker/source.name).write_text(json.dumps(result,ensure_ascii=False)+'\n')
    return inputs,run,tmp_path/'state'/'merged'


def test_merge_complete_and_preserve_input_hash(tmp_path,monkeypatch):
    paths=fixture(tmp_path,monkeypatch)
    summary=module.merge_batches(*paths)
    assert summary['rows']==summary['batches']==1
    with pytest.raises(ValueError,match='덮어'):
        module.merge_batches(*paths)


def test_merge_rejects_missing_duplicate_and_changed_input(tmp_path,monkeypatch):
    inputs,run,out=fixture(tmp_path,monkeypatch)
    result=run/'worker_1'/'batch-0001.jsonl'
    original=result.read_text();result.unlink()
    with pytest.raises(ValueError,match='집합'):
        module.merge_batches(inputs,run,out)
    result.write_text(original)
    worker2=run/'worker_2';worker2.mkdir();duplicate=worker2/result.name;duplicate.write_text(original)
    with pytest.raises(ValueError,match='중복'):
        module.merge_batches(inputs,run,out)
    duplicate.unlink()
    (inputs/result.name).write_text('{}')
    with pytest.raises(ValueError,match='SHA'):
        module.merge_batches(inputs,run,out)


def test_merge_rejects_fabricated_evidence_and_changed_prompt(tmp_path,monkeypatch):
    inputs,run,out=fixture(tmp_path,monkeypatch)
    p=run/'worker_1'/'batch-0001.jsonl';r=json.loads(p.read_text());r['evidence']='없는 말';p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='evidence'):
        module.merge_batches(inputs,run,out)
    (run/'prompt.md').write_text('changed')
    with pytest.raises(ValueError,match='prompt'):
        module.merge_batches(inputs,run,out)
