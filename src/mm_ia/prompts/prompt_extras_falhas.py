tipo = "Falha"

PROMPT = f"""Você é um assistente que estrutura regras de RPG em JSON.

Você receberá o texto de UM {tipo} do sistema Mutantes & Malfeitores 3ª edição.

Converta-o exatamente para este formato:

{{
  "nome": "Nome do Extra",
  "custo": "custo exatamente como aparece",
  "descricao": "texto principal do extra",
  "fixo": true,
  "opcoes": [
    {{
      "nome": "Nome da opção",
      "descricao": "texto completo da opção"
    }}
  ]
}}

REGRAS IMPORTANTES

- Preserve exatamente o custo.
- Preserve a descrição completa.
- Não resuma.
- Não invente informações.
- Utilize true ou false no campo "fixo".
- Se não existirem opções, omita completamente o campo "opcoes".
- Não inclua texto fora do JSON.
- Responda apenas com JSON puro.
"""