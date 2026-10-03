const $ = (selector) => document.querySelector(selector);
const state = { catalog: null, sheet: null, kind: null, currentId: null, dirty: false, revision: 0, auth: null };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

async function api(path, method = 'GET', body = null) {
  const response = await fetch(path, {
    method,
    headers: body === null ? {} : { 'Content-Type': 'application/json' },
    body: body === null ? undefined : JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.erro || 'Não foi possível concluir a operação.');
  return data;
}

let toastTimer;
function toast(message) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.add('hidden'), 5200);
}

function show(view) {
  for (const id of ['startView', 'creationView', 'sheetView', 'legacyView']) {
    $('#' + id).classList.toggle('hidden', id !== view);
  }
}

function updateProviderUi() {
  const usingPlan = $('#aiProvider').value === 'chatgpt';
  $('#chatgptControls').classList.toggle('hidden', !usingPlan);
  $('#connectionState').textContent = usingPlan ? 'Usando plano ChatGPT Plus' : 'Ollama local';
  $('#generateButton').disabled = usingPlan && (!state.auth?.conectado || !$('#chatgptModel').value);
}

function updateEffortOptions(reset = false) {
  const model = $('#chatgptModel').value;
  const known = /^(gpt-6-luna|gpt-6-sol|gpt-6-astra|gpt-6\.1-sol|gpt-5\.6-(?:sol|terra|luna)|gpt-5\.5)(?:$|-)/.test(model);
  const effort = $('#reasoningEffort');
  effort.disabled = !known;
  effort.querySelector('[value="none"]').disabled = model.startsWith('gpt-6-astra') || model.startsWith('gpt-6.1-sol');
  effort.querySelector('[value="max"]').disabled = model.startsWith('gpt-5.5');
  if (!known) effort.value = '';
  else if (reset || [...effort.options].some((option) => option.value === effort.value && option.disabled)) {
    effort.value = model.startsWith('gpt-6-luna') ? 'low' : '';
  }
  $('#reasoningEffortWrap').classList.toggle('hidden', !state.auth?.conectado);
}

async function refreshAuth() {
  state.auth = await api('/api/auth/status');
  const connected = state.auth.conectado;
  $('#chatgptStatus').textContent = connected
    ? `Conectado: ${state.auth.email || state.auth.nome || 'conta ChatGPT'}`
    : 'Conecte sua conta para usar o plano.';
  $('#chatgptConnect').classList.toggle('hidden', connected);
  $('#chatgptDisconnect').classList.toggle('hidden', !connected);
  $('#chatgptModelWrap').classList.toggle('hidden', !connected);
  $('#reasoningEffortWrap').classList.toggle('hidden', !connected);
  $('#chatgptUsage').classList.toggle('hidden', !connected);
  if (connected) {
    $('#aiProvider').value = 'chatgpt';
    try {
      const data = await api('/api/auth/models');
      $('#chatgptModel').innerHTML = data.modelos.map((model) =>
        `<option value="${escapeHtml(model.id)}">${escapeHtml(model.nome)}</option>`
      ).join('');
      const savedModel = window.localStorage.getItem('mm_chatgpt_model');
      const preferred = data.modelos.find((item) => item.id === savedModel)
        || data.modelos.find((item) => item.id === 'gpt-6-luna' || item.id.startsWith('gpt-6-luna-'));
      if (preferred) $('#chatgptModel').value = preferred.id;
      updateEffortOptions(true);
      const savedEffort = window.localStorage.getItem('mm_chatgpt_effort');
      if (savedModel === $('#chatgptModel').value && savedEffort !== null) {
        const option = [...$('#reasoningEffort').options].find((item) => item.value === savedEffort && !item.disabled);
        if (option && !$('#reasoningEffort').disabled) $('#reasoningEffort').value = savedEffort;
      }
      if (!data.modelos.length) toast('Sua conta não apresentou modelos disponíveis para este aplicativo.');
    } finally { updateProviderUi(); }
  } else {
    $('#chatgptModel').innerHTML = '';
    if ($('#aiProvider').value === 'chatgpt') $('#aiProvider').value = 'ollama';
  }
  updateProviderUi();
}

