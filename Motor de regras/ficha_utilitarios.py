"""Perguntas e menus do criador manual. Zero volta, sem alterar a ficha."""
from copy import deepcopy
from uuid import uuid4
import unicodedata
from calculos import HABILIDADES, custo_componente, custo_poder
from poderes import (efeitos_poderes_dicionario, extras_dict_atualizado, falhas_dict_atualizado,
    PERICIAS_ESPECIALIZADAS, VANTAGENS_GRADUADAS, pericias_por_habilidade, vantagens)
from ficha import DEFESAS, texto
from regras_ficha import TAMANHOS_VEICULO, TAMANHOS_QG

def verificar_digito(mensagem, minimo=0, maximo=None, padrao=None):
    while True:
        valor = input(mensagem).strip()
        if not valor and padrao is not None:
            return padrao
        try:
            numero = int(valor)
            if numero < minimo or (maximo is not None and numero > maximo):
                raise ValueError
            return numero
        except ValueError:
            intervalo = f"{minimo} a {maximo}" if maximo is not None else f"pelo menos {minimo}"
            print(f"Informe um número inteiro ({intervalo}).")

def escolher_da_lista(lista, rotulo=str):
    if not lista:
        print("Nenhum item disponível.")
        return None
    opcoes = list(lista)
    while True:
        for i, item in enumerate(opcoes, 1):
            print(f"{i:2} - {rotulo(item)}")
        valor = input("Número, texto para filtrar ou 0 para voltar: ").strip()
        if valor == "0":
            return None
        if valor.isdigit():
            indice = int(valor) - 1
            if 0 <= indice < len(opcoes):
                return opcoes[indice]
            print("Número fora da lista.")
        else:
            def busca(v):
                return "".join(c for c in unicodedata.normalize("NFKD", v.casefold()) if not unicodedata.combining(c))
            filtrados = [v for v in lista if busca(valor) in busca(rotulo(v))]
            if filtrados:
                opcoes = filtrados
            else:
                print("Nenhum resultado. Tente outro nome.")
                opcoes = list(lista)

def escolher_tudo(categoria):
    return escolher_da_lista(categoria, lambda v: v.get("nome", str(v)))

def listar_atributos(categoria):
    for i, item in enumerate(categoria, 1):
        print(f"{i} - {item}")

def listar_poderes(categoria):
    for i, item in enumerate(categoria, 1):
        print(f"{i} - {item['nome']}")

def listar_poderes_retornar(categoria):
    return [i["nome"] for i in categoria]

def listar_ficha(categoria, chave1, chave2):
    for item in categoria:
        print(f"{item[chave1]} | graduação: {item[chave2]}")

def validar_tudo(nome, categoria):
    return nome in categoria

def valor_texto(mensagem, atual="", obrigatorio=False):
    valor = input(f"{mensagem}" + (f" [{atual}]" if atual else "") + ": ").strip()
    if valor == "-":
        return ""
    return texto(valor or atual, mensagem, obrigatorio)

def indice_item(lista):
    item = escolher_tudo(lista)
    return None if item is None else next(i for i, v in enumerate(lista) if v is item)

def simplificar_habilidade(ficha):
    nome = escolher_da_lista(ficha.habilidades_oficiais)
    if nome is None:
        return
    atual = ficha.habilidades[nome].graduacao
    print(f"Graduação atual: {atual}. Digite ausente para uma habilidade inexistente.")
    valor = input("Nova graduação total (mínimo -5), Enter para manter: ").strip()
    if not valor:
        return
    ficha.definirHabilidade(nome, None if valor.casefold() == "ausente" else int(valor))

def menu_defesas(ficha):
    nome = escolher_da_lista(list(DEFESAS))
    if nome:
        atual = ficha.defesas[nome]
        total = ficha.estatisticas["defesas"][nome]
        print(f"Total {total}; {atual} graduações compradas. Cada graduação custa 1 PP.")
        ficha.definirDefesa(nome, verificar_digito("Nova compra total: ", padrao=atual))

