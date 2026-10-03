"""Regressões do criador manual, sem IA, bancos ou serviços externos."""
import json
import sys
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Motor de regras"))
from ficha import Ficha
from calculos import custo_componente, custo_poder
import armazenamento
from ficha_utilitarios import escolher_da_lista, verificar_digito
from poderes import vantagens, efeitos_poderes_lista, pericias_por_habilidade


def componente(nome="Raio", efeito="Raio", graduacao=10, base=2, **campos):
    return {"nome": nome, "efeito": efeito, "graduacao": graduacao,
            "custo_base": base, "extras": {}, "falhas": {}, **campos}


class ManualTests(unittest.TestCase):
    def nova(self, np=10):
        return Ficha(np, "Jogador", "Herói")

    def test_defesas_bonus_iniciativa_e_reembolso(self):
        f = self.nova()
        f.definirHabilidade("agilidade", 3)
        f.definirDefesa("esquiva", 7)
        f.definirVantagem("iniciativa aprimorada", 2)
        self.assertEqual(f.estatisticas["defesas"]["esquiva"], 10)
        self.assertEqual(f.estatisticas["iniciativa"], 11)
        f.definirHabilidade("agilidade", 1)
        self.assertEqual(f.estatisticas["defesas"]["esquiva"], 8)
        f.remover("vantagens", 0)
        self.assertEqual(f.pontosDisponiveis, 141)

    def test_falha_orcamento_preserva_estado_inteiro(self):
        f = self.nova(1)
        f.definirHabilidade("agilidade", 5)
        antes = f.para_dict()
        with self.assertRaises(ValueError):
            f.definirHabilidade("luta", 5)
        self.assertEqual(f.para_dict(), antes)

    def test_negativas_e_ausentes(self):
        f = self.nova()
        f.definirHabilidade("forca", -5)
        self.assertEqual(f.pontosDisponiveis, 160)
        with self.assertRaises(ValueError):
            f.definirHabilidade("forca", -6)
        f.definirHabilidade("vigor", None)
        self.assertIsNone(f.estatisticas["defesas"]["fortitude"])
        self.assertEqual(f.estatisticas["defesas"]["resistencia"], 0)
        self.assertEqual(f.pontosDisponiveis, 170)

    def test_pericias_impares_especializadas_e_limite_total(self):
        f = self.nova()
        f.definirHabilidade("intelecto", 10)
        f.definirPericia("especialidade", 11, "Medicina")
        f.definirPericia("especialidade", 1, "Direito")
        self.assertEqual(f.custos["pericias"], 6)
        self.assertTrue(any("bônus 21" in e for e in f.validar()["erros"]))
        with self.assertRaises(ValueError):
            f.definirPericia("especialidade", 2, "medicina")
        with self.assertRaises(ValueError):
            f.definirPericia("especialidade", 2)

    def test_vantagens_graduações(self):
        f = self.nova()
        with self.assertRaises(ValueError):
            f.definirVantagem("inventor", 2)
        with self.assertRaises(ValueError):
            f.definirVantagem("sorte", 6)
        f.definirVantagem("equipamento", 2)
        self.assertEqual(f.estatisticas["equipamento_disponivel"], 10)

    def test_modificadores_parciais_e_removivel_arredondado(self):
        self.assertEqual(custo_componente(1, 5, [
            {"tipo": "por_graduacao", "valor": -1, "inicio": 4, "fim": 5}]), 4)
        p = {"componentes": [componente(graduacao=49)], "falhas": {"removivel": 1}}
        self.assertEqual(custo_poder(p), 78)

    def test_extra_fixo_global_cobrado_uma_vez(self):
        f = self.nova()
        f.adicionarPoder("Kit")
        f.adicionarComponente(0, componente("A", graduacao=5))
        f.adicionarComponente(0, componente("B", graduacao=5))
        f.modificarPoder(0, "extras", "descritor variavel", {"tipo": "fixo", "valor": 2})
        self.assertEqual(f.poderes[0]["custo_total"], 22)
        f.recalcular()
        self.assertEqual(f.poderes[0]["custo_total"], 22)

    def test_modificador_sem_pontos_preserva_poder(self):
        f = self.nova(1)
        f.adicionarPoder("Raio")
        f.adicionarComponente(0, componente(graduacao=7))
        antes = f.para_dict()
        with self.assertRaises(ValueError):
            f.modificarPoder(0, "extras", "afeta outros", {"tipo": "por_graduacao", "valor": 1})
        self.assertEqual(f.para_dict(), antes)

    def test_arranjo_custo_ativacao_e_reducao_invalida(self):
        f = self.nova()
        f.adicionarPoder("Mobilidade")
        f.adicionarComponente(0, componente("Corrida", "Velocidade", 10, 1))
        p = deepcopy(f.poderes[0])
        p["alternativas"] = [{"nome": "Voo", "componentes": [componente("Voo", "Voo", 5, 2)]}]
        f.substituirPoder(0, p)
        self.assertEqual(f.poderes[0]["custo_total"], 11)
        p = deepcopy(f.poderes[0])
        p["componentes"][0]["graduacao"] = 9
        with self.assertRaises(ValueError):
            f.substituirPoder(0, p)
        self.assertEqual(f.poderes[0]["custo_total"], 11)

    def test_protecao_e_limites_de_combate(self):
        f = self.nova()
        f.definirHabilidade("vigor", 5)
        f.definirDefesa("esquiva", 11)
        f.adicionarPoder("Armadura")
        f.adicionarComponente(0, componente("Blindagem", "Proteção", 5, 1))
        self.assertEqual(f.estatisticas["defesas"]["resistencia"], 10)
        self.assertTrue(any("esquiva + resistencia = 21" in e for e in f.validar()["erros"]))

    def test_ataque_especializado_acurado(self):
        f = self.nova()
        f.definirHabilidade("destreza", 3)
        f.definirPericia("combate a distancia", 5, "Laser")
        f.definirVantagem("ataque a distancia", 1)
        f.adicionarPoder("Laser")
        c = componente("Laser", graduacao=10, modo_ataque="distancia", especializacao_ataque="Laser")
        c["extras"]["acurado"] = {"tipo": "fixo", "valor": 1}
        f.adicionarComponente(0, c)
        ataque = next(a for a in f.estatisticas["ataques"] if a["nome"] == "Laser")
        self.assertEqual(ataque["bonus"], 11)
        self.assertEqual(f.poderes[0]["custo_total"], 21)
        self.assertTrue(any("ataque + efeito" in e for e in f.validar()["erros"]))

    def test_caracteristica_aumentada_atualiza_pericia_e_defesa(self):
        f = self.nova()
        f.definirPericia("furtividade", 3)
        f.adicionarPoder("Reflexos")
        f.adicionarComponente(0, componente("Agilidade", "Característica Aumentada", 4, 2, caracteristica="agilidade"))
        self.assertEqual(f.pericias[0]["bonus"], 7)
        self.assertEqual(f.estatisticas["defesas"]["esquiva"], 4)

    def test_equipamento_veiculo_qg_orcamento_separado(self):
        f = self.nova()
        f.definirVantagem("equipamento", 2)
        f._alterar(lambda c: c.equipamentos.extend([
            {"nome": "Moto", "tipo": "veiculo", "tamanho": "medio", "movimento": 6},
            {"nome": "Base", "tipo": "qg", "tamanho": "pequeno", "resistencia": 8, "extras": 3}]))
        self.assertEqual(f.estatisticas["equipamento_gasto"], 10)
        self.assertEqual(f.gastos, 2)
        f.remover("vantagens", 0)
        self.assertTrue(any("Equipamento:" in e for e in f.validar()["erros"]))

    def test_salvar_carregar_recalcula_e_preserva_todos_campos(self):
        f = self.nova()
        f.definirPericia("percepcao", 2)
        f.identidade["origem"] = "Laboratório"
        f.complicacoes = [{"tipo": "Motivação", "descricao": "Justiça"}, {"tipo": "Segredo", "descricao": "Identidade"}]
        f.notas = "Notas"
        with tempfile.TemporaryDirectory() as diretorio, patch.object(armazenamento, "FICHAS_DIR", Path(diretorio)):
            caminho = armazenamento.salvar(f, "heroi")
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            dados["pontosDisponiveis"] = 99999
            dados["pericias"][0]["bonus"] = 99999
            caminho.write_text(json.dumps(dados), encoding="utf-8")
            g = armazenamento.carregar_ficha("heroi")
            self.assertEqual(g.pontosDisponiveis, 149)
            self.assertEqual(g.pericias[0]["bonus"], 2)
            self.assertEqual(g.identidade, f.identidade)
            self.assertEqual(g.complicacoes, f.complicacoes)
            self.assertEqual(g.notas, f.notas)

    def test_dados_antigos_sem_confiar_nos_caches(self):
        f = Ficha.de_dict({"np": 10, "nomePersonagem": "Antigo", "habilidades": {"vigor": 3},
            "pontosDisponiveis": 999, "total": 99, "pericias": [{"nome": "atletismo", "graduacao": 3}]})
        self.assertEqual(f.total, 150)
        self.assertEqual(f.pontosDisponiveis, 142.5)

    def test_entradas_cancelamento_e_arquivo_invalido(self):
        with patch("builtins.input", side_effect=["abc", "-1", "2"]):
            self.assertEqual(verificar_digito(""), 2)
        with patch("builtins.input", return_value="0"):
            self.assertIsNone(escolher_da_lista(["A"]))
        for nome in ("../fora", "CON", "", "a/b"):
            with self.assertRaises(ValueError):
                armazenamento._caminho_ficha(nome, escrita=True)

    def test_crescimento_e_encolhimento_bonificam_ficha(self):
        f = self.nova()
        f.definirPericia("furtividade", 2)
        f.adicionarPoder("Gigante")
        f.adicionarComponente(0, componente("Tamanho", "Crescimento", 8, 2))
        self.assertEqual(f.estatisticas["habilidades"]["forca"], 8)
        self.assertEqual(f.estatisticas["defesas"]["fortitude"], 8)
        self.assertEqual(f.estatisticas["defesas"]["esquiva"], -4)
        self.assertEqual(f.pericias[0]["bonus"], -6)
        self.assertEqual(f.estatisticas["tamanho"], 0)
        self.assertEqual(f.estatisticas["velocidade_terrestre"], 1)
        f.remover("poderes", 0)
        f.adicionarPoder("Pequeno")
        f.adicionarComponente(0, componente("Tamanho", "Encolhimento", 12, 2))
        self.assertEqual(f.estatisticas["habilidades"]["forca"], -3)
        self.assertEqual(f.estatisticas["defesas"]["esquiva"], 6)
        self.assertEqual(f.pericias[0]["bonus"], 14)

    def test_habilidade_aumentada_por_pericia_e_vantagem(self):
        f = self.nova()
        f.adicionarPoder("Treinamento")
        f.adicionarComponente(0, componente("Mira", "Característica Aumentada", 5, 1,
            caracteristica="combate a distancia", categoria_caracteristica="pericia",
            especializacao_caracteristica="Laser"))
        f.adicionarComponente(0, componente("Reação", "Característica Aumentada", 2, 1,
            caracteristica="iniciativa aprimorada", categoria_caracteristica="vantagem"))
        self.assertEqual(f.estatisticas["iniciativa"], 8)
        mira = next(p for p in f.estatisticas["pericias_efetivas"] if p["especializacao"] == "laser")
        self.assertEqual(mira["bonus"], 10)
        f.adicionarComponente(0, componente("Laser", graduacao=10, modo_ataque="distancia"))
        ataque = next(a for a in f.estatisticas["ataques"] if a["nome"] == "Laser")
        self.assertEqual(ataque["bonus"], 10)

    def test_modificador_especifico_custo_parcial_e_fonte(self):
        f = self.nova()
        f.adicionarPoder("Efeito")
        c = componente(graduacao=5)
        c["extras"]["personalizado:Opção específica"] = {
            "tipo": "por_graduacao", "valor": 1, "inicio": 4, "fim": 5,
            "pagina": 100, "detalhes": "Escolha manual conferida no livro"}
        f.adicionarComponente(0, c)
        self.assertEqual(f.poderes[0]["custo_total"], 12)
        self.assertTrue(any("Opção específica" in p for p in f.validar()["pendencias"]))

    def test_armadura_escudo_e_arma(self):
        f = self.nova()
        f.definirVantagem("equipamento", 3)
        f.definirHabilidade("forca", 3)
        f.definirPericia("combate a corpo-a-corpo", 6, "Espada")
        f._alterar(lambda g: g.equipamentos.extend([
            {"nome": "Armadura A", "tipo": "item", "custo": 3, "protecao": 3, "em_uso": True},
            {"nome": "Armadura B", "tipo": "item", "custo": 2, "protecao": 2, "em_uso": True},
            {"nome": "Escudo", "tipo": "item", "custo": 2, "defesa_ativa": 1, "em_uso": True},
            {"nome": "Espada", "tipo": "item", "custo": 3,
             "ataque": {"modo": "corpo", "graduacao": 3, "soma_forca": True, "especializacao": "Espada"}}]))
        self.assertEqual(f.estatisticas["defesas"]["resistencia"], 3)
        self.assertEqual(f.estatisticas["defesas"]["esquiva"], 1)
        ataque = next(a for a in f.estatisticas["ataques"] if a["nome"] == "Espada")
        self.assertEqual((ataque["bonus"], ataque["efeito"], ataque["cd"]), (6, 6, 21))

    def test_salvar_novamente_preserva_versao_anterior(self):
        f = self.nova()
        with tempfile.TemporaryDirectory() as diretorio, patch.object(armazenamento, "FICHAS_DIR", Path(diretorio)):
            armazenamento.salvar(f, "heroi")
            f.definirHabilidade("luta", 2)
            armazenamento.salvar(f, "heroi")
            antigos = list((Path(diretorio) / ".historico").glob("*.json"))
            self.assertEqual(len(antigos), 1)
            self.assertEqual(json.loads(antigos[0].read_text(encoding="utf-8"))["habilidades"]["luta"], 0)

    def test_menus_criar_editar_salvar_carregar_exportar(self):
        from interface import menu
        numero_equipamento = str(vantagens.index("equipamento") + 1)
        numero_protecao = str(efeitos_poderes_lista.index("Proteção") + 1)
        numero_percepcao = str(list(pericias_por_habilidade).index("percepcao") + 1)
        entradas = [
            "1", "Jogador", "Manual", "",  # personagem
            "2", "1", "5",  # Esquiva
            "3", "1", numero_percepcao, "3", "0",  # perícia
            "4", "1", numero_equipamento, "2", "", "0",  # vantagem
            "7", "1", "Nome civil",
            "8", "1", "Motivação", "Justiça", "1", "Segredo", "Identidade", "0",
            "5", "1", "Armadura", "1", "1", numero_protecao, "", "4",
            "", "", "", "", "", "0", "0",  # componente e volta
            "6", "1", "Colete", "1", "4", "", "4", "0", "0", "1", "0", "0",
            "9", "10", "11", "manual", "12", "manual", "0", "0", "0"]
        with tempfile.TemporaryDirectory() as diretorio, patch.object(armazenamento, "FICHAS_DIR", Path(diretorio)):
            saida = io.StringIO()
            with patch("builtins.input", side_effect=entradas), redirect_stdout(saida):
                menu()
            self.assertNotIn("Não foi possível", saida.getvalue())
            f = armazenamento.carregar_ficha("manual")
            self.assertEqual(f.nomePersonagem, "Manual")
            self.assertEqual(f.defesas["esquiva"], 5)
            self.assertEqual(f.estatisticas["defesas"]["resistencia"], 8)
            self.assertEqual(f.identidade["nome_civil"], "Nome civil")
            self.assertEqual(len(f.complicacoes), 2)
            self.assertTrue((Path(diretorio) / "manual.txt").is_file())

    def test_interrupcao_preserva_rascunho(self):
        from ficha_utilitarios import menu_ficha
        with tempfile.TemporaryDirectory() as diretorio, patch.object(armazenamento, "FICHAS_DIR", Path(diretorio)):
            with patch("builtins.input", side_effect=EOFError), redirect_stdout(io.StringIO()):
                menu_ficha(self.nova())
            self.assertEqual(len(list(Path(diretorio).glob("rascunho-*.json"))), 1)

    def test_duplicata_nao_burla_vantagem_unica(self):
        f = self.nova()
        f.definirVantagem("inventor", 1, "Detalhe A")
        with self.assertRaises(ValueError):
            f.definirVantagem("inventor", 1, "Detalhe B")

    def test_combinacao_de_dois_arranjos_verifica_limite(self):
        f = self.nova()
        f.definirDefesa("esquiva", 15)
        for nome in ("A", "B"):
            f.adicionarPoder(nome)
            indice = len(f.poderes) - 1
            f.adicionarComponente(indice, componente(nome, "Velocidade", 8, 1))
            p = deepcopy(f.poderes[indice])
            p["alternativas"] = [{"nome": nome + " Reflexos", "componentes": [
                componente("Agilidade", "Característica Aumentada", 4, 2, caracteristica="agilidade")]}]
            f.substituirPoder(indice, p)
        self.assertTrue(any("Combinação de poderes: esquiva + resistencia = 23" in e for e in f.validar()["erros"]))

    def test_arranjo_dinamico_custo_de_criacao(self):
        f = self.nova()
        f.adicionarPoder("Arranjo")
        f.adicionarComponente(0, componente("Corrida", "Velocidade", 10, 1))
        p = deepcopy(f.poderes[0])
        p["dinamico"] = True
        p["alternativas"] = [{"nome": "Voo", "dinamico": True, "componentes": [
            componente("Voo", "Voo", 5, 2)]}]
        f.substituirPoder(0, p)
        self.assertEqual(f.poderes[0]["custo_total"], 13)
        self.assertTrue(any("dinâmico" in e for e in f.validar()["pendencias"]))

    def test_bonus_de_pericia_aumentada_sem_compra_respeita_np(self):
        f = self.nova()
        f.adicionarPoder("Sensor")
        f.adicionarComponente(0, componente("Percepção", "Característica Aumentada", 11, 1,
            categoria_caracteristica="pericia", caracteristica="percepcao"))
        self.assertTrue(any("bônus 22" in e for e in f.validar()["erros"]))

    def test_dados_malformados_rejeitados(self):
        for campos in ({"habilidades": []}, {"pericias": ["invalid"]}, {"poderes": [{"nome": "A", "componentes": [None]}]}):
            with self.assertRaises(ValueError):
                Ficha.de_dict({"np": 10, "nomePersonagem": "Inválido", **campos})

    def test_busca_sem_acentos_e_custo_minimo(self):
        with patch("builtins.input", side_effect=["protecao", "1"]), redirect_stdout(io.StringIO()):
            self.assertEqual(escolher_da_lista(["Proteção", "Voo"]), "Proteção")
        self.assertEqual(custo_componente(1, 1, [{"tipo": "fixo", "valor": -3}]), 1)


if __name__ == "__main__":
    unittest.main()
