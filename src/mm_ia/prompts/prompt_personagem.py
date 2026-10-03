LISTA_EFEITOS = """
Absorção de Energia
Aflição
Alongamento
Ambiente
Armadilha
Aura de Energia
Campo de Força
Camuflagem
Característica Aumentada
Característica
Compreender
Comunicação
Controle da Sorte
Controle de Elemento
Controle de Energia
Controle Mental
Crescimento
Criar
Cura
Dano
Deflexão
Duplicação
Encolhimento
Enfraquecer
Escavação
Forma Alternativa
Golpe
Ilusão
Imitar
Imortalidade
Imunidade
Intangibilidade
Invisibilidade
Invocar
Leitura Mental
Magia
Membros Extras
Metamorfo
Morfar
Mover Objeto
Movimento
Natação
Nulificar
Pasmar
Poder de Carga
Proteção
Raio
Rajada Mental
Rapidez
Regeneração
Salto
Sentidos
Sentido Remoto
Sono
Sufocamento
Supervelocidade
Teleporte
Transformação
Variável
Velocidade
Voo
"""



PROMPT_PERSONAGEM = f"""
Sua tarefa é pegar o texto recebido e relacionar com a lista de efeitos disponiveis para montar o conjunto obrigatorio de poderes. Não considere o poderes temporarios para a montagem

Lista disponivel: {LISTA_EFEITOS}

"""