def _pericia(ficha, indice=None):
    anterior = {} if indice is None else ficha.pericias[indice]
    nome = anterior.get("nome") or escolher_da_lista(ficha.pericias_oficiais)
    if nome is None:
        return
    especializacao = ""
    if nome in PERICIAS_ESPECIALIZADAS:
        especializacao = valor_texto("Especialização (ex.: Desarmado, Laser, Medicina)",
                                     anterior.get("especializacao", ""), True)
    habilidade = anterior.get("habilidade")
    if nome == "especialidade":
        print("Escolha a habilidade apropriada à especialidade.")
        habilidade = escolher_da_lista(ficha.habilidades_oficiais)
        if habilidade is None:
            return
    graduacao = verificar_digito("Graduações totais (duas custam 1 PP): ", 1,
                               padrao=anterior.get("graduação"))
    ficha.definirPericia(nome, graduacao, especializacao, indice, habilidade)

def simplificar_pericia(ficha):
    _pericia(ficha)

def _vantagem(ficha, indice=None):
    anterior = {} if indice is None else ficha.vantagens[indice]
    nome = anterior.get("nome") or escolher_da_lista(ficha.vantagens_oficiais)
    if nome is None:
        return
    gra = verificar_digito("Graduação total: ", 1, padrao=anterior.get("graduacao", 1)) if nome in VANTAGENS_GRADUADAS else 1
    detalhe = valor_texto("Escolhas/detalhes da vantagem", anterior.get("detalhe", ""))
    ficha.definirVantagem(nome, gra, detalhe, indice)

def simplificar_vantagem(ficha):
    _vantagem(ficha)

def menu_lista(ficha, categoria, autor):
    while True:
        print(f"\n{categoria.upper()}: 1 Adicionar | 2 Editar | 3 Remover | 0 Voltar")
        opc = verificar_digito("Escolha: ", 0, 3)
        if opc == 0:
            return
        if opc == 1:
            autor(ficha)
        else:
            indice = indice_item(getattr(ficha, categoria))
            if indice is not None:
                if opc == 2:
                    autor(ficha, indice)
                else:
                    ficha.remover(categoria, indice)

def ler_componente(anterior=None):
    anterior = anterior or {}
    efeito = anterior.get("efeito") or escolher_da_lista(list(efeitos_poderes_dicionario))
    if efeito is None:
        return None
    regra = efeitos_poderes_dicionario[efeito]
    nome = valor_texto("Nome do componente", anterior.get("nome", efeito), True)
    base = regra.get("custo")
    caracteristica = anterior.get("caracteristica")
    categoria_caracteristica = anterior.get("categoria_caracteristica")
    especializacao_caracteristica = anterior.get("especializacao_caracteristica", "")
    if efeito == "Característica Aumentada":
        print("Escolha a característica que será aumentada.")
        categoria_caracteristica = escolher_da_lista(["habilidade", "defesa", "pericia", "vantagem"])
        if categoria_caracteristica is None:
            return None
        catalogo = {"habilidade": list(HABILIDADES), "defesa": [*DEFESAS, "resistencia"],
                    "pericia": list(pericias_por_habilidade), "vantagem": vantagens}[categoria_caracteristica]
        caracteristica = escolher_da_lista(catalogo)
        if caracteristica is None:
            return None
        base = 2 if categoria_caracteristica == "habilidade" else 1
        if categoria_caracteristica == "pericia":
            print("Cada graduação deste componente concede duas graduações de perícia (1 PP).")
            if caracteristica in PERICIAS_ESPECIALIZADAS:
                especializacao_caracteristica = valor_texto("Especialização concedida", especializacao_caracteristica, True)
    elif type(base) is not int:
        print(f"Custo variável no catálogo: {base}. Confira no livro a opção desejada.")
        base = verificar_digito("Custo por graduação: ", 1, padrao=anterior.get("custo_base"))
    gra = verificar_digito("Graduação total: ", 1, padrao=anterior.get("graduacao", 1))
    c = {**deepcopy(anterior), "nome": nome, "efeito": efeito, "graduacao": gra,
         "custo_base": base, "extras": deepcopy(anterior.get("extras", {})),
         "falhas": deepcopy(anterior.get("falhas", {}))}
    if caracteristica:
        c["caracteristica"] = caracteristica
        c["categoria_caracteristica"] = categoria_caracteristica
        c["especializacao_caracteristica"] = especializacao_caracteristica
    c["detalhes"] = valor_texto("Opções do efeito, condições, sentidos ou imunidades", anterior.get("detalhes", ""))
    if efeito in ("Crescimento", "Encolhimento"):
        c["ativado"] = verificar_digito("Considerar este efeito ativo nos bônus? 1 Sim / 0 Não: ", 0, 1,
                                       padrao=int(anterior.get("ativado", True))) == 1
    if efeito == "Encolhimento":
        c["forca_normal"] = verificar_digito("Usa o extra Força Normal? 1 Sim / 0 Não: ", 0, 1,
                                            padrao=int(anterior.get("forca_normal", False))) == 1
        if c["forca_normal"]:
            c["extras"]["forca normal"] = {"tipo": "por_graduacao", "valor": 1}
        else:
            c["extras"].pop("forca normal", None)
    for campo, chave in (("acao", "ação"), ("alcance", "alcance"), ("duracao", "duração"), ("resistencia", "resistência")):
        c[campo] = valor_texto(campo.capitalize(), anterior.get(campo, regra.get(chave) or ""))
    c["ataque"] = regra.get("tipo") == "Ataque" or anterior.get("ataque", False)
    if c["ataque"]:
        print("Modo de ataque: corpo, distancia, area ou percepcao.")
        c["modo_ataque"] = escolher_da_lista(["corpo", "distancia", "area", "percepcao"])
        if c["modo_ataque"] is None:
            return None
        if c["modo_ataque"] in ("corpo", "distancia"):
            c["especializacao_ataque"] = valor_texto("Especialização da perícia de combate", anterior.get("especializacao_ataque", nome), True)
        c["soma_forca"] = verificar_digito("Soma Força ao efeito? 1 Sim / 0 Não: ", 0, 1,
                                         padrao=int(anterior.get("soma_forca", False))) == 1
    return c

