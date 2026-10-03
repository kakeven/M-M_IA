"""Custos e validações da ficha manual, conferidos no PDF local.

Referências (páginas impressas): 24-27, 55-59, 61, 77-87, 129-145,
155, 164-165, 168 e 224. Decisões narrativas permanecem com o mestre.
"""
from copy import deepcopy
from math import ceil
from itertools import product

from calculos import custo_componente, custo_poder, modificadores_componente
from poderes import (efeitos_poderes_dicionario, extras_dict_atualizado,
    falhas_dict_atualizado, pericias_por_habilidade, VANTAGENS_GRADUADAS,
    LIMITES_VANTAGENS, PERICIAS_ESPECIALIZADAS, VANTAGENS_POR_ESCOLHA, vantagens as catalogo_vantagens)
from ficha import DEFESAS, HABILIDADES, inteiro, texto

TAMANHOS_VEICULO = {
    "medio": (0, 0, 5, 0), "grande": (1, 4, 7, -2),
    "enorme": (2, 8, 9, -4), "descomunal": (3, 12, 11, -6),
    "colossal": (4, 16, 13, -8), "incrivel": (5, 20, 15, -10),
}
TAMANHOS_QG = dict(zip(
    ("minusculo", "miudo", "diminuto", "minimo", "pequeno", "medio",
     "grande", "enorme", "imenso", "colossal", "impressionante"), range(-4, 7)))


def _modificadores(registro, componente=False):
    for grupo, tabela in (("extras", extras_dict_atualizado), ("falhas", falhas_dict_atualizado)):
        entradas = registro.setdefault(grupo, {})
        if not isinstance(entradas, dict):
            raise ValueError("Extras e falhas devem ser objetos.")
        for nome, item in list(entradas.items()):
            if nome.startswith("poder:"):
                entradas.pop(nome)  # refeito a partir da compra global, sem duplicação
                continue
            if nome.startswith("personalizado:"):
                if not isinstance(item, dict) or item.get("tipo") not in ("fixo", "por_graduacao"):
                    raise ValueError("Informe o tipo de custo do modificador personalizado.")
                if type(item.get("valor")) is not int or (grupo == "extras" and item["valor"] < 0) or (grupo == "falhas" and item["valor"] >= 0):
                    raise ValueError("Valor inválido para modificador personalizado.")
                texto(item.get("detalhes", ""), "Justificativa do modificador", True)
                inteiro(item.get("pagina"), "Página impressa do modificador", 1, 224)
                if item["tipo"] == "fixo" and (item.get("inicio") is not None or item.get("fim") is not None):
                    raise ValueError("Modificadores fixos não têm intervalos.")
                continue
            if nome not in tabela:
                raise ValueError(f"Modificador desconhecido: {nome}")
            if nome == "removivel":
                if componente:
                    raise ValueError("Aplique Removível ao poder ou dispositivo inteiro.")
                valor = item.get("valor") if isinstance(item, dict) else item
                entradas[nome] = inteiro(valor, "Removível", 1, 2)
                continue
            if not isinstance(item, dict):
                item = {"valor": item}
            item = deepcopy(item)
            item["tipo"] = tabela[nome]["tipo"]
            valor = item.get("valor")
            if type(valor) is not int or (grupo == "extras" and valor < 0) or (grupo == "falhas" and valor >= 0):
                raise ValueError(f"Valor inválido para {nome}.")
            permitidos = tabela[nome]["valor"]
            if nome in ("inato", "incuravel", "preciso", "reversivel", "traicoeiro", "perceptivel", "ligado") and valor != permitidos:
                raise ValueError(f"{nome}: o valor fixo é {permitidos}.")
            if isinstance(permitidos, list) and valor not in permitidos:
                raise ValueError(f"Valor não previsto para {nome}: {valor}")
            if item["tipo"] == "fixo" and (item.get("inicio") is not None or item.get("fim") is not None):
                raise ValueError("Custos fixos não têm intervalo de graduações.")
            entradas[nome] = item