async function refreshList() {
  const [data, drafts] = await Promise.all([api('/api/sheets'), api('/api/creations')]);
  const activeDrafts = drafts.criacoes.filter((item) => item.status !== 'finalizada');
  $('#creationList').innerHTML = activeDrafts.length ? activeDrafts.map((item) => `
    <button type="button" data-creation="${escapeHtml(item.id)}" class="${window.creationUi?.currentId() === item.id ? 'active' : ''}">
      <strong>${escapeHtml(item.nome || 'Novo personagem')}</strong>
      <small>${label(item.etapa_atual)} · rascunho</small>
    </button>`).join('') : '<p class="empty-list">Nenhum rascunho ainda.</p>';
  const list = $('#sheetList');
  if (!data.fichas.length) {
    list.innerHTML = '<p class="empty-list">Nenhuma ficha salva ainda.</p>';
    return;
  }
  list.innerHTML = data.fichas.map((item) => `
    <button type="button" data-open="${escapeHtml(item.id)}" class="${item.id === state.currentId ? 'active' : ''}">
      <strong>${escapeHtml(item.nome || 'Sem nome')}</strong>
      <small>NP ${escapeHtml(item.np ?? '?')} · ${item.tipo === 'nova' ? 'Editável' : 'Leitura'}</small>
    </button>`).join('');
}

function newSheet() {
  if ((state.dirty || window.creationUi?.hasUnsaved()) && !window.confirm('Há alterações não salvas. Deseja sair desta ficha?')) return;
  state.sheet = null;
  state.kind = null;
  state.currentId = null;
  state.dirty = false;
  window.creationUi?.clear();
  show('startView');
  updateStartPreview();
  refreshList().catch((error) => toast(error.message));
  $('#description').focus();
}

function updateStartPreview() {
  $('#startPreviewName').textContent = $('#characterName').value.trim() || 'Seu personagem';
  $('#startPreviewNP').textContent = $('#powerLevel').value || '?';
  $('#startPreviewConcept').textContent = $('#description').value.trim() || 'Seu conceito aparecerá aqui enquanto a ficha ganha forma.';
}

function sourceText(sources) {
  if (!Array.isArray(sources) || !sources.length) return 'Fonte não cadastrada';
  return sources.map((source) => `${source.livro || ''}, ${source.secao || ''}, p. ${source.pagina_impressa || '?'} (PDF ${source.pagina_pdf || '?'})`).join(' · ');
}

function section(title, detail, content, totalKey = '') {
  return `<section class="sheet-section"><div class="section-title"><h2>${escapeHtml(title)}</h2><span ${totalKey ? `data-section-total="${totalKey}"` : ''}>${escapeHtml(detail)}</span></div>${content}</section>`;
}

function optionsFor(items, used) {
  const available = items.filter((item) => !used.has(item.id));
  return available.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.nome)}</option>`).join('');
}

function addControl(kind, items, used) {
  const options = optionsFor(items, used);
  if (!options) return '';
  return `<div class="add-row"><select aria-label="Adicionar ${escapeHtml(kind)}" data-select="${kind}">${options}</select><button type="button" data-add="${kind}">Adicionar</button></div>`;
}

function renderLedger(sheet) {
  const summary = sheet.resumo;
  $('#ledger').innerHTML = `
    <div><span>Pontos do NP</span><strong>${summary.orcamento}</strong></div>
    <div><span>Pontos usados</span><strong>${summary.gastos}</strong></div>
    <div class="${summary.restantes < 0 ? 'negative' : ''}"><span>Disponíveis</span><strong>${summary.restantes}</strong></div>`;
  const warnings = [...summary.avisos];
  if (!warnings.length) {
    $('#warnings').classList.add('hidden');
  } else {
    $('#warnings').innerHTML = warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`).join('');
    $('#warnings').classList.remove('hidden');
  }
}