def _variante(poder):
    opcoes = [poder, *poder.get("alternativas", [])]
    indice = indice_item(opcoes)
    return (None, None) if indice is None else (indice, opcoes[indice])

def ler_modificador(grupo, global_=False):
    tabela = extras_dict_atualizado if grupo == "extras" else falhas_dict_atualizado
    nomes = list(tabela)
    if global_:
        nomes = (["afeta outros", "descritor variavel", "ligado"] if grupo == "extras"
                 else ["acao aumentada", "alcance reduzido", "ativacao", "efeito colateral", "removivel"])
    else:
        nomes = [n for n in nomes if n not in ("removivel", "efeito alternativo", "ligado")]
        nomes.append("Outro modificador do livro")
    nome = escolher_da_lista(nomes)
    if nome is None:
        return None, None
    if nome == "Outro modificador do livro":
        nome = "personalizado:" + valor_texto("Nome do modificador específico", obrigatorio=True)
        tipo = escolher_da_lista(["fixo", "por_graduacao"])
        if tipo is None:
            return None, None
        valor = verificar_digito("Magnitude do custo (sem sinal): ", 1)
        item = {"tipo": tipo, "valor": valor if grupo == "extras" else -valor,
                "detalhes": valor_texto("Aplicação e escolhas do modificador", obrigatorio=True),
                "pagina": verificar_digito("Página impressa no livro: ", 1, 224)}
        if tipo == "por_graduacao" and verificar_digito("Aplicar só a um intervalo? 1 Sim / 0 Não: ", 0, 1) == 1:
            item["inicio"] = verificar_digito("Primeira graduação: ", 1)
            item["fim"] = verificar_digito("Última graduação: ", 1)
        return nome, item
    entrada = tabela[nome]
    if nome == "removivel":
        return nome, verificar_digito("1 Removível / 2 Facilmente Removível: ", 1, 2)
    valor = entrada["valor"]
    if isinstance(valor, list):
        valor = escolher_da_lista(valor)
        if valor is None:
            return None, None
    elif entrada["tipo"] == "fixo" and nome not in ("ligado", "inato", "incuravel", "preciso", "reversivel", "traicoeiro", "perceptivel"):
        gra = verificar_digito("Graduações do modificador fixo: ", 1, padrao=1)
        valor *= gra
    item = {"tipo": entrada["tipo"], "valor": valor}
    item["detalhes"] = valor_texto("Condição ou escolhas do modificador")
    if entrada["tipo"] == "por_graduacao" and not global_:
        if verificar_digito("Aplicar só a um intervalo? 1 Sim / 0 Não: ", 0, 1) == 1:
            item["inicio"] = verificar_digito("Primeira graduação: ", 1)
            item["fim"] = verificar_digito("Última graduação: ", 1)
    return nome, item