def normalizar_poder(poder, eh_alternativa=False):
    if not isinstance(poder, dict):
        raise ValueError("Poder deve ser um registro.")
    poder["nome"] = texto(poder.get("nome", ""), "Nome do poder", True, 100)
    poder.setdefault("componentes", [])
    poder.setdefault("alternativas", [])
    if not isinstance(poder["componentes"], list) or any(not isinstance(c, dict) for c in poder["componentes"]):
        raise ValueError("Componentes devem ser uma lista de registros.")
    if not isinstance(poder["alternativas"], list):
        raise ValueError("Alternativas devem ser uma lista.")
    inteiro(poder.get("ativo", 0), "Variante ativa", 0, len(poder["alternativas"]))
    _modificadores(poder)
    for alternativa in poder["alternativas"]:
        if alternativa.get("alternativas"):
            raise ValueError("Um efeito alternativo não pode conter outro arranjo.")
        normalizar_poder(alternativa, eh_alternativa=True)
    for variante in [poder, *poder["alternativas"]]:
        nomes = set()
        for c in variante["componentes"]:
            c["nome"] = texto(c.get("nome", ""), "Nome do componente", True, 100)
            if c["nome"].casefold() in nomes:
                raise ValueError("Use nomes diferentes para os componentes da mesma variante.")
            nomes.add(c["nome"].casefold())
            if c.get("efeito") not in efeitos_poderes_dicionario:
                raise ValueError(f"Efeito desconhecido: {c.get('efeito')}")
            inteiro(c.get("graduacao"), "Graduação do efeito", 1)
            inteiro(c.get("custo_base"), "Custo base", 1)
            _modificadores(c, componente=True)
            for grupo in ("extras", "falhas"):
                for nome, item in poder[grupo].items():
                    if isinstance(item, dict) and item["tipo"] == "por_graduacao":
                        c[grupo][f"poder:{nome}"] = deepcopy(item)
            c["custo_total"] = custo_componente(c["custo_base"], c["graduacao"], modificadores_componente(c))
            if c.get("efeito") == "Característica Aumentada" and c.get("caracteristica"):
                alvo = c["caracteristica"]
                categoria = c.get("categoria_caracteristica", "habilidade" if alvo in HABILIDADES else "defesa")
                catalogo = {"habilidade": HABILIDADES, "defesa": (*DEFESAS, "resistencia"),
                            "pericia": pericias_por_habilidade, "vantagem": catalogo_vantagens}.get(categoria)
                if catalogo is None or alvo not in catalogo:
                    raise ValueError("Característica aumentada: escolha uma característica válida.")
                esperado = 2 if categoria == "habilidade" else 1
                if c["custo_base"] != esperado:
                    raise ValueError(f"Aumentar {alvo} custa {esperado} por graduação.")
            for nome, item in c["extras"].items():
                if nome == "acurado" and item["valor"] < 1:
                    raise ValueError("Acurado exige ao menos uma graduação.")
        if poder["alternativas"]:
            if any(c.get("duracao", efeitos_poderes_dicionario[c["efeito"]].get("duração")) == "Permanente"
                   for c in variante["componentes"]):
                raise ValueError("Efeitos permanentes não podem fazer parte de um arranjo alternativo.")
        for c in variante["componentes"]:
            if "forca normal" in c.get("extras", {}) and c["efeito"] != "Encolhimento":
                raise ValueError("Força Normal só se aplica a Encolhimento.")
            c["forca_normal"] = "forca normal" in c.get("extras", {})
        if "ligado" in variante.get("extras", {}):
            alcances = {c.get("alcance", efeitos_poderes_dicionario[c["efeito"]].get("alcance"))
                        for c in variante["componentes"]}
            if len(alcances) > 1:
                raise ValueError("Efeitos Ligados devem operar ao mesmo alcance.")
    for a in poder["alternativas"]:
        a["custo_total"] = custo_poder(a, eh_alternativa=True)
    poder["custo_total"] = custo_poder(poder, eh_alternativa=eh_alternativa)