function renderEditor() {
  const sheet = state.sheet;
  const skills = state.catalog.pericias;
  const effects = state.catalog.efeitos;
  const advantages = state.catalog.vantagens;
  const skillOptions = Object.keys(skills).map((name) => ({ id: canonical(name), nome: name }));
  const advantageOptions = advantages.map((name) => ({ id: canonical(name), nome: name }));
  const abilityRows = state.catalog.habilidades.map((name) => `
    <div class="ability"><label for="ability-${escapeHtml(name)}">${escapeHtml(label(name))}<small>${state.catalog.custos.habilidade} pontos/grad.</small></label>
    <input id="ability-${escapeHtml(name)}" type="number" min="0" max="100" value="${sheet.habilidades[name] || 0}" data-field="ability" data-id="${escapeHtml(name)}" aria-label="Graduação de ${escapeHtml(label(name))}"></div>`).join('');
  const skillRows = sheet.pericias.map((row) => `
    <tr><td class="name">${escapeHtml(label(row.nome))}<span class="sub">${escapeHtml(label(row.habilidade))}</span></td>
    <td><input class="number-input" type="number" min="0" max="100" value="${row.pontos}" data-field="skill" data-id="${escapeHtml(row.id)}" aria-label="Pontos em ${escapeHtml(row.nome)}"></td>
    <td data-ranks="${escapeHtml(row.id)}">${row.graduacoes}</td><td data-bonus="${escapeHtml(row.id)}">${row.bonus}</td>
    <td data-cost="skill:${escapeHtml(row.id)}">${row.custo}</td><td><button type="button" class="row-delete" data-remove="skill" data-id="${escapeHtml(row.id)}">Remover</button></td></tr>`).join('');
  const advantageRows = sheet.vantagens.map((row) => `
    <tr><td class="name">${escapeHtml(label(row.nome))}</td><td><input class="number-input" type="number" min="0" max="100" value="${row.graduacao}" data-field="advantage" data-id="${escapeHtml(row.id)}" aria-label="Graduação de ${escapeHtml(row.nome)}"></td>
    <td data-cost="advantage:${escapeHtml(row.id)}">${row.custo}</td><td><button type="button" class="row-delete" data-remove="advantage" data-id="${escapeHtml(row.id)}">Remover</button></td></tr>`).join('');
  const powerRows = sheet.poderes.map((row) => `
    <tr><td class="name">${escapeHtml(row.nome)}<span class="sub">${escapeHtml(row.motivo || 'Efeito selecionado')}</span><span class="source">${escapeHtml(sourceText(row.fontes))}</span></td>
    <td><input class="number-input" type="number" min="0" max="100" value="${row.graduacao}" data-field="power" data-id="${escapeHtml(row.id)}" aria-label="Graduação de ${escapeHtml(row.nome)}"></td>
    <td>${row.custo_base === null ? `<input class="number-input" type="number" min="1" max="100" placeholder="Definir" value="${row.custo_manual ?? ''}" data-field="manual" data-id="${escapeHtml(row.id)}" aria-label="Custo base de ${escapeHtml(row.nome)}">` : `${row.custo_base}/grad.`}</td>
    <td data-cost="power:${escapeHtml(row.id)}" class="${row.custo_pendente ? 'pending' : ''}">${row.custo_pendente ? 'Pendente' : row.custo}</td>
    <td><button type="button" class="row-delete" data-remove="power" data-id="${escapeHtml(row.id)}">Remover</button></td></tr>`).join('');
  $('#sheetView').innerHTML = `
    <div class="sheet-head"><div><div class="overline">Ficha editável · salvo neste computador</div><input id="editName" maxlength="100" value="${escapeHtml(sheet.nome)}" aria-label="Nome do personagem"><p>Jogador <input id="editPlayer" class="small-edit" maxlength="100" value="${escapeHtml(sheet.jogador)}" placeholder="Adicionar nome" aria-label="Nome do jogador"></p></div><div class="sheet-meta"><label>NP<input id="editNP" type="number" min="1" max="30" value="${sheet.np}"></label></div></div>
    <div class="ledger" id="ledger"></div><div class="warnings hidden" id="warnings"></div>
    <div class="sheet-actions"><button type="button" class="primary" id="saveSheet">Salvar alterações</button><span class="save-state" id="saveState">Salva localmente</span></div>
    ${section('Conceito', 'Pedido original', `<p class="sheet-description">${escapeHtml(sheet.descricao || 'Sem descrição.')}</p>`)}
    ${section('Habilidades', `${sheet.resumo.habilidades} pontos usados`, `<div class="abilities">${abilityRows}</div>`, 'habilidades')}
    ${section('Perícias', `${sheet.resumo.pericias} pontos usados`, `<div class="table-wrap"><table class="sheet-table"><thead><tr><th>Perícia</th><th>Pontos</th><th>Grad.</th><th>Bônus</th><th>Custo</th><th></th></tr></thead><tbody>${skillRows || '<tr><td colspan="6" class="empty-section">Nenhuma perícia selecionada.</td></tr>'}</tbody></table></div>${addControl('skill', skillOptions, new Set(sheet.pericias.map((r) => r.id)))}`, 'pericias')}
    ${section('Vantagens', `${sheet.resumo.vantagens} pontos usados`, `<div class="table-wrap"><table class="sheet-table"><thead><tr><th>Vantagem</th><th>Graduação</th><th>Custo</th><th></th></tr></thead><tbody>${advantageRows || '<tr><td colspan="4" class="empty-section">Nenhuma vantagem selecionada.</td></tr>'}</tbody></table></div>${addControl('advantage', advantageOptions, new Set(sheet.vantagens.map((r) => r.id)))}`, 'vantagens')}
    ${section('Poderes e efeitos', `${sheet.resumo.poderes} pontos conhecidos`, `<div class="table-wrap"><table class="sheet-table"><thead><tr><th>Efeito</th><th>Graduação</th><th>Custo base</th><th>Custo</th><th></th></tr></thead><tbody>${powerRows || '<tr><td colspan="5" class="empty-section">Nenhum efeito selecionado.</td></tr>'}</tbody></table></div>${addControl('power', effects, new Set(sheet.poderes.map((r) => r.id)))}<p class="source">O cálculo exibido cobre custos base. Extras, falhas e limites completos de NP ainda exigem revisão.</p>`, 'poderes')}
  `;
  renderLedger(sheet);
}

