"""Modelo da ficha manual; recalcula as compras antes de aplicar alterações."""
from copy import deepcopy
from calculos import HABILIDADES, custo_habilidade, custo_graduacoes_pericia, custo_vantagem, orcamento, poder_com_modificador
from poderes import (efeitos_poderes_dicionario, efeitos_poderes_lista, extras_dict_atualizado,
    falhas_dict_atualizado, vantagens, pericias_por_habilidade, PERICIAS_ESPECIALIZADAS,
    VANTAGENS_GRADUADAS, LIMITES_VANTAGENS, VANTAGENS_POR_ESCOLHA)

DEFESAS = {"esquiva": "agilidade", "aparar": "luta", "fortitude": "vigor", "vontade": "prontidao"}

def inteiro(valor, nome, minimo=0, maximo=None):
    if type(valor) is not int or valor < minimo or (maximo is not None and valor > maximo):
        intervalo = f" de {minimo} a {maximo}" if maximo is not None else f" ≥ {minimo}"
        raise ValueError(f"{nome}: informe um número inteiro{intervalo}.")
    return valor

def texto(valor, nome, obrigatorio=False, limite=4000):
    if not isinstance(valor, str) or len(valor) > limite:
        raise ValueError(f"{nome}: informe um texto com até {limite} caracteres.")
    valor = valor.strip()
    if obrigatorio and not valor:
        raise ValueError(f"Preencha {nome}.")
    return valor

class Habilidade:
    def __init__(self, nome, graduacao):
        self.nome, self.graduacao = nome, graduacao
    def custo(self, gra):
        return custo_habilidade(gra)

class Pericia:
    def __init__(self, nome, valor):
        self.nome, self.graduacao = nome, inteiro(valor, "Pontos de perícia") * 2
    @property
    def custo(self):
        return custo_graduacoes_pericia(self.graduacao)