def custo_equipamento(item):
    texto(item.get("nome", ""), "Nome do equipamento", True, 100)
    inteiro(item.get("protecao", 0), "Proteção do equipamento")
    inteiro(item.get("defesa_ativa", 0), "Defesa ativa do equipamento")
    tipo = item.get("tipo", "item")
    if tipo == "item":
        return inteiro(item.get("custo"), "Pontos de equipamento", 1)
    extras = inteiro(item.get("extras", 0), "Custo de características e poderes adicionais")
    if tipo == "veiculo":
        tamanho = item.get("tamanho")
        if tamanho not in TAMANHOS_VEICULO:
            raise ValueError("Tamanho de veículo desconhecido.")
        custo, forca, resistencia, defesa = TAMANHOS_VEICULO[tamanho]
        aumento_forca = inteiro(item.get("forca", forca), "Força do veículo", forca) - forca
        aumento_res = inteiro(item.get("resistencia", resistencia), "Resistência do veículo", resistencia) - resistencia
        aumento_def = inteiro(item.get("defesa", defesa), "Defesa do veículo", defesa, 0) - defesa
        movimento = inteiro(item.get("movimento", 0), "Custo dos efeitos de movimento")
        return max(1, custo + aumento_forca + aumento_res + aumento_def + movimento + extras)
    if tipo == "qg":
        if item.get("tamanho") not in TAMANHOS_QG:
            raise ValueError("Tamanho de QG desconhecido.")
        res = inteiro(item.get("resistencia", 6), "Resistência do QG", 6)
        return max(1, TAMANHOS_QG[item["tamanho"]] + ceil((res - 6) / 2) + extras)
    raise ValueError("Tipo de equipamento desconhecido.")


def _componentes_ativos(ficha, selecoes=None):
    for i, poder in enumerate(ficha.poderes):
        ativo = (selecoes or {}).get(i, poder.get("ativo", 0))
        variante = poder if ativo == 0 else poder["alternativas"][ativo - 1]
        yield from (c for c in variante["componentes"] if c.get("ativado", True))