function label(value) {
  return String(value || '').replace(/(^|[\s-])\p{L}/gu, (part) => part.toLocaleUpperCase('pt-BR'));
}

function canonical(value) {
  const key = String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  return ({ sorte: 'controledasorte', moverobjetos: 'moverobjeto' })[key] || key;
}

function renderLegacy() {
  const sheet = state.sheet;
  const abilities = sheet.habilidades && typeof sheet.habilidades === 'object' ? sheet.habilidades : {};
  const abilityRows = Object.entries(abilities).map(([name, value]) => `<div class="ability"><label>${escapeHtml(label(name))}</label><strong>${escapeHtml(value && typeof value === 'object' ? value.graduacao : value)}</strong></div>`).join('');
  const skills = Array.isArray(sheet.pericias) ? sheet.pericias : [];
  const advantages = Array.isArray(sheet.vantagens) ? sheet.vantagens : [];
  const powers = Array.isArray(sheet.poderes) ? sheet.poderes : [];
  const total = Number(sheet.total);
  const left = Number(sheet.pontosDisponiveis);
  const legacyLedger = Number.isFinite(total) && Number.isFinite(left)
    ? `<div class="ledger"><div><span>Pontos do NP</span><strong>${total}</strong></div><div><span>Pontos usados</span><strong>${total - left}</strong></div><div><span>Disponíveis</span><strong>${left}</strong></div></div>` : '';
  $('#legacyView').innerHTML = `
    <div class="sheet-head"><div><div class="overline">Ficha antiga · somente leitura</div><h1>${escapeHtml(sheet.nomePersonagem || 'Personagem')}</h1><p>${escapeHtml(sheet.nomeJogador || 'Jogador não informado')}</p></div><div class="sheet-meta">NP ${escapeHtml(sheet.np ?? '?')}</div></div>
    ${legacyLedger}
    <div class="legacy-notice">Esta ficha usa o formato anterior. Ela pode ser lida aqui; novas fichas geradas pela IA têm edição e cálculo de pontos.</div>
    ${section('Habilidades', '', `<div class="abilities">${abilityRows || '<p class="empty-section">Sem dados.</p>'}</div>`)}
    ${section('Perícias', '', `<ul class="legacy-list">${skills.map((row) => `<li>${escapeHtml(label(row.nome))} · graduação ${escapeHtml(row['graduação'] ?? row.graduacao ?? '?')} · bônus ${escapeHtml(row.bonus ?? '?')}</li>`).join('') || '<li>Nenhuma perícia.</li>'}</ul>`)}
    ${section('Vantagens', '', `<ul class="legacy-list">${advantages.map((row) => `<li>${escapeHtml(label(row.nome))} · graduação ${escapeHtml(row.graduacao ?? '?')}</li>`).join('') || '<li>Nenhuma vantagem.</li>'}</ul>`)}
    ${section('Poderes', '', powers.map((power) => `<div class="legacy-power"><strong>${escapeHtml(power.nome || 'Poder')}</strong><ul class="legacy-list">${(Array.isArray(power.componentes) ? power.componentes : []).map((row) => `<li>${escapeHtml(row.nome || row.efeito || 'Componente')} · ${escapeHtml(row.efeito || '')} · graduação ${escapeHtml(row.graduacao ?? '?')} · custo registrado ${escapeHtml(row.custo_total ?? '?')}</li>`).join('')}</ul></div>`).join('') || '<p class="empty-section">Nenhum poder.</p>')}
  `;
}

