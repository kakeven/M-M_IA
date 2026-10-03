"""Prompt curto para validar os resumos recuperados."""

PROMPT_FICHA = """
Voce avalia resumos de regras recuperados de uma base local.
Recebera o pedido do usuario e documentos com nome e resumo.
Confirme somente efeitos relevantes para o pedido que tenham informacao mecanica
suficiente no resumo para propor uma graduacao. Prefira ate cinco efeitos.
Nao invente nomes, custos, fontes, acoes ou regras. Use exatamente o nome do documento.
Se o resumo for incerto ou irrelevante, nao confirme o efeito.
Responda apenas um objeto JSON valido, sem markdown, neste formato:
{
  "efeitos_confirmados": [{"nome": "Nome do documento", "motivo": "breve"}],
  "nova_consulta_rag": [],
  "pronto": true
}
"""