def estatisticas(ficha, selecoes=None):
    habilidades = {n: h.graduacao for n, h in ficha.habilidades.items()}
    vantagens = {}
    for v in ficha.vantagens:
        vantagens[v["nome"]] = vantagens.get(v["nome"], 0) + v["graduacao"]
    componentes = list(_componentes_ativos(ficha, selecoes))
    pericias_aumentadas = {}
    for c in componentes:
        if c["efeito"] == "Característica Aumentada":
            alvo, categoria = c.get("caracteristica"), c.get("categoria_caracteristica")
            if categoria == "vantagem":
                vantagens[alvo] = vantagens.get(alvo, 0) + c["graduacao"]
            if categoria == "pericia":
                chave = chave_pericia(alvo, c.get("especializacao_caracteristica", ""))
                pericias_aumentadas[chave] = pericias_aumentadas.get(chave, 0) + c["graduacao"] * 2
    bonus_defesa = dict.fromkeys((*DEFESAS, "resistencia"), 0)
    bonus_defesa["resistencia"] = vantagens.get("rolamento defensivo", 0)
    armadura = max((inteiro(e.get("protecao", 0), "Proteção do equipamento")
                    for e in ficha.equipamentos if e.get("em_uso")), default=0)
    bonus_defesa["resistencia"] += armadura
    escudo = max((inteiro(e.get("defesa_ativa", 0), "Defesa ativa do equipamento")
                  for e in ficha.equipamentos if e.get("em_uso")), default=0)
    bonus_defesa["esquiva"] += escudo
    bonus_defesa["aparar"] += escudo
    bonus_pericias = {"furtividade": 0, "intimidacao": 0}
    tamanho, massa, velocidade = -2, 2, 0
    for c in componentes:
        if c["efeito"] in ("Proteção", "Campo de Força"):
            bonus_defesa["resistencia"] += c["graduacao"]
        if c["efeito"] == "Característica Aumentada":
            alvo = c.get("caracteristica")
            categoria = c.get("categoria_caracteristica", "habilidade" if alvo in habilidades else "defesa")
            if categoria == "habilidade" and alvo in habilidades and habilidades[alvo] is not None:
                habilidades[alvo] += c["graduacao"]
            elif categoria == "defesa" and alvo in bonus_defesa:
                bonus_defesa[alvo] += c["graduacao"]
        if c["efeito"] == "Crescimento":
            gra = c["graduacao"]
            for alvo in ("forca", "vigor"):
                if habilidades[alvo] is not None:
                    habilidades[alvo] += gra
            if habilidades["vigor"] is None:
                bonus_defesa["resistencia"] += gra
            for alvo in ("esquiva", "aparar"):
                bonus_defesa[alvo] -= ceil(gra / 2)
            bonus_pericias["furtividade"] -= gra
            bonus_pericias["intimidacao"] += gra // 2
            tamanho += gra // 4
            massa += gra
            velocidade += gra // 8
        if c["efeito"] == "Encolhimento":
            gra = c["graduacao"]
            tamanho -= gra // 4
            if not c.get("forca_normal"):
                if habilidades["forca"] is not None:
                    habilidades["forca"] -= gra // 4
                velocidade -= gra // 8
                bonus_pericias["intimidacao"] -= gra // 2
            for alvo in ("esquiva", "aparar"):
                bonus_defesa[alvo] += gra // 2
            bonus_pericias["furtividade"] += gra
    defesas = {}
    for nome, h in {**DEFESAS, "resistencia": "vigor"}.items():
        base = habilidades[h]
        if nome == "resistencia" and base is None:
            base = 0  # objetos/construtos obtêm Resistência de Proteção
        defesas[nome] = None if base is None else base + ficha.defesas.get(nome, 0) + bonus_defesa[nome]
    if any(habilidades[n] is None for n in ("intelecto", "presenca", "prontidao")):
        defesas["vontade"] = None
    if habilidades["prontidao"] is None:
        defesas["esquiva"] = defesas["aparar"] = None
    ataques = []
    armas = []
    for e in ficha.equipamentos:
        if e.get("ataque"):
            a = e["ataque"]
            if not isinstance(a, dict):
                raise ValueError("Ataque do equipamento deve ser um objeto.")
            gra = inteiro(a.get("graduacao"), "Graduação do ataque do equipamento", 1)
            armas.append({"nome": e["nome"], "efeito": "Dano", "graduacao": gra,
                "modo_ataque": a.get("modo", "corpo"), "soma_forca": a.get("soma_forca", False),
                "especializacao_ataque": a.get("especializacao", e["nome"]),
                "resistencia": a.get("resistencia", "Resistência"), "extras": {}, "ataque": True})
    for c in [*componentes, *armas]:
        regra = efeitos_poderes_dicionario[c["efeito"]]
        if regra.get("tipo") != "Ataque" and not c.get("ataque"):
            continue
        modo = c.get("modo_ataque")
        if modo is None:
            alcance = c.get("alcance", regra.get("alcance"))
            modo = "percepcao" if alcance == "Percepção" else ("distancia" if alcance == "À Distância" else "corpo")
            if "area" in c.get("extras", {}) or "poder:area" in c.get("extras", {}):
                modo = "area"
        if modo not in ("corpo", "distancia", "area", "percepcao"):
            raise ValueError("Modo de ataque inválido.")
        bonus = None
        efeito = c["graduacao"]
        if c.get("soma_forca"):
            efeito += habilidades["forca"] or 0
        if modo in ("corpo", "distancia"):
            h = "luta" if modo == "corpo" else "destreza"
            pericia = "combate a corpo-a-corpo" if modo == "corpo" else "combate a distancia"
            treinamento = max((p["graduação"] for p in ficha.pericias
                if p["nome"] == pericia and p.get("especializacao", "").casefold() ==
                c.get("especializacao_ataque", c["nome"]).casefold()), default=0)
            treinamento += pericias_aumentadas.get(chave_pericia(pericia, c.get("especializacao_ataque", c["nome"])), 0)
            bonus = None if habilidades[h] is None else habilidades[h] + treinamento + vantagens.get(
                "ataque corpo a corpo" if modo == "corpo" else "ataque a distancia", 0)
            acurado = sum(m["valor"] for nome, m in c.get("extras", {}).items()
                          if nome in ("acurado", "poder:acurado"))
            if bonus is not None:
                bonus += acurado * 2
        ataques.append({"nome": c["nome"], "modo": modo, "bonus": bonus, "efeito": efeito,
                        "resistencia": c.get("resistencia", regra.get("resistência")),
                        "cd": (15 if c["efeito"] in ("Dano", "Golpe", "Raio", "Aura de Energia",
                               "Controle de Energia", "Magia", "Rajada Mental") else 10) + efeito})
    luta, forca = habilidades["luta"], habilidades["forca"]
    desarmado = max((p["graduação"] for p in ficha.pericias if p["nome"] == "combate a corpo-a-corpo"
                    and p.get("especializacao", "").casefold() == "desarmado"), default=0)
    desarmado += pericias_aumentadas.get(chave_pericia("combate a corpo-a-corpo", "desarmado"), 0)
    if luta is not None and forca is not None and habilidades["destreza"] is not None:
        ataques.insert(0, {"nome": "Desarmado", "modo": "corpo",
            "bonus": luta + desarmado + vantagens.get("ataque corpo a corpo", 0), "efeito": forca,
            "resistencia": "Resistência", "cd": 15 + forca})
    pericias_efetivas = []
    compras = {chave_pericia(p["nome"], p.get("especializacao", "")): p for p in ficha.pericias}
    chaves = set(compras) | set(pericias_aumentadas)
    chaves.update(chave_pericia(n) for n in pericias_por_habilidade if n not in PERICIAS_ESPECIALIZADAS)
    for chave in sorted(chaves):
        nome, especializacao = chave.split("|", 1)
        compra = compras.get(chave, {})
        habilidade = compra.get("habilidade", pericias_por_habilidade[nome])
        ranks = compra.get("graduação", 0) + pericias_aumentadas.get(chave, 0)
        base = habilidades[habilidade]
        pericias_efetivas.append({"nome": nome, "especializacao": especializacao, "graduacao": ranks,
            "bonus": None if base is None else base + ranks + bonus_pericias.get(nome, 0)})
    return {"habilidades": habilidades, "defesas": defesas, "bonus_pericias": bonus_pericias,
            "pericias_aumentadas": pericias_aumentadas, "pericias_efetivas": pericias_efetivas,
            "vantagens_efetivas": vantagens,
            "tamanho": tamanho, "massa": massa, "velocidade_terrestre": velocidade,
            "iniciativa": None if habilidades["agilidade"] is None else habilidades["agilidade"] +
            4 * vantagens.get("iniciativa aprimorada", 0), "ataques": ataques,
            "equipamento_disponivel": 5 * vantagens.get("equipamento", 0),
            "equipamento_gasto": sum(e["custo"] for e in ficha.equipamentos)}


