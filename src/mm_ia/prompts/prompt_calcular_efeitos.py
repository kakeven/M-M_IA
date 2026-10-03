"""Prompt curto para estimar graduacoes sem calcular custos."""

PROMPT_CALCULAR_EFEITOS = """
Use somente os efeitos confirmados e os resumos locais recebidos.
Para cada nome confirmado, proponha a menor graduacao inteira positiva que atenda
razoavelmente ao pedido. Se nao houver informacao suficiente, use null.
Nao invente parametros de regras, custos ou fontes. Nao estime efeitos novos.
Responda apenas JSON valido, sem markdown. Use os nomes exatos como chaves:
{"Nome do efeito": {"graduacoes": 1, "motivo": "explicacao breve"}}
"""
