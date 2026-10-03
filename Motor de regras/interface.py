"""Entrada do criador manual, independente de serviços externos."""
from ficha import Ficha
from armazenamento import carregar_ficha, listar_fichas
from ficha_utilitarios import verificar_digito, escolher_da_lista, valor_texto, mostrar_validacao

def menu():
    while True:
        print("\nCRIADOR MANUAL DE FICHAS")
        print("1 Criar personagem | 2 Abrir ficha salva | 0 Sair")
        try:
            opc = verificar_digito("Escolha: ", 0, 2)
            if opc == 0:
                return
            if opc == 1:
                jogador = valor_texto("Nome do jogador")
                personagem = valor_texto("Nome do personagem", obrigatorio=True)
                np = verificar_digito("Nível de poder (Enter = 10): ", 1, 30, padrao=10)
                ficha = Ficha(np, jogador, personagem)
            else:
                entradas = listar_fichas()
                entrada = escolher_da_lista(entradas, lambda e: f"{e['nome']} — NP {e['np']} ({e['arquivo']})")
                if entrada is None:
                    continue
                ficha = carregar_ficha(entrada["arquivo"])
                print("Ficha carregada. Custos e bônus foram recalculados.")
                mostrar_validacao(ficha)
            ficha.fazerFicha()
        except (ValueError, OSError, KeyError, TypeError) as erro:
            print(f"Não foi possível abrir/criar a ficha: {erro}")
        except (KeyboardInterrupt, EOFError):
            print("\nPrograma encerrado.")
            return

