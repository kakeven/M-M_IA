PROMPT_RESUMO = """
Você receberá o texto oficial de um efeito de Mutantes & Malfeitores 3ª edição.

Produza um resumo técnico para uso em RAG, preservando integralmente as regras do efeito.

Regras:
- Inclua apenas informações explicitamente presentes no texto fornecido.
- Não faça inferências, esclarecimentos, perguntas, correções ou comentários pessoais.
- Se um campo não for informado, escreva “Não especificado”.
- Não cite exemplos narrativos, exceto se forem necessários para compreender uma regra.
- Mantenha a redação objetiva e concisa.

Use exatamente este formato:

Nome:
...

Função:
...

Representa:
...

Mecânica:
- Custo:
- Ação:
- Alcance:
- Duração:
- Resistência:
- Extras importantes:
- Falhas importantes:

Observações:
(apenas regras especiais indispensáveis; caso não existam, escreva “Nenhuma”.)

Retorne somente o resumo.
"""