def menu_poder(ficha, indice):
    while True:
        poder = ficha.poderes[indice]
        print(f"\n{poder['nome']} — {poder['custo_total']} PP")
        print("1 Adicionar componente | 2 Editar componente | 3 Remover componente")
        print("4 Extra/falha de componente | 5 Extra/falha global | 6 Remover modificador")
        print("7 Adicionar alternativa | 8 Remover alternativa | 9 Escolher variante ativa")
        print("10 Nome, descritores e notas | 0 Voltar")
        print("11 Alternar arranjo comum/dinâmico")
        opc = verificar_digito("Escolha: ", 0, 11)
        if opc == 0:
            return
        novo = deepcopy(poder)
        if opc in (1, 2, 3, 4, 6):
            vi, variante = _variante(novo)
            if variante is None:
                continue
            if opc == 1:
                c = ler_componente()
                if c is not None:
                    variante["componentes"].append(c)
            else:
                ci = indice_item(variante["componentes"])
                if ci is None:
                    continue
                c = variante["componentes"][ci]
                if opc == 2:
                    editado = ler_componente(c)
                    if editado is None:
                        continue
                    variante["componentes"][ci] = editado
                elif opc == 3:
                    variante["componentes"].pop(ci)
                elif opc == 4:
                    grupo = escolher_da_lista(["extras", "falhas"])
                    if grupo is None:
                        continue
                    nome, mod = ler_modificador(grupo)
                    if nome:
                        c.setdefault(grupo, {})[nome] = mod
                elif opc == 6:
                    grupo = escolher_da_lista(["extras", "falhas"])
                    if grupo is None:
                        continue
                    nome = escolher_da_lista([n for n in c.get(grupo, {}) if not n.startswith("poder:")])
                    if nome:
                        c[grupo].pop(nome)
        elif opc == 5:
            grupo = escolher_da_lista(["extras", "falhas"])
            if grupo is None:
                continue
            nome, mod = ler_modificador(grupo, global_=True)
            if nome:
                novo.setdefault(grupo, {})[nome] = mod
                if nome == "removivel":
                    novo["indestrutivel"] = verificar_digito("Indestrutível? 1 Sim / 0 Não: ", 0, 1) == 1
        elif opc == 7:
            print("A alternativa custa 1 PP e seus efeitos devem caber no custo do primário.")
            nome = valor_texto("Nome da alternativa", obrigatorio=True)
            c = ler_componente()
            if c is None:
                continue
            novo["alternativas"].append({"nome": nome, "componentes": [c], "extras": {}, "falhas": {},
                                        "alternativas": [], "dinamico": novo.get("dinamico", False)})
        elif opc == 8:
            ai = indice_item(novo["alternativas"])
            if ai is None:
                continue
            novo["alternativas"].pop(ai)
            novo["ativo"] = 0
        elif opc == 9:
            vi, _ = _variante(novo)
            if vi is None:
                continue
            novo["ativo"] = vi
        elif opc == 10:
            novo["nome"] = valor_texto("Nome", novo["nome"], True)
            novo["descritores"] = valor_texto("Descritores", novo.get("descritores", ""))
            novo["notas"] = valor_texto("Notas", novo.get("notas", ""))
            grupo = escolher_da_lista(["Manter modificadores globais", "Remover extra global", "Remover falha global"])
            if grupo and grupo.startswith("Remover"):
                g = "extras" if "extra" in grupo else "falhas"
                nome = escolher_da_lista(list(novo.get(g, {})))
                if nome:
                    novo[g].pop(nome)
        elif opc == 11:
            dinamico = verificar_digito("1 Dinâmico / 0 Comum: ", 0, 1) == 1
            novo["dinamico"] = dinamico
            for alternativa in novo["alternativas"]:
                alternativa["dinamico"] = dinamico
            print("O arranjo dinâmico custa +1 PP no primário e 2 PP por alternativa.")
        ficha.substituirPoder(indice, novo)

