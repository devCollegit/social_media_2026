(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let state, index = 0, chosen = '', dirty = false, busy = false;
  const finished = r => Boolean(r && r.label && !r.uncertain);
  function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
  function subset() {
    return state.rows.map((_, i) => i).filter(i => {
      const r = state.records[i];
      return $('filter').value === 'all' || ($('filter').value === 'uncertain' ? Boolean(r && r.uncertain) : !finished(r));
    });
  }
  function pick(label) {
    chosen = label; dirty = true;
    document.querySelectorAll('[data-label]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.label === chosen)));
  }
  function render() {
    const done = Object.values(state.records).filter(finished).length;
    const held = Object.values(state.records).filter(r => r.uncertain).length;
    $('progress').textContent = `${done} / ${state.rows.length}건 검수 완료`;
    $('counts').textContent = `보류 ${held}건 · 미완료 ${state.rows.length - done}건`;
    $('bar').max = state.rows.length; $('bar').value = done;
    $('export').disabled = busy || done !== state.rows.length || dirty;
    const ids = subset();
    $('workspace').hidden = ids.length === 0; $('empty').hidden = ids.length !== 0;
    if (!ids.length) return;
    if (!ids.includes(index)) index = ids.find(i => i >= index) ?? ids[0];
    const row = state.rows[index], record = state.records[index];
    $('position').textContent = `표본 ${index + 1} · 현재 보기 ${ids.indexOf(index) + 1} / ${ids.length}`;
    $('stock').textContent = `${row.stock_id} · ${row.parent_id ? '댓글' : '게시글'}`;
    $('parent').textContent = row.parent_text;
    $('context-status').textContent = ({parent_available: '연결된 부모 글', parent_missing: '저장된 자료에 부모 글이 없습니다.', top_level: '게시글 자체를 검수합니다.'})[row.context_status] || '맥락 확인 필요';
    $('parent').hidden = !row.parent_text;
    $('text').textContent = row.text_norm;
    chosen = record ? record.label : '';
    document.querySelectorAll('[data-label]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.label === chosen)));
    $('note').value = record ? record.note : '';
    $('uncertain').checked = record ? record.uncertain : false;
    $('previous').disabled = busy || ids.indexOf(index) === 0;
    $('skip').disabled = busy || ids.indexOf(index) === ids.length - 1;
    $('save').disabled = busy;
    dirty = false;
  }
  function mayLeave() { return !dirty || window.confirm('아직 저장하지 않은 선택과 메모가 있습니다. 버리고 이동할까요?'); }
  function move(delta) {
    if (busy || !mayLeave()) return;
    const ids = subset(), position = ids.indexOf(index) + delta;
    if (position >= 0 && position < ids.length) { index = ids[position]; dirty = false; render(); }
  }
  async function api(path, payload) {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Review-Token': state.token}, body: JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '요청에 실패했습니다.');
    return result;
  }
  function setBusy(value) {
    busy = value;
    ['save', 'previous', 'skip', 'filter', 'reviewer', 'uncertain', 'note', 'export'].forEach(id => $(id).disabled = value);
    document.querySelectorAll('[data-label]').forEach(b => b.disabled = value);
    if (!value) $('export').disabled = dirty || Object.values(state.records).filter(finished).length !== state.rows.length;
  }
  async function save() {
    if (busy || !state || $('workspace').hidden) return;
    const reviewer = $('reviewer').value.trim();
    if (!reviewer) { message('검수자 이름 또는 별칭을 입력하세요.', true); $('reviewer').focus(); return; }
    if (!chosen && !$('uncertain').checked) { message('감정을 선택하거나 보류로 표시하세요.', true); return; }
    const record = {label: chosen, uncertain: $('uncertain').checked, note: $('note').value, reviewer};
    const ids = subset(), next = ids[ids.indexOf(index) + 1];
    setBusy(true);
    try {
      const result = await api('/api/save', {...record, index, revision: state.revision});
      state.revision = result.revision; state.records[index] = record; dirty = false;
      const savedNumber = index + 1;
      if (next !== undefined) index = next;
      message(`${savedNumber}번 저장 완료. ${record.uncertain ? '보류 항목으로 남겼습니다.' : ''}`);
    } catch (error) { message(error.message + ' 현재 입력은 화면에 유지됩니다.', true); }
    finally { setBusy(false); if (!dirty) render(); }
  }
  document.querySelectorAll('[data-label]').forEach(b => b.addEventListener('click', () => { pick(b.dataset.label); $('export').disabled = true; }));
  ['note', 'uncertain'].forEach(id => $(id).addEventListener('input', () => { dirty = true; $('export').disabled = true; }));
  let lastFilter = $('filter').value;
  $('filter').addEventListener('change', () => {
    if (!mayLeave()) { $('filter').value = lastFilter; return; }
    lastFilter = $('filter').value; dirty = false; render();
  });
  $('previous').addEventListener('click', () => move(-1));
  $('skip').addEventListener('click', () => move(1));
  $('save').addEventListener('click', save);
  $('export').addEventListener('click', async () => {
    if (busy || dirty) return;
    setBusy(true);
    try {
      const result = await api('/api/export', {revision: state.revision});
      const url = URL.createObjectURL(new Blob(['\ufeff' + result.csv], {type: 'text/csv;charset=utf-8'}));
      const link = document.createElement('a'); link.href = url; link.download = result.filename;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
      message(`내보내기 완료 · 저장 경로: ${result.path}`);
    } catch (error) { message(error.message, true); }
    finally { setBusy(false); }
  });
  document.addEventListener('keydown', event => {
    if (busy || !state || $('workspace').hidden) return;
    if (event.ctrlKey && event.key === 'Enter') { event.preventDefault(); save(); return; }
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (['1', '2', '3'].includes(event.key)) { event.preventDefault(); pick(['긍정', '중립', '부정'][Number(event.key) - 1]); $('export').disabled = true; }
  });
  window.addEventListener('beforeunload', event => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } });
  setBusy(true);
  fetch('/api/state').then(async response => {
    if (!response.ok) throw new Error('검수 파일을 불러오지 못했습니다.');
    state = await response.json();
    const saved = Object.values(state.records).at(-1);
    if (saved) $('reviewer').value = saved.reviewer;
    setBusy(false); render();
  }).catch(error => message(error.message, true));
})();