async function openSheet(identifier) {
  if ((state.dirty || window.creationUi?.hasUnsaved()) && !window.confirm('Há alterações não salvas. Deseja abrir outra ficha?')) return;
  try {
    const data = await api('/api/sheets/' + encodeURIComponent(identifier));
    state.sheet = data.ficha;
    state.kind = data.tipo;
    state.currentId = identifier;
    state.dirty = false;
    window.creationUi?.clear();
    if (data.tipo === 'nova') { renderEditor(); show('sheetView'); }
    else { renderLegacy(); show('legacyView'); }
    await refreshList();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (error) { toast(error.message); }
}

function updateComputed(sheet) {
  renderLedger(sheet);
  for (const key of ['habilidades', 'pericias', 'vantagens', 'poderes']) {
    const total = document.querySelector(`[data-section-total="${key}"]`);
    if (total) total.textContent = `${sheet.resumo[key]} pontos ${key === 'poderes' ? 'conhecidos' : 'usados'}`;
  }
  for (const row of sheet.pericias) {
    const ranks = document.querySelector(`[data-ranks="${row.id}"]`);
    const bonus = document.querySelector(`[data-bonus="${row.id}"]`);
    const cost = document.querySelector(`[data-cost="skill:${row.id}"]`);
    if (ranks) ranks.textContent = row.graduacoes;
    if (bonus) bonus.textContent = row.bonus;
    if (cost) cost.textContent = row.custo;
  }
  for (const row of sheet.vantagens) {
    const cost = document.querySelector(`[data-cost="advantage:${row.id}"]`);
    if (cost) cost.textContent = row.custo;
  }
  for (const row of sheet.poderes) {
    const cost = document.querySelector(`[data-cost="power:${row.id}"]`);
    if (cost) { cost.textContent = row.custo_pendente ? 'Pendente' : row.custo; cost.classList.toggle('pending', row.custo_pendente); }
  }
}

let previewTimer;
function changed(rebuild = false) {
  state.dirty = true;
  $('#saveState').textContent = 'Alterações não salvas';
  const revision = ++state.revision;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    try {
      const data = await api('/api/preview', 'POST', state.sheet);
      if (revision !== state.revision) return;
      state.sheet = data.ficha;
      if (rebuild) renderEditor(); else updateComputed(data.ficha);
    } catch (error) {
      if (revision === state.revision) toast(error.message);
    }
  }, 250);
}

function updateField(target) {
  const sheet = state.sheet;
  if (!sheet) return;
  if (target.id === 'editName') { sheet.nome = target.value; changed(); return; }
  if (target.id === 'editPlayer') { sheet.jogador = target.value; changed(); return; }
  const field = target.dataset.field;
  if (!field && target.id !== 'editNP') return;
  const value = target.value === '' && field === 'manual' ? null : Number(target.value);
  if (value !== null && (!Number.isInteger(value) || value < (field === 'manual' || target.id === 'editNP' ? 1 : 0))) {
    toast('Informe um número válido.'); return;
  }
  if (target.id === 'editNP') sheet.np = value;
  else if (field === 'ability') sheet.habilidades[target.dataset.id] = value;
  else {
    const collection = { skill: 'pericias', advantage: 'vantagens', power: 'poderes', manual: 'poderes' }[field];
    const row = sheet[collection]?.find((item) => item.id === target.dataset.id);
    if (!row) return;
    if (field === 'skill') row.pontos = value;
    if (field === 'advantage' || field === 'power') row.graduacao = value;
    if (field === 'manual') row.custo_manual = value;
  }
  changed();
}

function addRow(kind) {
  const select = document.querySelector(`[data-select="${kind}"]`);
  if (!select?.value) return;
  const id = select.value;
  if (kind === 'skill') state.sheet.pericias.push({ id, pontos: 1 });
  else if (kind === 'advantage') state.sheet.vantagens.push({ id, graduacao: 1 });
  else if (kind === 'power') state.sheet.poderes.push({ id, graduacao: 1, motivo: '', fontes: [] });
  changed(true);
}

async function saveSheet() {
  try {
    clearTimeout(previewTimer);
    ++state.revision;
    const button = $('#saveSheet');
    button.disabled = true;
    const data = await api('/api/sheets/' + encodeURIComponent(state.sheet.id), 'PUT', state.sheet);
    state.sheet = data.ficha;
    state.dirty = false;
    renderEditor();
    await refreshList();
    toast('Ficha salva neste computador.');
  } catch (error) { toast(error.message); $('#saveSheet').disabled = false; }
}