class Ficha:
    def __init__(self, np, nomeJogador, nomePersonagem):
        self.np = inteiro(np, "NP", 1, 30)
        self.nomeJogador = texto(nomeJogador, "Nome do jogador", limite=100)
        self.nomePersonagem = texto(nomePersonagem, "Nome do personagem", True, 100)
        self.pontosExtras, self.pontosHeroicos = 0, 1
        self.habilidades = {nome: Habilidade(nome, 0) for nome in HABILIDADES}
        self.defesas = dict.fromkeys(DEFESAS, 0)
        self.pericias, self.vantagens, self.poderes = [], [], []
        self.equipamentos, self.complicacoes = [], []
        self.notas = ""
        self.identidade = dict.fromkeys(("nome_civil", "identidade", "genero", "idade", "altura",
            "peso", "olhos", "cabelo", "grupo", "base", "origem", "aparencia", "personalidade",
            "objetivos", "historico"), "")
        self.habilidades_oficiais = list(HABILIDADES)
        self.pericias_oficiais = list(pericias_por_habilidade)
        self.vantagens_oficiais = vantagens
        self.poderes_lista, self.poderes_dict = efeitos_poderes_lista, efeitos_poderes_dicionario
        self.recalcular()

    def _alterar(self, operacao):
        """Erros preservam a ficha; remoções devolvem os pontos exatos."""
        candidato = deepcopy(self)
        operacao(candidato)
        candidato.recalcular()
        if candidato.pontosDisponiveis < 0 and candidato.gastos > self.gastos:
            raise ValueError(f"Pontos insuficientes: faltam {-candidato.pontosDisponiveis:g} pontos.")
        self.__dict__.update(candidato.__dict__)

    def definirHabilidade(self, nome, graduacao):
        if nome not in self.habilidades:
            raise ValueError("Habilidade desconhecida.")
        custo_habilidade(graduacao)
        self._alterar(lambda f: setattr(f.habilidades[nome], "graduacao", graduacao))

    def adicionarHabilidades(self, nomeHabilidade, gra):
        atual = self.habilidades[nomeHabilidade].graduacao
        if atual is None:
            raise ValueError("Defina uma graduação para a habilidade ausente antes de aumentá-la.")
        self.definirHabilidade(nomeHabilidade, atual + inteiro(gra, "Graduações", 1))

    def definirDefesa(self, nome, graduacao):
        if nome not in DEFESAS:
            raise ValueError("Resistência é aumentada com Proteção ou Rolamento Defensivo.")
        inteiro(graduacao, "Graduações compradas de defesa")
        self._alterar(lambda f: f.defesas.update({nome: graduacao}))

    def definirPericia(self, nome, graduacao, especializacao="", indice=None, habilidade=None):
        if nome not in pericias_por_habilidade:
            raise ValueError("Perícia desconhecida.")
        inteiro(graduacao, "Graduações da perícia", 1)
        especializacao = texto(especializacao, "Especialização", nome in PERICIAS_ESPECIALIZADAS, 100)
        habilidade = habilidade or pericias_por_habilidade[nome]
        if habilidade not in HABILIDADES:
            raise ValueError("Habilidade da perícia desconhecida.")
        if nome != "especialidade" and habilidade != pericias_por_habilidade[nome]:
            raise ValueError("Esta perícia tem uma habilidade fixa.")
        item = {"nome": nome, "especializacao": especializacao, "habilidade": habilidade, "graduação": graduacao}
        def mudar(f):
            if any(i != indice and (p["nome"], p.get("especializacao", "").casefold()) ==
                   (nome, especializacao.casefold()) for i, p in enumerate(f.pericias)):
                raise ValueError("Esta perícia já existe. Use editar para alterar suas graduações.")
            if indice is None:
                f.pericias.append(item)
            else:
                f.pericias[indice] = item
        self._alterar(mudar)

    def adicionarPericia(self, nomePericia, habilidade, pontosInvs, especializacao=""):
        self.definirPericia(nomePericia, inteiro(pontosInvs, "Pontos de perícia", 1) * 2, especializacao)

    def definirVantagem(self, nome, graduacao=1, detalhe="", indice=None):
        if nome not in vantagens:
            raise ValueError("Vantagem desconhecida.")
        inteiro(graduacao, "Graduação da vantagem", 1)
        limite = LIMITES_VANTAGENS.get(nome, 1 if nome not in VANTAGENS_GRADUADAS else None)
        if nome == "sorte":
            limite = self.np // 2
        if limite is not None and graduacao > limite:
            raise ValueError(f"{nome}: a graduação máxima é {limite}.")
        item = {"nome": nome, "graduacao": graduacao, "detalhe": texto(detalhe, "Detalhe", limite=500)}
        def mudar(f):
            if any(i != indice and v["nome"] == nome and (nome not in VANTAGENS_POR_ESCOLHA or
                   v.get("detalhe", "").casefold() == item["detalhe"].casefold()) for i, v in enumerate(f.vantagens)):
                raise ValueError("Esta vantagem já existe. Use editar para alterar a graduação.")
            if indice is None:
                f.vantagens.append(item)
            else:
                f.vantagens[indice] = item
        self._alterar(mudar)

    def adicionarVantagem(self, nomeVantagem, graduacao):
        self.definirVantagem(nomeVantagem, graduacao)

    def adicionarPoder(self, nomePoder):
        nome = texto(nomePoder, "Nome do poder", True, 100)
        if any(p["nome"].casefold() == nome.casefold() for p in self.poderes):
            raise ValueError("Já existe um poder com esse nome.")
        self._alterar(lambda f: f.poderes.append({"nome": nome, "componentes": [],
            "extras": {}, "falhas": {}, "alternativas": [], "ativo": 0, "descritores": "", "notas": ""}))

    def substituirPoder(self, indice, poder):
        self._alterar(lambda f: f.poderes.__setitem__(indice, deepcopy(poder)))

    def adicionarComponente(self, indice, componente, alternativa=0):
        novo = deepcopy(self.poderes[indice])
        variante = novo if alternativa == 0 else novo["alternativas"][alternativa - 1]
        variante["componentes"].append(deepcopy(componente))
        self.substituirPoder(indice, novo)

    def modificarPoder(self, indice, grupo, nome, modificador):
        tabela = extras_dict_atualizado if grupo == "extras" else falhas_dict_atualizado
        if nome not in tabela:
            raise ValueError("Modificador desconhecido.")
        self.substituirPoder(indice, poder_com_modificador(self.poderes[indice], grupo, nome, modificador))

    def remover(self, categoria, indice):
        if categoria not in ("pericias", "vantagens", "poderes", "equipamentos", "complicacoes"):
            raise ValueError("Categoria inválida.")
        self._alterar(lambda f: getattr(f, categoria).pop(indice))

    def recalcular(self):
        from regras_ficha import custo_equipamento, estatisticas, normalizar_poder, chave_pericia
        for campo in ("pericias", "vantagens", "poderes", "equipamentos", "complicacoes"):
            itens = getattr(self, campo)
            if not isinstance(itens, list) or any(not isinstance(item, dict) for item in itens):
                raise ValueError(f"{campo}: use uma lista de registros.")
        texto(self.notas, "Notas")
        if not isinstance(self.identidade, dict):
            raise ValueError("Identidade deve ser um objeto.")
        for nome, valor in self.identidade.items():
            texto(valor, nome)
        self.np = inteiro(self.np, "NP", 1, 30)
        self.total = orcamento(self.np) + inteiro(self.pontosExtras, "Pontos adicionais")
        inteiro(self.pontosHeroicos, "Pontos heroicos")
        custos = {"habilidades": sum(custo_habilidade(h.graduacao) for h in self.habilidades.values()),
            "defesas": sum(inteiro(v, "Defesa comprada") for v in self.defesas.values()),
            "pericias": 0, "vantagens": 0, "poderes": 0}
        for p in self.pericias:
            if p["nome"] not in pericias_por_habilidade:
                raise ValueError(f"Perícia desconhecida: {p['nome']}")
            p["graduação"] = inteiro(p.get("graduação", p.get("graduacao", 0)), "Graduações de perícia")
            p.setdefault("especializacao", "")
            p.setdefault("habilidade", pericias_por_habilidade[p["nome"]])
            if p["habilidade"] not in HABILIDADES:
                raise ValueError("Habilidade da perícia inválida.")
            p["custo"] = custo_graduacoes_pericia(p["graduação"])
            custos["pericias"] += p["custo"]
        for v in self.vantagens:
            if v["nome"] not in vantagens:
                raise ValueError(f"Vantagem desconhecida: {v['nome']}")
            v["pontos_gastos"] = custo_vantagem(inteiro(v["graduacao"], "Graduação da vantagem", 1))
            v.pop("pontos gastos", None)
            custos["vantagens"] += v["pontos_gastos"]
        for p in self.poderes:
            normalizar_poder(p)
            custos["poderes"] += p["custo_total"]
        for e in self.equipamentos:
            e["custo"] = custo_equipamento(e)
        self.custos, self.gastos = custos, sum(custos.values())
        self.pontosDisponiveis = self.total - self.gastos
        self.estatisticas = estatisticas(self)
        for p in self.pericias:
            h = self.estatisticas["habilidades"][p["habilidade"]]
            p["bonus"] = None if h is None else h + p["graduação"] + self.estatisticas["bonus_pericias"].get(p["nome"], 0) + self.estatisticas["pericias_aumentadas"].get(chave_pericia(p["nome"], p.get("especializacao", "")), 0)

    def validar(self):
        from regras_ficha import validar_ficha
        self.recalcular()
        return validar_ficha(self)

    def para_dict(self):
        self.recalcular()
        campos = ("np", "nomeJogador", "nomePersonagem", "pontosExtras", "pontosHeroicos", "total",
            "pontosDisponiveis", "defesas", "pericias", "vantagens", "poderes", "equipamentos",
            "complicacoes", "identidade", "notas", "custos", "estatisticas")
        dados = {campo: deepcopy(getattr(self, campo)) for campo in campos}
        dados["schema_manual"] = 2
        dados["habilidades"] = {n: h.graduacao for n, h in self.habilidades.items()}
        dados["validacao"] = self.validar()
        return dados

    @classmethod
    def de_dict(cls, dados):
        if not isinstance(dados, dict) or "nomePersonagem" not in dados:
            raise ValueError("O arquivo não é uma ficha do criador manual.")
        if dados.get("schema_manual") not in (None, 2):
            raise ValueError("Esta ficha usa uma versão não suportada do criador manual.")
        for campo in ("habilidades", "defesas", "identidade"):
            if not isinstance(dados.get(campo, {}), dict):
                raise ValueError(f"{campo}: formato inválido no arquivo.")
        f = cls(dados["np"], dados.get("nomeJogador", ""), dados["nomePersonagem"] or "Personagem sem nome")
        for nome, valor in dados.get("habilidades", {}).items():
            if nome not in HABILIDADES:
                raise ValueError(f"Habilidade desconhecida: {nome}")
            f.habilidades[nome].graduacao = valor.get("graduacao", 0) if isinstance(valor, dict) else valor
        for campo in ("pontosExtras", "pontosHeroicos", "pericias", "vantagens", "poderes",
                      "equipamentos", "complicacoes", "notas"):
            if campo in dados:
                setattr(f, campo, deepcopy(dados[campo]))
        f.defesas.update({n: dados.get("defesas", {}).get(n, 0) for n in DEFESAS})
        f.identidade.update({n: dados.get("identidade", {}).get(n, "") for n in f.identidade})
        f.recalcular()
        return f

    def fazerFicha(self):
        from ficha_utilitarios import menu_ficha
        menu_ficha(self)

