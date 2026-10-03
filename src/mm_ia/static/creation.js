/* Criação acompanhada: a ficha persistida pelo servidor é a fonte de verdade. */
(() => {
  const stages = ['conceito', 'habilidades', 'pericias', 'vantagens', 'poderes', 'revisao'];
  const titles = { conceito: 'Conceito', habilidades: 'Habilidades', pericias: 'Perícias', vantagens: 'Vantagens', poderes: 'Poderes', revisao: 'Revisão', concluida: 'Concluída' };
  let creation = null;
  let draft = null;
  let catalog = null;
  let busy = false;
  let sheetDirty = false;

  const endpoint = (action = '') => `/api/creations/${encodeURIComponent(creation.id)}${action ? `/${action}` : ''}`;
  const display = (value) => escapeHtml(value ?? '');
  const title = (stage) => titles[stage] || stage;

  async function loadCatalog() {
    if (!catalog) catalog = await api('/api/catalog');
    return catalog;
  }

  function setCreation(value) {
    creation = value;
    draft = JSON.parse(JSON.stringify(value.ficha));
    sheetDirty = false;
    render();
    refreshList().catch((error) => toast(error.message));
  }

  async function start(input) {
    await loadCatalog();
    const data = await api('/api/creations', 'POST', input);
    setCreation(data.criacao);
    show('creationView');
    $('#chatInput').focus();
  }

  async function open(identifier) {
    await loadCatalog();
    const data = await api(`/api/creations/${encodeURIComponent(identifier)}`);
    setCreation(data.criacao);
    show('creationView');
  }

  function renderProgress() {
    $('#stageProgress').innerHTML = stages.map((stage) => {
      const status = creation.etapas[stage]?.status || 'pendente';
      const active = creation.etapa_atual === stage || creation.proposta?.etapa === stage;
      return `<span class="stage-chip ${status === 'aprovada' ? 'done' : ''} ${active ? 'current' : ''}">${display(title(stage))}</span>`;
    }).join('');
  }

  function renderMessages() {
    const messages = creation.mensagens || [];
    $('#chatMessages').innerHTML = messages.map((message) => `
      <article class="chat-message ${display(message.papel)}">
        <small>${message.papel === 'usuario' ? 'Você' : message.papel === 'sistema' ? 'Ficha' : 'Assistente'} · ${display(title(message.etapa))}</small>
        <p>${display(message.texto)}</p>
      </article>`).join('');
    const proposal = creation.proposta;
    const actions = $('#proposalActions');
    actions.classList.toggle('hidden', !proposal && creation.etapa_atual !== 'concluida');
    if (proposal) {
      const data = proposal.dados;
      const details = proposal.etapa === 'conceito'
        ? data.conceito?.resumo
        : proposal.etapa === 'revisao'
          ? data.coerencia
          : `${proposal.ficha_previa.resumo[proposal.etapa]} pontos nesta área`;
      actions.innerHTML = `<strong>Proposta de ${display(title(proposal.etapa))}</strong>
        <p>${display(details || 'Confira a ficha antes de aceitar.')}</p>
        ${data.pendencias?.length ? `<ul>${data.pendencias.map((item) => `<li>${display(item)}</li>`).join('')}</ul>` : ''}
        <div><button type="button" class="primary" id="acceptProposal">Aceitar proposta</button><span>Para alterar, escreva no chat abaixo.</span></div>`;
    } else if (creation.etapa_atual === 'concluida' && creation.status !== 'finalizada') {
      actions.innerHTML = '<strong>Ficha pronta para revisão</strong><p>Confira pontos e pendências na ficha antes de finalizar.</p><button type="button" class="primary" id="finishCreation">Finalizar ficha</button>';
    } else actions.innerHTML = '';
    const stream = $('#chatMessages');
    stream.scrollTop = stream.scrollHeight;
  }

  function section(heading, body, detail = '') {
    return `<section class="creation-section"><div class="creation-section-head"><h3>${display(heading)}</h3><span>${display(detail)}</span></div>${body}</section>`;
  }

  function rowsFor(field, sheet, editable) {
    const rows = sheet[field] || [];
    const numeric = field === 'pericias' ? 'pontos' : 'graduacao';
    const name = field === 'pericias' ? 'Perícias' : field === 'vantagens' ? 'Vantagens' : 'Poderes';
    const body = rows.length ? rows.map((row, index) => `<div class="creation-row">
      <div><strong>${display(row.nome)}</strong>${field === 'pericias' ? `<small>${row.graduacoes} graduações · ${display(label(row.habilidade))} · bônus total ${row.bonus >= 0 ? '+' : ''}${row.bonus}</small>` : row.motivo ? `<small>${display(row.motivo)}</small>` : ''}</div>
      <label>${numeric === 'pontos' ? 'Pontos gastos' : 'Graduação'}<input type="number" min="0" max="100" value="${row[numeric]}" data-collection="${field}" data-index="${index}" data-key="${numeric}" ${editable ? '' : 'disabled'}></label>
      <span>${row.custo_pendente ? 'Custo pendente' : `${row.custo} pts`}</span>
      ${editable ? `<button type="button" class="row-delete" data-delete="${field}" data-index="${index}">Remover</button>` : ''}
    </div>`).join('') : '<p class="empty-section">Ainda não preenchido.</p>';
    let choices = [];
    if (field === 'pericias') choices = Object.keys(catalog.pericias || {}).map((item) => ({ id: canonical(item), nome: item }));
    if (field === 'vantagens') choices = (catalog.vantagens || []).map((item) => ({ id: canonical(item), nome: item }));
    if (field === 'poderes') choices = catalog.efeitos || [];
    const used = new Set(rows.map((row) => row.id));
    const available = choices.filter((item) => !used.has(item.id));
    const add = editable && available.length ? `<div class="creation-add"><select aria-label="Adicionar a ${name}" data-choice="${field}">${available.map((item) => `<option value="${display(item.id)}">${display(item.nome)}</option>`).join('')}</select><button type="button" class="secondary" data-add-creation="${field}">Adicionar</button></div>` : '';
    return section(name, body + add, `${sheet.resumo[field]} pontos`);
  }

  function renderSheet() {
    const preview = creation.proposta?.ficha_previa;
    const sheet = preview || draft;
    const editable = creation.status === 'em_criacao' && !preview;
    const areaEditable = (area) => editable && (
      creation.etapas[area]?.status === 'aprovada' ||
      stages.indexOf(area) <= stages.indexOf(creation.etapa_atual)
    );
    const warnings = [...(sheet.resumo.avisos || []), ...(creation.pendencias || [])];
    const abilityRows = Object.entries(sheet.habilidades).map(([name, rank]) => `<label class="creation-ability"><span>${display(label(name))}</span><input type="number" min="0" max="100" value="${rank}" data-ability="${display(name)}" ${areaEditable('habilidades') ? '' : 'disabled'}></label>`).join('');
    $('#creationSheet').innerHTML = `<div class="creation-sheet-head"><div><small>${preview ? 'Prévia da proposta' : 'Rascunho salvo'}</small><h2>Ficha do personagem</h2></div><span>NP ${sheet.np}</span></div>
      <div class="creation-ledger"><div><span>Orçamento</span><strong>${sheet.resumo.orcamento}</strong></div><div><span>Gastos</span><strong>${sheet.resumo.gastos}</strong></div><div><span>Restantes</span><strong class="${sheet.resumo.restantes < 0 ? 'negative' : ''}">${sheet.resumo.restantes}</strong></div></div>
      ${warnings.length ? `<div class="creation-warnings">${warnings.map((warning) => `<p>${display(warning)}</p>`).join('')}</div>` : ''}
      ${section('Identidade', `<div class="creation-fields"><label>Nome<input data-sheet="nome" maxlength="100" value="${display(sheet.nome)}" ${editable ? '' : 'disabled'}></label><label>Jogador<input data-sheet="jogador" maxlength="100" value="${display(sheet.jogador)}" ${editable ? '' : 'disabled'}></label><label>NP<input data-sheet="np" type="number" min="1" max="30" value="${sheet.np}" ${editable ? '' : 'disabled'}></label></div><p class="sheet-description">${display(sheet.descricao)}</p>`)}
      ${creation.conceito ? section('Conceito', `<p>${display(creation.conceito.resumo)}</p>`) : ''}
      ${section('Habilidades', `<div class="creation-abilities">${abilityRows}</div>`, `${sheet.resumo.habilidades} pontos`)}
      ${rowsFor('pericias', sheet, areaEditable('pericias'))}
      ${rowsFor('vantagens', sheet, areaEditable('vantagens'))}
      ${rowsFor('poderes', sheet, areaEditable('poderes'))}
      ${editable ? '<div class="creation-save"><button type="button" class="secondary" id="saveCreationSheet">Salvar edições da ficha</button><span id="creationEditState">Edições diretas são salvas ao clicar.</span></div>' : '<p class="creation-preview-note">Aceite ou ajuste a proposta pelo chat para editar a ficha.</p>'}`;
  }

  function render() {
    $('#creationTitle').textContent = creation.ficha.nome;
    $('#creationStatus').textContent = creation.status === 'finalizada' ? 'Ficha finalizada' : `Etapa atual: ${title(creation.etapa_atual)} · rascunho salvo`;
    $('#chatInput').disabled = creation.status !== 'em_criacao' || creation.etapa_atual === 'concluida';
    $('#chatSend').disabled = $('#chatInput').disabled;
    $('#chatHint').textContent = creation.proposta ? 'Peça uma mudança para reformular a proposta.' : 'A IA fará uma proposta para a etapa atual.';
    $('#chatSend').textContent = creation.proposta ? 'Pedir ajuste' : 'Gerar proposta';
    renderProgress();
    renderMessages();
    renderSheet();
  }

  async function perform(action, body) {
    if (busy) return false;
    busy = true;
    $('#chatSend').disabled = true;
    try {
      const data = await api(endpoint(action), 'POST', { revisao: creation.revisao, ...body });
      setCreation(data.criacao);
      return true;
    } catch (error) {
      if (error.message.includes('Recarregue')) {
        await open(creation.id);
      }
      toast(error.message);
      return false;
    } finally {
      busy = false;
      $('#chatSend').disabled = creation.status !== 'em_criacao' || creation.etapa_atual === 'concluida';
    }
  }

  function updateDraft(target) {
    if (!draft || creation.proposta) return;
    if (target.dataset.sheet) draft[target.dataset.sheet] = target.dataset.sheet === 'np' ? Number(target.value) : target.value;
    if (target.dataset.ability) draft.habilidades[target.dataset.ability] = Number(target.value);
    if (target.dataset.collection) draft[target.dataset.collection][Number(target.dataset.index)][target.dataset.key] = Number(target.value);
    sheetDirty = true;
    $('#creationEditState').textContent = 'Há edições para salvar.';
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#backToStart').addEventListener('click', () => newSheet());
    $('#chatForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = $('#chatInput');
      const instruction = input.value.trim();
      if (!instruction && creation.proposta) return;
      if (sheetDirty && !(await perform('sheet', { ficha: draft }))) return;
      if (await perform('propose', { etapa: creation.etapa_atual, instrucao: instruction })) input.value = '';
    });
    $('#proposalActions').addEventListener('click', (event) => {
      if (event.target.id === 'acceptProposal') perform('approve', {});
      if (event.target.id === 'finishCreation') perform('finish', {});
    });
    $('#creationSheet').addEventListener('input', (event) => updateDraft(event.target));
    $('#creationSheet').addEventListener('click', (event) => {
      const add = event.target.closest('[data-add-creation]');
      const remove = event.target.closest('[data-delete]');
      if (add) {
        const field = add.dataset.addCreation;
        const id = $(`[data-choice="${field}"]`).value;
        draft[field].push(field === 'pericias' ? { id, pontos: 1 } : { id, graduacao: 1 });
        sheetDirty = true;
        renderSheet();
        $('#creationEditState').textContent = 'Há edições para salvar.';
      } else if (remove) {
        draft[remove.dataset.delete].splice(Number(remove.dataset.index), 1);
        sheetDirty = true;
        renderSheet();
        $('#creationEditState').textContent = 'Há edições para salvar.';
      } else if (event.target.id === 'saveCreationSheet') {
        perform('sheet', { ficha: draft });
      }
    });
    $('#creationView').querySelectorAll('[data-pane]').forEach((button) => button.addEventListener('click', () => {
      $('#creationView').dataset.pane = button.dataset.pane;
      $('#creationView').querySelectorAll('[data-pane]').forEach((tab) => tab.classList.toggle('active', tab === button));
    }));
  });

  window.creationUi = {
    start, open, currentId: () => creation?.id, hasUnsaved: () => sheetDirty,
    clear: () => { creation = null; draft = null; sheetDirty = false; },
  };
})();