async function generate(event) {
  event.preventDefault();
  const button = $('#generateButton');
  button.disabled = true;
  button.textContent = 'Abrindo conversa…';
  try {
    const form = new FormData(event.target);
    await window.creationUi.start({
      descricao: form.get('descricao'), nome: form.get('nome'), jogador: form.get('jogador'),
      np: Number(form.get('np')), provedor: form.get('provedor'),
      modelo: form.get('modelo'), esforco: form.get('esforco')
    });
    await refreshList();
    toast('Rascunho salvo. Continue a criação no chat.');
  } catch (error) { toast(error.message); }
  finally { button.textContent = 'Começar conversa'; updateProviderUi(); }
}

document.addEventListener('DOMContentLoaded', async () => {
  window.addEventListener('beforeunload', (event) => {
    if (state.dirty || window.creationUi?.hasUnsaved()) { event.preventDefault(); event.returnValue = ''; }
  });
  $('#newSheet').addEventListener('click', newSheet);
  $('#refreshList').addEventListener('click', () => refreshList().catch((error) => toast(error.message)));
  $('#generateForm').addEventListener('submit', generate);
  for (const id of ['description', 'characterName', 'powerLevel']) {
    $('#' + id).addEventListener('input', updateStartPreview);
  }
  updateStartPreview();
  $('#aiProvider').addEventListener('change', updateProviderUi);
  $('#chatgptModel').addEventListener('change', () => {
    updateEffortOptions(true);
    window.localStorage.setItem('mm_chatgpt_model', $('#chatgptModel').value);
    window.localStorage.setItem('mm_chatgpt_effort', $('#reasoningEffort').value);
    updateProviderUi();
  });
  $('#reasoningEffort').addEventListener('change', () => {
    window.localStorage.setItem('mm_chatgpt_effort', $('#reasoningEffort').value);
  });
  $('#closePlanWelcome').addEventListener('click', () => $('#planWelcome').close());
  $('#chatgptDisconnect').addEventListener('click', async () => {
    try {
      const result = await api('/api/auth/disconnect', 'POST', {});
      await refreshAuth();
      toast(result.revogado ? 'ChatGPT desconectado.' : 'Conexão local removida. Confira a revogação em Gerenciar uso.');
    } catch (error) { toast(error.message); }
  });
  $('#sheetList').addEventListener('click', (event) => {
    const button = event.target.closest('[data-open]');
    if (button) openSheet(button.dataset.open);
  });
  $('#creationList').addEventListener('click', (event) => {
    const button = event.target.closest('[data-creation]');
    if (button) {
      if (window.creationUi.hasUnsaved() && !window.confirm('Há alterações não salvas. Deseja abrir outro rascunho?')) return;
      window.creationUi.open(button.dataset.creation).catch((error) => toast(error.message));
    }
  });
  $('#sheetView').addEventListener('input', (event) => {
    if (event.target.id === 'editName' || event.target.id === 'editPlayer') updateField(event.target);
  });
  $('#sheetView').addEventListener('change', (event) => updateField(event.target));
  $('#sheetView').addEventListener('click', (event) => {
    if (event.target.id === 'saveSheet') { saveSheet(); return; }
    const add = event.target.closest('[data-add]');
    if (add) { addRow(add.dataset.add); return; }
    const remove = event.target.closest('[data-remove]');
    if (remove) {
      const collection = { skill: 'pericias', advantage: 'vantagens', power: 'poderes' }[remove.dataset.remove];
      state.sheet[collection] = state.sheet[collection].filter((item) => item.id !== remove.dataset.id);
      changed(true);
    }
  });
  const authResult = new URLSearchParams(window.location.search).get('chatgpt');
  if (authResult) window.history.replaceState({}, '', '/');
  try {
    await refreshAuth();
    if (authResult === 'conectado' && state.auth?.conectado) {
      if (!window.localStorage.getItem('mm_chatgpt_welcome_seen')) {
        $('#planWelcome').showModal();
        window.localStorage.setItem('mm_chatgpt_welcome_seen', '1');
      } else toast('ChatGPT Plus conectado.');
    } else if (authResult === 'erro') toast('Não foi possível conectar o ChatGPT. Tente novamente.');
  } catch (error) { toast(error.message); updateProviderUi(); }
  try {
    state.catalog = await api('/api/catalog');
    if (!state.catalog.disponivel) {
      $('#connectionState').textContent = 'Motor local ausente';
      $('#generateButton').disabled = true;
      toast(state.catalog.motivo);
    }
    await refreshList();
  } catch (error) { toast(error.message); }
});