def _poder(ficha, indice=None):
    if indice is None:
        ficha.adicionarPoder(valor_texto("Nome do poder ou dispositivo", obrigatorio=True))
        indice = len(ficha.poderes) - 1
    menu_poder(ficha, indice)

def simplificar_componente(ficha):
    indice = indice_item(ficha.poderes)
    if indice is not None:
        c = ler_componente()
        if c is not None:
            ficha.adicionarComponente(indice, c)

def _equipamento(ficha, indice=None):
    anterior = {} if indice is None else ficha.equipamentos[indice]
    nome = valor_texto("Nome do equipamento", anterior.get("nome", ""), True)
    tipo = anterior.get("tipo") or escolher_da_lista(["item", "veiculo", "qg"])
    if tipo is None:
        return
    item = {"nome": nome, "tipo": tipo}
    if tipo == "item":
        item["custo"] = verificar_digito("Pontos de equipamento (PE), não PP: ", 1, padrao=anterior.get("custo"))
    else:
        item["tamanho"] = escolher_da_lista(list(TAMANHOS_VEICULO if tipo == "veiculo" else TAMANHOS_QG))
        if item["tamanho"] is None:
            return
        if tipo == "veiculo":
            _, forca, resistencia, defesa = TAMANHOS_VEICULO[item["tamanho"]]
            item["forca"] = verificar_digito("Força final: ", forca, padrao=anterior.get("forca", forca))
            item["defesa"] = verificar_digito("Defesa final: ", defesa, 0, padrao=anterior.get("defesa", defesa))
            item["movimento"] = verificar_digito("Custo dos efeitos de movimento em PE: ", padrao=anterior.get("movimento", 0))
        else:
            resistencia = 6
        item["resistencia"] = verificar_digito("Resistência final: ", resistencia, padrao=anterior.get("resistencia", resistencia))
        item["extras"] = verificar_digito("PE das características/poderes adicionais: ", padrao=anterior.get("extras", 0))
    item["detalhes"] = valor_texto("Detalhes, características e efeitos", anterior.get("detalhes", ""))
    item["protecao"] = verificar_digito("Proteção concedida ao herói por este item (0 se nenhuma): ", padrao=anterior.get("protecao", 0))
    item["defesa_ativa"] = verificar_digito("Esquiva/Aparar concedidos por escudo (0 se nenhum): ", padrao=anterior.get("defesa_ativa", 0))
    item["condicional"] = verificar_digito("O bônus depende de condição (ex.: só balístico)? 1 Sim / 0 Não: ", 0, 1,
                                         padrao=int(anterior.get("condicional", False))) == 1
    item["em_uso"] = verificar_digito("Item em uso? 1 Sim / 0 Não: ", 0, 1, padrao=int(anterior.get("em_uso", False))) == 1
    if verificar_digito("Registrar ataque deste equipamento? 1 Sim / 0 Não: ", 0, 1,
                       padrao=int(bool(anterior.get("ataque")))) == 1:
        anterior_ataque = anterior.get("ataque", {})
        modo = escolher_da_lista(["corpo", "distancia", "area", "percepcao"])
        if modo is None:
            return
        item["ataque"] = {
            "modo": modo, "graduacao": verificar_digito("Graduação do efeito de Dano: ", 1, padrao=anterior_ataque.get("graduacao", 1)),
            "especializacao": valor_texto("Especialização da perícia de combate", anterior_ataque.get("especializacao", nome), True),
            "soma_forca": verificar_digito("Soma Força ao dano? 1 Sim / 0 Não: ", 0, 1,
                                         padrao=int(anterior_ataque.get("soma_forca", False))) == 1}
    def mudar(f):
        if indice is None:
            f.equipamentos.append(item)
        else:
            f.equipamentos[indice] = item
    ficha._alterar(mudar)

def _complicacao(ficha, indice=None):
    anterior = {} if indice is None else ficha.complicacoes[indice]
    tipo = valor_texto("Tipo (Motivação, Rivalidade, Segredo...)", anterior.get("tipo", ""), True)
    descricao = valor_texto("Descrição", anterior.get("descricao", ""), True)
    item = {"nome": tipo, "tipo": tipo, "descricao": descricao}
    ficha._alterar(lambda f: f.complicacoes.append(item) if indice is None else f.complicacoes.__setitem__(indice, item))

