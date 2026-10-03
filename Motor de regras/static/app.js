"use strict";

let catalog, draft, calculated, filename = "", active = "personagem";
let revision = 0, dirty = false, timer, loading = true;
const $ = (id) => document.getElementById(id);
const sections = {
  personagem: ["Personagem", "Nome, identidade, histórico e pontos do personagem."],
  habilidades: ["Habilidades", "Defina as graduações totais. Cada graduação custa 2 pontos."],
  defesas: ["Defesas", "Compre graduações além das habilidades. Cada graduação custa 1 ponto."],
  pericias: ["Perícias", "Duas graduações custam 1 ponto. Perícias de combate e Especialidade precisam de uma especialização."],
  vantagens: ["Vantagens", "Escolha as vantagens e suas graduações ou detalhes."],
  poderes: ["Poderes e dispositivos", "Monte cada poder por componentes, extras e falhas."],
  equipamentos: ["Equipamento", "Itens, armas, veículos e QGs usam pontos de equipamento da vantagem Equipamento."],
  complicacoes: ["Complicações e notas", "Escolha pelo menos duas complicações, incluindo uma Motivação."],
  revisao: ["Revisão da ficha", "Confira os custos, os bônus e as pendências antes de jogar."]
};
const names = {
  forca: "Força", agilidade: "Agilidade", destreza: "Destreza", luta: "Luta",
  intelecto: "Intelecto", prontidao: "Prontidão", presenca: "Presença", vigor: "Vigor",
  esquiva: "Esquiva", aparar: "Aparar", fortitude: "Fortitude", vontade: "Vontade", resistencia: "Resistência",
  nome_civil: "Nome civil", identidade: "Identidade pública ou secreta", genero: "Gênero",
  idade: "Idade", altura: "Altura", peso: "Peso", olhos: "Olhos", cabelo: "Cabelo", grupo: "Grupo",
  base: "Base de operações", origem: "Origem", aparencia: "Aparência", personalidade: "Personalidade",
  objetivos: "Objetivos", historico: "Histórico",
  nome: "Nome", especializacao: "Especialização", graduacao: "Graduação", "graduação": "Graduações",
  custo_base: "Custo por graduação", detalhes: "Detalhes", acao: "Ação", alcance: "Alcance",
  duracao: "Duração", protecao: "Proteção", defesa_ativa: "Bônus de Esquiva e Aparar",
  corpo: "Corpo a corpo", distancia: "À distância", area: "Área", percepcao: "Percepção",
  fixo: "Fixo", por_graduacao: "Por graduação"
};
const label = (v) => names[v] || v.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
const clone = (v) => structuredClone(v);
function node(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith("on")) n.addEventListener(key.slice(2), value);
    else if (key === "class") n.className = value;
    else if (key === "text") n.textContent = value;
    else if (value !== null && value !== undefined && value !== false) n.setAttribute(key, value === true ? "" : value);
  }
  n.append(...children.flat().filter((c) => c !== null && c !== undefined));
  return n;
}
const button = (text, action, cls = "") => node("button", {type: "button", class: cls, onclick: action}, text);
const grid = (...children) => node("div", {class: "grid"}, ...children);
const get = (path) => path.reduce((v, key) => v?.[key], draft);
function set(path, value) {
  const parent = get(path.slice(0, -1));
  parent[path.at(-1)] = value;
}
function msg(id, text) {
  $(id).textContent = text || "";
  $(id).hidden = !text;
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.erro || "Não foi possível concluir a operação.");
  return body;
}
function remember() {
  try { localStorage.setItem("mm-manual-rascunho", JSON.stringify({ficha: draft, arquivo: filename, dirty})); }
  catch { msg("notice", "O rascunho não pôde ser guardado no navegador. Use Salvar ficha."); }
}
function changed(renderAgain = false) {
  revision++;
  dirty = true;
  remember();
  $("save-state").textContent = "Alterações não salvas · recalculando…";
  msg("error", "");
  msg("notice", "");
  if (renderAgain) render();
  clearTimeout(timer);
  timer = setTimeout(preview, 350);
}
async function preview() {
  clearTimeout(timer);
  if (!draft) return false;
  const version = revision;
  try {
    const body = await api("/api/calcular", {ficha: draft});
    if (version !== revision) return false;
    draft = body.ficha;
    calculated = body.ficha;
    updateStats();
    remember();
    msg("error", "");
    $("save-state").textContent = dirty ? "Alterações não salvas" : "Ficha salva";
    if (active === "revisao") render();
    return true;
  } catch (error) {
    if (version === revision) {
      msg("error", error.message);
      $("save-state").textContent = "Corrija os campos para recalcular. Os pontos exibidos são do último cálculo válido.";
    }
    return false;
  }
}
let fieldId = 0;
function field(path, title, opts = {}) {
  const id = "field-" + (++fieldId), value = get(path);
  let input;
  if (opts.choices) {
    input = node("select", {id});
    for (const choice of opts.choices) {
      const [key, text] = Array.isArray(choice) ? choice : [choice, label(choice)];
      input.append(node("option", {value: key}, text));
    }
    input.value = value == null ? (input.options[0]?.value ?? "") : String(value);
    if (value == null) set(path, opts.numericChoice ? Number(input.value) : input.value);
    if (![...input.options].some((o) => o.value === String(value)) && value !== undefined && value !== null) {
      input.append(node("option", {value}, String(value)));
      input.value = value;
    }
  } else if (opts.multiline) {
    input = node("textarea", {id, rows: opts.rows || 3, maxlength: 4000});
    input.value = value ?? "";
  } else {
    input = node("input", {id, type: opts.number ? "number" : "text",
      min: opts.min, max: opts.max, step: opts.number ? 1 : null,
      maxlength: opts.number ? null : (opts.maxlength || 100),
      disabled: opts.disabled, placeholder: opts.placeholder});
    input.value = value ?? "";
  }
  input.setAttribute("aria-label", title);
  const event = opts.choices ? "change" : "input";
  input.addEventListener(event, () => {
    let val = opts.number ? (input.value === "" ? null : Number(input.value)) : input.value;
    if (opts.numericChoice) val = Number(val);
    set(path, val);
    opts.after?.(val);
    changed(!!opts.rerender);
  });
  const wrap = node("label", {for: id, class: opts.full ? "full" : ""}, title, input);
  if (opts.help) wrap.append(node("small", {}, opts.help));
  return wrap;
}
function check(path, title, after, rerender = false) {
  const id = "field-" + (++fieldId);
  const input = node("input", {id, type: "checkbox"});
  input.checked = !!get(path);
  input.addEventListener("change", () => {
    set(path, input.checked);
    after?.(input.checked);
    changed(rerender);
  });
  return node("label", {for: id, class: "check"}, input, title);
}
function computed(path, prefix = "") {
  const n = node("p", {class: "muted computed"});
  n.dataset.path = JSON.stringify(path);
  n.dataset.prefix = prefix;
  return n;
}
function updateStats() {
  if (!calculated) return;
  $("hero").textContent = draft.nomePersonagem || "Novo personagem";
  $("spent").textContent = calculated.total - calculated.pontosDisponiveis;
  $("budget").textContent = calculated.total;
  $("remaining").textContent = calculated.pontosDisponiveis;
  $("remaining").parentElement.classList.toggle("negative", calculated.pontosDisponiveis < 0);
  document.querySelectorAll(".computed").forEach((n) => {
    const path = JSON.parse(n.dataset.path);
    const value = path.reduce((v, key) => v?.[key], calculated);
    n.textContent = n.dataset.prefix + (value ?? "—");
  });
}
function remove(path, index) {
  get(path).splice(index, 1);
  changed(true);
}
function entry(title, onRemove, ...children) {
  return node("section", {class: "entry"},
    node("div", {class: "entry-head"}, node("h3", {}, title), button("Remover", onRemove, "danger")), ...children);
}
function add(text, action) {
  return button(text, () => { action(); changed(true); }, "add");
}
function render() {
  if (!draft) return;
  fieldId = 0;
  $("section-title").textContent = sections[active][0];
  $("section-help").textContent = sections[active][1];
  for (const n of $("nav").children) n.setAttribute("aria-current", n.dataset.section === active ? "page" : "false");
  const body = $("editor");
  body.replaceChildren();
  if (active === "personagem") {
    body.append(grid(field(["nomePersonagem"], "Nome do personagem"),
      field(["nomeJogador"], "Jogador"), field(["np"], "Nível de poder", {number: true, min: 1, max: 30}),
      field(["pontosExtras"], "Pontos adicionais do mestre", {number: true, min: 0}),
      field(["pontosHeroicos"], "Pontos heroicos", {number: true, min: 0})));
    body.append(node("h3", {class: "entry"}, "Identidade e histórico"));
    body.append(grid(...Object.keys(draft.identidade).map((key) =>
      field(["identidade", key], label(key), {multiline: ["origem","aparencia","personalidade","objetivos","historico"].includes(key)}))));
  } else if (active === "habilidades") {
    const panel = node("div", {class: "grid four"});
    for (const name of catalog.habilidades) {
      panel.append(node("div", {}, field(["habilidades", name], label(name), {number: true, min: -5, disabled: get(["habilidades", name]) === null}),
        node("label", {class: "check"}, (() => {
          const box = node("input", {type: "checkbox", "aria-label": label(name) + " ausente"});
          box.checked = draft.habilidades[name] === null;
          box.addEventListener("change", () => { draft.habilidades[name] = box.checked ? null : 0; changed(true); });
          return box;
        })(), "Habilidade ausente"),
        computed(["estatisticas", "habilidades", name], "Total com poderes: ")));
    }
    body.append(panel);
  } else if (active === "defesas") {
    body.append(grid(...Object.keys(catalog.defesas).map((name) => node("div", {},
      field(["defesas", name], label(name) + " · graduações compradas", {number: true, min: 0}),
      computed(["estatisticas", "defesas", name], "Total: ")))));
    body.append(computed(["estatisticas", "defesas", "resistencia"], "Resistência (habilidades, poderes e equipamento): "),
      computed(["estatisticas", "iniciativa"], "Iniciativa: "));
  } else if (active === "pericias") renderSkills(body);
  else if (active === "vantagens") renderAdvantages(body);
  else if (active === "poderes") renderPowers(body);
  else if (active === "equipamentos") renderEquipment(body);
  else if (active === "complicacoes") {
    draft.complicacoes.forEach((c, i) => body.append(entry("Complicação " + (i + 1), () => remove(["complicacoes"], i),
      grid(field(["complicacoes", i, "tipo"], "Tipo", {placeholder: "Motivação, Segredo, Rivalidade…"}),
        field(["complicacoes", i, "descricao"], "Descrição", {multiline: true})))));
    body.append(add("Adicionar complicação", () => draft.complicacoes.push({tipo: "", descricao: ""})),
      node("div", {class: "entry"}, field(["notas"], "Notas da ficha", {multiline: true, rows: 5})));
  } else renderReview(body);
  updateStats();
}
function renderSkills(body) {
  draft.pericias.forEach((p, i) => {
    const path = ["pericias", i];
    const fields = [field([...path, "nome"], "Perícia", {choices: Object.keys(catalog.pericias), rerender: true,
      after: (v) => { get(path).habilidade = catalog.pericias[v]; }}),
      field([...path, "graduação"], "Graduações", {number: true, min: 0}),
      field([...path, "especializacao"], "Especialização", {help: catalog.pericias_especializadas.includes(p.nome) ? "Obrigatória para esta perícia." : "Opcional."})];
    if (p.nome === "especialidade") fields.push(field([...path, "habilidade"], "Habilidade associada", {choices: catalog.habilidades}));
    body.append(entry("Perícia " + (i + 1), () => remove(["pericias"], i), grid(...fields),
      computed([...path, "bonus"], "Bônus total: "), computed([...path, "custo"], "Custo em PP: ")));
  });
  body.append(add("Adicionar perícia", () => draft.pericias.push({
    nome: "acrobacia", "graduação": 2, habilidade: "agilidade", especializacao: ""})));
}
function renderAdvantages(body) {
  draft.vantagens.forEach((v, i) => {
    const path = ["vantagens", i];
    body.append(entry("Vantagem " + (i + 1), () => remove(["vantagens"], i), grid(
      field([...path, "nome"], "Vantagem", {choices: catalog.vantagens, rerender: true,
        after: (value) => { if (!catalog.vantagens_graduadas.includes(value)) get(path).graduacao = 1; }}),
      field([...path, "graduacao"], "Graduação", {number: true, min: 1,
        max: v.nome === "sorte" ? Math.floor(draft.np / 2) : catalog.limites_vantagens[v.nome],
        disabled: !catalog.vantagens_graduadas.includes(v.nome)}),
      field([...path, "detalhe"], "Escolhas e detalhes", {full: true, maxlength: 500})),
      computed([...path, "pontos_gastos"], "Custo em PP: ")));
  });
  body.append(add("Adicionar vantagem", () => draft.vantagens.push({nome: catalog.vantagens[0], graduacao: 1, detalhe: ""})));
}
function newPower(name) {
  return {nome: name, componentes: [], alternativas: [], extras: {}, falhas: {}, ativo: 0, descritores: "", notas: ""};
}
function newComponent(list) {
  let name = "Dano", count = 1;
  while (list.some((v) => v.nome === name)) name = "Dano " + (++count);
  return {nome: name, efeito: "Dano", graduacao: 1, custo_base: 1,
    extras: {}, falhas: {}, modo_ataque: "corpo", especializacao_ataque: name,
    acao: "Padrão", alcance: "Perto", duracao: "Instantâneo", resistencia: "Resistência", detalhes: ""};
}
function renderPowers(body) {
  draft.poderes.forEach((power, i) => {
    const path = ["poderes", i];
    const panel = entry(power.nome || "Poder " + (i + 1), () => remove(["poderes"], i),
      grid(field([...path, "nome"], "Nome do poder"), field([...path, "descritores"], "Descritores"),
        field([...path, "notas"], "Notas", {multiline: true, full: true})),
      computed([...path, "custo_total"], "Custo do conjunto em PP: "));
    if (power.alternativas.length) {
      panel.append(field([...path, "ativo"], "Variante usada nos bônus", {
        choices: [[0, "Primário"], ...power.alternativas.map((v, j) => [j + 1, v.nome])], numericChoice: true}),
        check([...path, "dinamico"], "Arranjo dinâmico", (checked) => {
          get(path).alternativas.forEach((a) => { a.dinamico = checked; });
        }));
    }
    renderVariant(panel, path, false);
    power.alternativas.forEach((a, j) => {
        const alternative = [...path, "alternativas", j];
      const sub = node("div", {class: "subentry"}, node("div", {class: "entry-head"},
        node("h3", {}, "Alternativa " + (j + 1)), button("Remover alternativa", () => {
          get([...path, "alternativas"]).splice(j, 1); set([...path, "ativo"], 0); changed(true);
        }, "danger")), field([...alternative, "nome"], "Nome da alternativa"));
      renderVariant(sub, alternative, true);
      panel.append(sub);
    });
    panel.append(add("Adicionar alternativa", () => {
      const a = newPower("Alternativa " + (get(path).alternativas.length + 1));
      a.dinamico = !!get(path).dinamico;
      get(path).alternativas.push(a);
    }));
    const global = node("details", {}, node("summary", {}, "Extras e falhas do conjunto"));
    global.append(renderModifiers(path, "extras", true), renderModifiers(path, "falhas", true),
      check([...path, "indestrutivel"], "Dispositivo indestrutível (quando Removível)"));
    panel.append(global);
    body.append(panel);
  });
  body.append(add("Adicionar poder", () => draft.poderes.push(newPower("Poder " + (draft.poderes.length + 1)))));
}
function renderVariant(panel, path) {
  const power = get(path);
  power.componentes.forEach((c, i) => {
    const cp = [...path, "componentes", i];
    const sub = node("div", {class: "subentry"},
      node("div", {class: "entry-head"}, node("h4", {}, c.nome || "Componente"), button("Remover componente", () => remove([...path, "componentes"], i), "danger")));
    sub.append(grid(field([...cp, "nome"], "Nome do componente"),
      field([...cp, "efeito"], "Efeito", {choices: Object.keys(catalog.efeitos), rerender: true, after: (v) => {
        const rule = catalog.efeitos[v], component = get(cp);
        component.custo_base = Number.isInteger(rule.custo) ? rule.custo : 1;
        component.acao = rule["ação"] || "";
        component.alcance = rule.alcance || "";
        component.duracao = rule["duração"] || "";
        component.resistencia = rule["resistência"] || "";
        component.modo_ataque = rule.alcance === "Percepção" ? "percepcao" : rule.alcance === "À Distância" ? "distancia" : "corpo";
        delete component.caracteristica; delete component.categoria_caracteristica;
      }}), field([...cp, "graduacao"], "Graduação", {number: true, min: 1}),
      field([...cp, "custo_base"], "Custo por graduação", {number: true, min: 1,
        disabled: Number.isInteger(catalog.efeitos[c.efeito]?.custo) && c.efeito !== "Característica Aumentada"}),
      field([...cp, "detalhes"], "Opções e detalhes do efeito", {multiline: true, full: true})));
    if (c.efeito === "Característica Aumentada") {
      const category = c.categoria_caracteristica || (catalog.habilidades.includes(c.caracteristica) ? "habilidade" : "defesa");
      c.categoria_caracteristica = category;
      const targets = {habilidade: catalog.habilidades, defesa: [...Object.keys(catalog.defesas), "resistencia"],
        pericia: Object.keys(catalog.pericias), vantagem: catalog.vantagens};
      if (!c.caracteristica) { c.caracteristica = targets[category][0]; c.custo_base = category === "habilidade" ? 2 : 1; }
      sub.append(grid(field([...cp, "categoria_caracteristica"], "Tipo de característica", {
        choices: ["habilidade","defesa","pericia","vantagem"], rerender: true, after: (v) => {
          get(cp).caracteristica = targets[v][0]; get(cp).custo_base = v === "habilidade" ? 2 : 1;
        }}), field([...cp, "caracteristica"], "Característica", {choices: targets[category]}),
        field([...cp, "especializacao_caracteristica"], "Especialização concedida")));
      if (category === "pericia") sub.append(node("p", {class: "muted"}, "Cada graduação do componente concede duas graduações de perícia."));
    }
    const attack = catalog.efeitos[c.efeito]?.tipo === "Ataque" || c.ataque;
    if (attack && !c.modo_ataque) {
      const range = c.alcance || catalog.efeitos[c.efeito].alcance;
      c.modo_ataque = c.extras?.area ? "area" : range === "Percepção" ? "percepcao" : range === "À Distância" ? "distancia" : "corpo";
    }
    if (attack) sub.append(grid(field([...cp, "modo_ataque"], "Modo de ataque", {choices: ["corpo","distancia","area","percepcao"]}),
      field([...cp, "especializacao_ataque"], "Especialização da perícia de combate", {placeholder: c.nome})),
      check([...cp, "soma_forca"], "Somar Força ao efeito"));
    const params = node("details", {}, node("summary", {}, "Parâmetros e modificadores"),
      grid(...["acao","alcance","duracao","resistencia"].map((key) => field([...cp, key], label(key)))),
      check([...cp, "ataque"], "Tratar este efeito como ataque", null, true),
      renderModifiers(cp, "extras"), renderModifiers(cp, "falhas"));
    sub.append(params, computed([...cp, "custo_total"], "Custo do componente em PP: "));
    if (["Crescimento","Encolhimento"].includes(c.efeito)) {
      if (c.ativado === undefined) c.ativado = true;
      sub.append(check([...cp, "ativado"], "Efeito ativo no perfil calculado"));
    }
    panel.append(sub);
  });
  panel.append(add("Adicionar componente", () => get(path).componentes.push(newComponent(get(path).componentes))));
}
function renderModifiers(path, group, global = false) {
  const table = catalog[group];
  const container = node("div", {}, node("h4", {}, group === "extras" ? "Extras" : "Falhas"));
  const entries = get([...path, group]) || {};
  for (const [name, mod] of Object.entries(entries)) {
    if (name.startsWith("poder:")) continue;
    const mp = [...path, group, name];
    if (name === "removivel") {
      container.append(node("div", {class: "modifier-row"},
        field(mp, "Removível", {choices: [[1,"Removível"],[2,"Facilmente removível"]], numericChoice: true}),
        button("Remover", () => { delete get([...path,group])[name]; changed(true); }, "danger")));
      continue;
    }
    const row = node("div", {class: "modifier-row"});
    const choices = table[name]?.valor;
    row.append(node("div", {}, node("strong", {}, label(name.replace("personalizado:", ""))),
      node("p", {class: "muted"}, label(mod.tipo))));
    row.append(field([...mp,"valor"], "Valor", Array.isArray(choices) ?
      {choices: choices.map((v) => [v,String(v)]), numericChoice: true} : {number: true}));
    if (mod.tipo === "por_graduacao" && !global) row.append(
      field([...mp,"inicio"], "Início", {number: true, min: 1, placeholder: "Todos"}),
      field([...mp,"fim"], "Fim", {number: true, min: 1, placeholder: "Todos"}));
    row.append(button("Remover", () => { delete get([...path,group])[name]; changed(true); }, "danger"));
    container.append(row);
    if (name.startsWith("personalizado:")) container.append(grid(
      field([...mp,"detalhes"], "Aplicação do modificador", {multiline: true}),
      field([...mp,"pagina"], "Página impressa", {number: true, min: 1, max: 224}),
      field([...mp,"tipo"], "Tipo de custo", {choices: ["fixo","por_graduacao"], rerender: true, after: (v) => {
        if (v === "fixo") { delete get(mp).inicio; delete get(mp).fim; }
      }})));
  }
  let allowed = Object.keys(table).filter((n) => !["efeito alternativo","removivel","ligado"].includes(n));
  if (global) allowed = group === "extras" ? ["afeta outros","descritor variavel","ligado"] :
    ["acao aumentada","alcance reduzido","ativacao","efeito colateral","removivel"];
  const select = node("select", {"aria-label": group === "extras" ? "Extra para adicionar" : "Falha para adicionar"},
    node("option", {value: ""}, "Selecione para adicionar…"),
    ...allowed.filter((n) => !(n in entries)).map((n) => node("option", {value: n}, label(n))));
  if (!global) select.append(node("option", {value: "custom"}, "Outro modificador do livro"));
  select.addEventListener("change", () => {
    let name = select.value;
    if (!name) return;
    let mod;
    if (name === "custom") {
      const title = prompt("Nome do modificador específico:");
      if (!title?.trim()) { select.value = ""; return; }
      name = "personalizado:" + title.trim();
      if (name in get([...path,group])) { msg("error", "Esse modificador já está cadastrado."); return; }
      mod = {tipo: "por_graduacao", valor: group === "extras" ? 1 : -1, detalhes: "", pagina: 1};
    } else if (name === "removivel") mod = 1;
    else {
      const item = table[name];
      mod = {tipo: item.tipo, valor: Array.isArray(item.valor) ? item.valor[0] : item.valor};
    }
    get(path)[group] ||= {};
    get(path)[group][name] = mod;
    changed(true);
  });
  container.append(select);
  return container;
}
function renderEquipment(body) {
  body.append(computed(["estatisticas","equipamento_disponivel"], "Pontos de equipamento disponíveis: "),
    computed(["estatisticas","equipamento_gasto"], "Pontos de equipamento gastos: "));
  draft.equipamentos.forEach((e, i) => {
    const path = ["equipamentos", i];
    const panel = entry(e.nome || "Equipamento " + (i + 1), () => remove(["equipamentos"], i));
    const fields = [field([...path,"nome"], "Nome"), field([...path,"tipo"], "Tipo", {
      choices: [["item","Item ou arma"],["veiculo","Veículo"],["qg","Quartel-general"]], rerender: true, after: (v) => {
        const item = get(path);
        item.tamanho = v === "qg" ? "pequeno" : "medio";
        item.resistencia = v === "qg" ? 6 : 5;
        item.forca = 0; item.defesa = 0; item.movimento = 0; item.extras = 0;
      }})];
    if (e.tipo === "item") fields.push(field([...path,"custo"], "Custo em pontos de equipamento", {number: true, min: 1}));
    else {
      fields.push(field([...path,"tamanho"], "Tamanho", {
        choices: Object.keys(e.tipo === "veiculo" ? catalog.veiculos : catalog.qgs), rerender: true, after: (v) => {
          if (get(path).tipo === "veiculo") {
            const [,strength,resistance,defense] = catalog.veiculos[v];
            Object.assign(get(path), {forca: strength, resistencia: resistance, defesa: defense});
          }
        }}), field([...path,"resistencia"], "Resistência", {number: true, min: e.tipo === "qg" ? 6 : catalog.veiculos[e.tamanho]?.[2]}),
        field([...path,"extras"], "PE de características e poderes adicionais", {number: true, min: 0}));
      if (e.tipo === "veiculo") fields.push(field([...path,"forca"], "Força", {number: true, min: catalog.veiculos[e.tamanho]?.[1]}),
        field([...path,"defesa"], "Defesa", {number: true, min: catalog.veiculos[e.tamanho]?.[3], max: 0}),
        field([...path,"movimento"], "PE dos efeitos de movimento", {number: true, min: 0}));
    }
    fields.push(field([...path,"detalhes"], "Características e detalhes", {multiline: true, full: true}),
      field([...path,"protecao"], "Proteção concedida ao herói", {number: true, min: 0}),
      field([...path,"defesa_ativa"], "Esquiva e Aparar concedidos", {number: true, min: 0}));
    panel.append(grid(...fields), check([...path,"em_uso"], "Equipamento em uso no perfil calculado"),
      check([...path,"condicional"], "Bônus condicional (ex.: apenas contra balístico)"));
    const box = node("input", {type: "checkbox", id: "weapon-" + i});
    box.checked = !!e.ataque;
    box.addEventListener("change", () => {
      if (box.checked) get(path).ataque = {modo: "corpo", graduacao: 1, especializacao: get(path).nome, soma_forca: false};
      else delete get(path).ataque;
      changed(true);
    });
    panel.append(node("label", {class: "check", for: "weapon-" + i}, box, "Registrar ataque desta arma"));
    if (e.ataque) panel.append(grid(field([...path,"ataque","modo"], "Modo de ataque", {choices: ["corpo","distancia","area","percepcao"]}),
      field([...path,"ataque","graduacao"], "Graduação do Dano", {number: true, min: 1}),
      field([...path,"ataque","especializacao"], "Especialização de combate")),
      check([...path,"ataque","soma_forca"], "Somar Força ao Dano"));
    panel.append(computed([...path,"custo"], "Custo total em PE: "));
    body.append(panel);
  });
  body.append(add("Adicionar equipamento", () => draft.equipamentos.push({
    nome: "Novo equipamento", tipo: "item", custo: 1, detalhes: "", protecao: 0, defesa_ativa: 0, em_uso: false})));
}
function table(headers, rows) {
  return node("div", {class: "table-wrap"}, node("table", {},
    node("thead", {}, node("tr", {}, ...headers.map((h) => node("th", {scope: "col"}, h)))),
    node("tbody", {}, ...rows.map((row) => node("tr", {}, ...row.map((v) => node("td", {}, String(v ?? "—"))))))));
}
function renderReview(body) {
  if (!calculated) { body.append(node("p", {}, "Preencha a ficha para calcular os pontos.")); return; }
  const s = calculated.estatisticas, validation = calculated.validacao;
  body.append(node("h3", {}, "Distribuição dos pontos"), table(["Área","Pontos gastos"], Object.entries(calculated.custos).map(([n,v]) => [label(n),v])),
    node("h3", {}, "Defesas e iniciativa"), table(["Defesa","Bônus"], [...Object.entries(s.defesas).map(([n,v]) => [label(n),v]), ["Iniciativa",s.iniciativa]]),
    node("h3", {}, "Ataques"), table(["Ataque","Modo","Bônus","Efeito","CD"], s.ataques.map((a) => [a.nome,label(a.modo),a.bonus,a.efeito,a.cd])),
    node("h3", {}, "Perícias totais"), table(["Perícia","Especialização","Graduações","Bônus"], s.pericias_efetivas.map((p) => [label(p.nome),p.especializacao,p.graduacao,p.bonus])));
  if (!validation.erros.length) body.append(node("p", {class: "message notice"}, "Sem erros numéricos detectados neste perfil."));
  for (const [key,title,cls] of [["erros","Erros","errors"],["pendencias","Pendências",""],["avisos","Observações","notes"]]) {
    if (validation[key].length) body.append(node("section", {class: "report " + cls},
      node("h3", {}, title), node("ul", {}, ...validation[key].map((text) => node("li", {}, text)))));
  }
  body.append(node("p", {class: "muted"}, "A validação cobre as regras implementadas. Confira as pendências e a aprovação do mestre."));
}
async function library() {
  const data = await api("/api/fichas");
  $("library").replaceChildren();
  if (!data.fichas.length) $("library").append(node("p", {class: "muted"}, "Nenhuma ficha salva ainda."));
  for (const item of data.fichas) {
    const b = button("", async () => {
      if (dirty && !confirm("Abrir esta ficha e substituir o rascunho atual?")) return;
      try {
        const data = await api("/api/ficha?arquivo=" + encodeURIComponent(item.arquivo));
        revision++; clearTimeout(timer); draft = data.ficha; calculated = data.ficha; filename = data.arquivo; dirty = false;
        active = "personagem"; remember(); render(); msg("error", ""); msg("notice", "Ficha aberta. Custos e bônus recalculados.");
        $("save-state").textContent = "Ficha salva · " + filename;
      } catch (error) { msg("error", error.message); }
    }, "saved-sheet");
    b.append(node("strong", {}, item.nome || "Personagem sem nome"), node("small", {}, "NP " + item.np));
    $("library").append(b);
  }
}
async function save() {
  clearTimeout(timer);
  const chosen = prompt("Nome do arquivo da ficha:", filename || draft.nomePersonagem);
  if (!chosen?.trim()) return;
  const version = revision;
  $("save").disabled = true;
  try {
    const data = await api("/api/salvar", {arquivo: chosen.trim(), ficha: draft});
    filename = data.arquivo;
    if (version === revision) {
      dirty = false; draft = data.ficha; calculated = data.ficha;
      remember(); updateStats(); $("save-state").textContent = "Ficha salva · " + filename;
      msg("error", ""); msg("notice", "Ficha salva no computador.");
    } else msg("notice", "Versão salva. As alterações mais recentes ainda precisam ser salvas.");
    await library();
  } catch (error) { msg("error", error.message); }
  finally { $("save").disabled = false; }
}
async function exportText() {
  try {
    const data = await api("/api/exportar", {ficha: draft});
    const url = URL.createObjectURL(new Blob([data.texto], {type: "text/plain;charset=utf-8"}));
    const a = node("a", {href: url, download: (draft.nomePersonagem || "ficha").replace(/[<>:"/\\|?*]/g, "-") + ".txt"});
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { msg("error", error.message); }
}
async function boot() {
  try {
    catalog = await api("/api/catalogo");
    for (const [key,[title]] of Object.entries(sections)) {
      const b = button(title, () => { active = key; render(); if (key === "revisao") preview(); });
      b.dataset.section = key;
      $("nav").append(b);
    }
    let remembered;
    try { remembered = JSON.parse(localStorage.getItem("mm-manual-rascunho")); } catch {}
    if (remembered?.ficha?.schema_manual === 2) {
      draft = remembered.ficha; filename = remembered.arquivo || ""; dirty = remembered.dirty !== false;
      calculated = draft.estatisticas ? clone(draft) : null;
    } else {
      const data = await api("/api/nova", {nome: "Novo personagem", np: 10});
      draft = data.ficha; calculated = data.ficha; dirty = true;
    }
    render();
    await preview();
    await library();
    loading = false;
  } catch (error) {
    msg("error", error.message);
    loading = !catalog;
    $("save-state").textContent = "Não foi possível carregar. Confira o servidor e atualize a página.";
  }
}
$("editor").addEventListener("submit", (event) => event.preventDefault());
$("new").addEventListener("click", () => {
  if (loading) return;
  if (dirty && !confirm("Criar uma ficha nova e substituir o rascunho atual?")) return;
  $("new-dialog").showModal();
});
$("cancel-new").addEventListener("click", () => $("new-dialog").close());
$("new-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = new FormData(event.target);
  try {
    const data = await api("/api/nova", {nome: values.get("nome"), jogador: values.get("jogador"), np: Number(values.get("np"))});
    clearTimeout(timer); revision++; draft = data.ficha; calculated = data.ficha; filename = ""; dirty = true;
    active = "personagem"; $("new-dialog").close(); remember(); render(); msg("error", ""); msg("notice", "");
    $("save-state").textContent = "Nova ficha · ainda não salva";
  } catch (error) { msg("error", error.message); }
});
$("save").addEventListener("click", () => { if (!loading) save(); });
$("export").addEventListener("click", () => { if (!loading) exportText(); });
$("refresh").addEventListener("click", () => library().catch((error) => msg("error", error.message)));
$("validate").addEventListener("click", async () => {
  if (await preview()) { active = "revisao"; render(); }
});
window.addEventListener("beforeunload", (event) => {
  if (dirty) { event.preventDefault(); event.returnValue = ""; }
});
boot();