def chave_pericia(nome, especializacao=""):
    return nome + "|" + especializacao.casefold()


def validar_ficha(ficha):
    erros, pendencias, avisos = [], [], []
    s = ficha.estatisticas
    limite = ficha.np * 2
    if ficha.pontosDisponiveis < 0:
        erros.append(f"Orçamento excedido em {-ficha.pontosDisponiveis:g} pontos.")
    if ficha.gastos % 1:
        pendencias.append("Complete o par de graduações de perícia: o gasto total tem meio ponto.")
    if len(ficha.complicacoes) < 2:
        pendencias.append("Escolha pelo menos duas complicações.")
    if not any(c.get("tipo", "").casefold() in ("motivacao", "motivação") for c in ficha.complicacoes):
        pendencias.append("Inclua uma complicação de Motivação.")
    vistos = set()
    for p in ficha.pericias:
        chave = (p["nome"], p.get("especializacao", "").casefold())
        if chave in vistos:
            erros.append(f"Perícia duplicada: {p['nome']} ({chave[1]}).")
        vistos.add(chave)
        if p["nome"] in PERICIAS_ESPECIALIZADAS and not p.get("especializacao"):
            pendencias.append(f"Defina a especialização de {p['nome']}.")
        if p["bonus"] is None:
            erros.append(f"{p['nome']}: a habilidade associada está ausente.")
        elif p["bonus"] > ficha.np + 10:
            erros.append(f"{p['nome']}: bônus {p['bonus']} excede NP + 10 ({ficha.np + 10}).")
    for nome, h in pericias_por_habilidade.items():
        if s["habilidades"][h] is not None and s["habilidades"][h] > ficha.np + 10:
            erros.append(f"{nome} sem treinamento excede NP + 10 pela habilidade {h}.")
    for v in ficha.vantagens:
        maximo = LIMITES_VANTAGENS.get(v["nome"], 1 if v["nome"] not in VANTAGENS_GRADUADAS else None)
        if v["nome"] == "sorte":
            maximo = ficha.np // 2
        if maximo is not None and v["graduacao"] > maximo:
            erros.append(f"{v['nome']}: graduação máxima {maximo}.")
        if v["nome"] in ("beneficio", "capanga", "parceiro", "idiomas", "fascinar",
                          "maestria em pericia", "segunda chance", "critico aprimorado") and not v.get("detalhe"):
            pendencias.append(f"Descreva as escolhas da vantagem {v['nome']}.")
    vistos_vantagens = set()
    for v in ficha.vantagens:
        chave = (v["nome"], v.get("detalhe", "").casefold() if v["nome"] in VANTAGENS_POR_ESCOLHA else "")
        if chave in vistos_vantagens:
            erros.append(f"Vantagem duplicada: {v['nome']}.")
        vistos_vantagens.add(chave)
    if s["equipamento_gasto"] > s["equipamento_disponivel"]:
        erros.append(f"Equipamento: {s['equipamento_gasto']} gastos para {s['equipamento_disponivel']} disponíveis. Compre Equipamento.")
    if any(h.graduacao is None for h in ficha.habilidades.values()):
        pendencias.append("Habilidades ausentes exigem aprovação do mestre e conferência das imunidades.")
    # Verifica cada alternativa isoladamente, inclusive suas próprias melhorias.
    for indice, poder in enumerate(ficha.poderes):
        if not poder["componentes"]:
            pendencias.append(f"{poder['nome']}: adicione ao menos um componente.")
        if poder.get("dinamico") or any(a.get("dinamico") for a in poder["alternativas"]):
            pendencias.append(f"{poder['nome']}: a alocação simultânea do arranjo dinâmico exige revisão do mestre.")
        for ativo, variante in enumerate([poder, *poder["alternativas"]]):
            estado = estatisticas(ficha, {indice: ativo})
            _limites_combate(estado, limite, ficha.np, erros, variante["nome"])
            for c in variante["componentes"]:
                custo_catalogo = efeitos_poderes_dicionario[c["efeito"]].get("custo")
                if type(custo_catalogo) is int and c["custo_base"] != custo_catalogo:
                    pendencias.append(f"{c['nome']}: custo base {c['custo_base']} difere do catálogo ({custo_catalogo}); revise a compra antiga.")
                if c["efeito"] == "Característica Aumentada" and not c.get("caracteristica"):
                    pendencias.append(f"{c['nome']}: informe a característica aumentada.")
                if c.get("categoria_caracteristica") == "pericia" and c.get("caracteristica") in PERICIAS_ESPECIALIZADAS and not c.get("especializacao_caracteristica"):
                    pendencias.append(f"{c['nome']}: informe a especialização da perícia aumentada.")
                if c["efeito"] in ("Variável", "Forma Alternativa", "Imitar", "Metamorfo", "Supervelocidade", "Absorção de Energia"):
                    pendencias.append(f"{c['nome']}: alterações de características e formas exigem revisão; não entram automaticamente nos bônus.")
                if not c.get("ativado", True):
                    pendencias.append(f"{c['nome']}: efeito desligado no perfil; ative-o para conferir seus limites.")
                if not c.get("detalhes") and c["efeito"] in ("Aflição", "Imunidade", "Sentidos", "Movimento", "Invocar", "Compreender"):
                    pendencias.append(f"{c['nome']}: descreva as opções do efeito {c['efeito']}.")
                for g in ("extras", "falhas"):
                    for nome in c.get(g, {}):
                        if nome.startswith("personalizado:"):
                            pendencias.append(f"{c['nome']}: confira a compatibilidade do modificador {nome.split(':', 1)[1]} na página {c[g][nome]['pagina']}.")
                    if "efeito alternativo" in c.get(g, {}):
                        pendencias.append(f"{c['nome']}: substitua o extra antigo Efeito Alternativo por uma variante do arranjo.")
                if c.get("modo_ataque") is None and (c.get("extras") or c.get("falhas")):
                    pendencias.append(f"{c['nome']}: confira o alcance e o modo de ataque após os modificadores.")
        if not poder.get("descritores"):
            avisos.append(f"{poder['nome']}: informe os descritores para facilitar o uso em jogo.")
        if "efeito alternativo" in poder.get("extras", {}):
            pendencias.append(f"{poder['nome']}: o extra antigo Efeito Alternativo não define uma alternativa completa.")
    _limites_combate(s, limite, ficha.np, erros, "Ficha")
    combinacoes = 1
    for p in ficha.poderes:
        combinacoes *= 1 + len(p["alternativas"])
    if combinacoes <= 512:
        for escolhas in product(*(range(1 + len(p["alternativas"])) for p in ficha.poderes)):
            estado = estatisticas(ficha, dict(enumerate(escolhas)))
            _limites_combate(estado, limite, ficha.np, erros, "Combinação de poderes")
            for p in ficha.pericias:
                h = estado["habilidades"][p["habilidade"]]
                bonus = None if h is None else h + p["graduação"] + estado["bonus_pericias"].get(p["nome"], 0)
                if bonus is not None and bonus > ficha.np + 10:
                    erros.append(f"Combinação de poderes: {p['nome']} tem bônus {bonus}, limite {ficha.np + 10}.")
            for p in estado["pericias_efetivas"]:
                if p["bonus"] is not None and p["bonus"] > ficha.np + 10:
                    erros.append(f"Combinação de poderes: {p['nome']} ({p['especializacao']}) tem bônus {p['bonus']}, limite {ficha.np + 10}.")
            for nome, graduacao in estado["vantagens_efetivas"].items():
                maximo = LIMITES_VANTAGENS.get(nome, 1 if nome not in VANTAGENS_GRADUADAS else None)
                if nome == "sorte":
                    maximo = ficha.np // 2
                if nome not in VANTAGENS_POR_ESCOLHA and maximo is not None and graduacao > maximo:
                    erros.append(f"Combinação de poderes: {nome} tem graduação {graduacao}, limite {maximo}.")
    else:
        pendencias.append("Mais de 512 combinações de arranjos: confira as combinações simultâneas com o mestre.")
    for p in ficha.pericias:
        if p.get("habilidade") != pericias_por_habilidade[p["nome"]] and p["nome"] != "especialidade":
            erros.append(f"{p['nome']}: habilidade base incorreta.")
    for e in ficha.equipamentos:
        if e.get("condicional") and e.get("em_uso"):
            pendencias.append(f"{e['nome']}: os bônus do equipamento são condicionais; revise o perfil para cada situação.")
        if e.get("tipo") == "item" and e.get("protecao", 0) + 2 * e.get("defesa_ativa", 0) > e["custo"] and not e.get("condicional"):
            erros.append(f"{e['nome']}: o custo informado não cobre a Proteção/defesas deste item.")
        if e.get("ataque"):
            pendencias.append(f"{e['nome']}: confira no livro o custo da arma e seus modificadores; o custo foi informado manualmente.")
    avisos.append("Compatibilidade de extras/falhas, condições situacionais e aprovação narrativa devem ser conferidas pelo mestre.")
    return {"erros": list(dict.fromkeys(erros)), "pendencias": list(dict.fromkeys(pendencias)),
            "avisos": list(dict.fromkeys(avisos)), "pronta": not erros and not pendencias,
            "validacao_completa": False}


def _limites_combate(s, limite, np, erros, origem):
    for a, b in (("esquiva", "resistencia"), ("aparar", "resistencia"), ("fortitude", "vontade")):
        if s["defesas"][a] is not None and s["defesas"][b] is not None:
            total = s["defesas"][a] + s["defesas"][b]
            if total > limite:
                erros.append(f"{origem}: {a} + {b} = {total}, limite {limite}.")
    for ataque in s["ataques"]:
        if ataque["modo"] in ("area", "percepcao"):
            if ataque["efeito"] > np:
                erros.append(f"{origem}: {ataque['nome']} sem teste de ataque tem efeito {ataque['efeito']}, limite NP {np}.")
        elif ataque["bonus"] is None:
            erros.append(f"{origem}: {ataque['nome']} exige uma habilidade ausente.")
        elif ataque["bonus"] + ataque["efeito"] > limite:
            erros.append(f"{origem}: ataque + efeito de {ataque['nome']} = {ataque['bonus'] + ataque['efeito']}, limite {limite}.")