def menu_identidade(ficha):
    campo = escolher_da_lista(list(ficha.identidade))
    if campo:
        valor = valor_texto(campo, ficha.identidade[campo])
        ficha._alterar(lambda f: f.identidade.update({campo: valor}))

def resumo_texto(ficha):
    ficha.recalcular()
    s = ficha.estatisticas
    linhas = [f"HERÓI: {ficha.nomePersonagem} | Jogador: {ficha.nomeJogador}",
        f"NP {ficha.np} | {ficha.gastos:g}/{ficha.total} PP | Restantes {ficha.pontosDisponiveis:g}",
        "Custos: " + " | ".join(f"{n} {v:g}" for n, v in ficha.custos.items()),
        f"Pontos heroicos: {ficha.pontosHeroicos}", "", "IDENTIDADE E HISTÓRICO"]
    linhas += [f"{n}: {v}" for n, v in ficha.identidade.items() if v]
    linhas += ["", "HABILIDADES (base / total)"]
    linhas += [f"{n}: {h.graduacao} / {s['habilidades'][n]}" for n, h in ficha.habilidades.items()]
    linhas += ["", "DEFESAS", " | ".join(f"{n} {v}" for n, v in s["defesas"].items()),
               f"Iniciativa: {s['iniciativa']}",
               f"Tamanho {s['tamanho']} | Massa {s['massa']} | Velocidade terrestre {s['velocidade_terrestre']}",
               "", "ATAQUES"]
    linhas += [f"{a['nome']}: {a['modo']} | ataque {a['bonus']} | efeito {a['efeito']} | CD {a['cd']} ({a['resistencia']})" for a in s["ataques"]]
    linhas += ["", "PERÍCIAS"]
    linhas += [f"{p['nome']} ({p.get('especializacao', '')}): grad. {p['graduação']}, bônus {p['bonus']}, {p['custo']:g} PP" for p in ficha.pericias]
    linhas += ["Bônus totais (inclui perícias sem treinamento e aumentadas por poderes):"]
    linhas += [f"  {p['nome']} ({p['especializacao']}): {p['bonus']} — {p['graduacao']} graduações"
               for p in s["pericias_efetivas"]]
    linhas += ["", "VANTAGENS"]
    linhas += [f"{v['nome']} {v['graduacao']} | {v.get('detalhe', '')}" for v in ficha.vantagens]
    linhas += ["Vantagens efetivas com poderes: " + str(s["vantagens_efetivas"])]
    linhas += ["", "PODERES E DISPOSITIVOS"]
    for poder in ficha.poderes:
        linhas.append(f"{poder['nome']}: {poder['custo_total']} PP | descritores {poder.get('descritores', '')}")
        for i, variante in enumerate([poder, *poder["alternativas"]]):
            linhas.append(f"  {'ATIVA' if poder.get('ativo', 0) == i else 'inativa'}: {variante['nome']}")
            for c in variante["componentes"]:
                linhas.append(f"    {c['nome']} — {c['efeito']} {c['graduacao']}: {c['custo_total']} PP")
                linhas.append(f"      {c.get('acao', '')} | {c.get('alcance', '')} | {c.get('duracao', '')} | {c.get('detalhes', '')}")
                for g in ("extras", "falhas"):
                    for n, m in c.get(g, {}).items():
                        linhas.append(f"      {g}: {n} {m}")
        for g in ("extras", "falhas"):
            if poder.get(g):
                linhas.append(f"  {g} globais: {poder[g]}")
    linhas += ["", f"EQUIPAMENTO: {s['equipamento_gasto']}/{s['equipamento_disponivel']} PE"]
    linhas += [f"{e['nome']} ({e['tipo']}): {e['custo']} PE | {e.get('detalhes', '')}" for e in ficha.equipamentos]
    linhas += ["", "COMPLICAÇÕES"]
    linhas += [f"{c.get('tipo', '')}: {c.get('descricao', '')}" for c in ficha.complicacoes]
    linhas += ["", "NOTAS", ficha.notas, "", "VALIDAÇÃO"]
    v = ficha.validar()
    for g in ("erros", "pendencias", "avisos"):
        linhas += [f"{g.upper()}: {a}" for a in v[g]]
    return "\n".join(linhas)

def mostrar_ficha_atual(ficha):
    print("\n" + resumo_texto(ficha))

def mostrar_validacao(ficha):
    v = ficha.validar()
    print("Sem erros numéricos detectados." if not v["erros"] else "Corrija os erros:")
    for grupo in ("erros", "pendencias", "avisos"):
        for mensagem in v[grupo]:
            print(f"  {grupo}: {mensagem}")

def menu_ficha(ficha):
    from armazenamento import salvar, exportar_texto
    while True:
        print(f"\n{ficha.nomePersonagem} | NP {ficha.np} | {ficha.pontosDisponiveis:g} PP disponíveis")
        print("1 Habilidades | 2 Defesas | 3 Perícias | 4 Vantagens | 5 Poderes/dispositivos")
        print("6 Equipamento/veículos/QG | 7 Identidade/histórico | 8 Complicações | 9 Ver ficha")
        print("10 Validar | 11 Salvar | 12 Exportar texto | 13 NP/pontos | 14 Notas | 0 Sair")
        try:
            opc = verificar_digito("Escolha: ", 0, 14)
            if opc == 0:
                if verificar_digito("Salvar antes de sair? 1 Sim / 0 Não: ", 0, 1) == 1:
                    salvar(ficha, valor_texto("Nome do arquivo", ficha.nomePersonagem, True))
                return
            if opc == 1:
                simplificar_habilidade(ficha)
            elif opc == 2:
                menu_defesas(ficha)
            elif opc in (3, 4, 5, 6, 8):
                categoria, autor = {3: ("pericias", _pericia), 4: ("vantagens", _vantagem),
                    5: ("poderes", _poder), 6: ("equipamentos", _equipamento),
                    8: ("complicacoes", _complicacao)}[opc]
                menu_lista(ficha, categoria, autor)
            elif opc == 7:
                menu_identidade(ficha)
            elif opc == 9:
                mostrar_ficha_atual(ficha)
            elif opc == 10:
                mostrar_validacao(ficha)
            elif opc == 11:
                salvar(ficha, valor_texto("Nome do arquivo", ficha.nomePersonagem, True))
            elif opc == 12:
                caminho = exportar_texto(ficha, valor_texto("Nome do arquivo", ficha.nomePersonagem, True))
                print(f"Exportado: {caminho}")
            elif opc == 13:
                np = verificar_digito("NP: ", 1, 30, padrao=ficha.np)
                extra = verificar_digito("PP adicionais concedidos pelo mestre: ", padrao=ficha.pontosExtras)
                heroicos = verificar_digito("Pontos heroicos: ", padrao=ficha.pontosHeroicos)
                ficha._alterar(lambda f: f.__dict__.update(np=np, pontosExtras=extra, pontosHeroicos=heroicos))
            elif opc == 14:
                notas = valor_texto("Notas (use - para limpar)", ficha.notas)
                ficha._alterar(lambda f: setattr(f, "notas", notas))
        except (ValueError, KeyError, IndexError, TypeError, OSError) as erro:
            print(f"Não foi possível aplicar a alteração: {erro}")
        except (KeyboardInterrupt, EOFError):
            print("\nEntrada interrompida. Preservando um rascunho antes de sair.")
            try:
                salvar(ficha, f"rascunho-{uuid4().hex}.json")
            except (ValueError, OSError) as erro:
                print(f"Não foi possível salvar o rascunho: {erro}")
            return

# Compatibilidade com os nomes antigos dos utilitários.
def calcular_custosComponente(custo_base, graduacao, mod_g, mod_f, inicio=None, fim=None):
    return custo_componente(custo_base, graduacao, (
        {"tipo": "por_graduacao", "valor": mod_g, "inicio": inicio, "fim": fim},
        {"tipo": "fixo", "valor": mod_f}))

def calcular_custosPoderes(poder):
    from regras_ficha import normalizar_poder
    normalizar_poder(poder)
    return custo_poder(poder)

