# Mutantes & Malfeitores com IA

Assistente experimental, em Python, para transformar uma descrição em linguagem natural em sugestões de efeitos e em um rascunho de ficha de **Mutantes & Malfeitores 3ª edição**. Ele consulta uma base local de resumos, pede propostas a um modelo de IA e usa um motor de regras local para recalcular os custos que consegue determinar.

> **Estado do projeto:** a criação com IA ainda é um protótipo e exige revisão humana: extras, falhas, custos variáveis e parte dos limites de NP não são validados automaticamente nesse fluxo. O repositório inclui uma versão **mais completa do motor de regras**, usada também pelo criador manual. O conteúdo dos livros e os JSONs de regras usados pela busca com IA não são distribuídos. Sem esses JSONs, a indexação e a geração com IA não funcionam.

## O que ele faz

- **Consulta de poderes no terminal:** relaciona um pedido a efeitos da base local e retorna um JSON com sugestões, graduações propostas e custos base calculáveis.
- **Criação de fichas no navegador:** conduz o conceito, habilidades, perícias, vantagens, poderes e revisão. Cada etapa produz uma proposta que pode ser ajustada antes da aprovação.
- **Criador manual mais completo:** oferece editor no navegador e no terminal para montar fichas sem IA, com validações adicionais de defesas, perícias, arranjos, equipamento e limites de NP.
- **Cálculo local:** recalcula pontos de habilidades, perícias, vantagens e custos base de poderes. Custos indefinidos aparecem como pendências.
- **Persistência local:** guarda rascunhos, conversas e fichas em `.local/`, fora do controle de versão.
- **Dois provedores de geração:** Ollama local ou, quando disponível para a conta, conexão com o ChatGPT por login no navegador. A indexação dos resumos usa Ollama.

## Como funciona

```text
JSONs de regras locais ──> indexador ──> resumos no ChromaDB local
                                            │
descrição do usuário ──> busca de resumos ──> modelo de IA
                                            │
                              proposta revisada pelo usuário
                                            │
                              motor de regras local ──> ficha
```

O indexador lê os JSONs em `data/`, cria documentos pesquisáveis e gera resumos com Ollama. A busca combina nomes exatos com similaridade vetorial. Na criação de fichas, apenas candidatos recuperados e partes limitadas desses resumos entram no contexto enviado ao provedor escolhido. O usuário aprova cada etapa; o backend só incorpora uma proposta à ficha depois dessa aprovação. O motor local recalcula os pontos e sinaliza o que não conseguiu validar.

As referências de livro exibidas pela aplicação vêm exclusivamente do campo `fontes` cadastrado nos dados locais, não de citações inventadas pelo modelo. Um registro sem referência completa aparece como **Fonte não cadastrada**.

## Requisitos

- Python 3.11 ou superior.
- Ollama em execução para gerar os resumos e para usar a geração local. O modelo padrão é `qwen2.5:7b`.
- Arquivos próprios de regras em `data/`: `efeitos.json`, `extras.json`, `falhas.json` e `poderes_prontos.json`. Consulte [data/README.md](data/README.md). Eles devem ser obtidos e usados conforme seus direitos de acesso.
- O motor de regras já está incluído em `Motor de regras/`. O criador manual usa somente a biblioteca padrão do Python e não precisa de Ollama nem dos JSONs de `data/`.

Na primeira indexação, a biblioteca Sentence Transformers também pode baixar o modelo de embeddings. Reserve espaço em disco e conexão à internet para essa etapa.

## Instalação

Execute na raiz do projeto, no PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
ollama pull qwen2.5:7b
```

Inicie o Ollama antes de indexar ou usar a geração local. Ajuste `.env` se precisar mudar o modelo, o endereço do Ollama ou os limites de contexto. Esse arquivo é local e está ignorado pelo Git.

Para a busca e a criação com IA, coloque seus JSONs em `data/`. Em seguida:

```powershell
python -m mm_ia.indexing
```

O comando lê os quatro JSONs e gera os resumos. `--skip-summaries` atualiza os documentos e metadados sem chamar o Ollama para resumir; `--reset` recria as coleções locais. O índice fica em `.local/chroma_db/`.

## Uso

### Consulta no terminal

```powershell
python -m mm_ia.cli "quero convencer qualquer pessoa"
```

O resultado é um JSON. A consulta precisa do índice já criado e do Ollama em execução. O campo `custos_motor` traz os custos base que o motor consegue calcular e sinaliza os demais como pendências.

### Interface de fichas

```powershell
python -m mm_ia.web
```

A aplicação abre `http://127.0.0.1:8765/`. Para escolher outra porta, use `--port 8766`; para iniciar sem abrir o navegador, use `--no-browser`. O servidor escuta somente em `127.0.0.1` e foi feito para uso local.

Descreva o personagem, informe o NP e escolha o provedor. O fluxo passa por **conceito → habilidades → perícias → vantagens → poderes → revisão**. Você pode pedir ajustes, aprovar uma proposta ou editar a ficha. Alterações em uma área aprovada reabrem as etapas que dependem dela. Rascunhos ficam em `.local/criacoes/` e fichas salvas em `.local/fichas/`.

Para usar o ChatGPT, selecione **Meu plano ChatGPT Plus** e siga **Continue with ChatGPT**. A disponibilidade depende da conta e dos limites do serviço. A aplicação guarda credenciais OAuth no gerenciador de credenciais do sistema; o identificador local da instalação fica em `.local/chatgpt-host.json`. Nessa modalidade, o pedido e os trechos de resumos necessários à geração são enviados ao serviço. Os JSONs completos, PDFs, índice e fichas salvas permanecem no computador. A opção **Desconectar** revoga a sessão renovável e remove as credenciais locais.

### Criador manual de fichas

O criador manual pode ser usado logo após clonar o repositório, sem instalar as dependências do assistente com IA:

```powershell
python "Motor de regras/web.py"
```

A interface abre em `http://127.0.0.1:8766/` e permite editar, validar, salvar e exportar fichas. Use `--port 8767` para outra porta ou `--no-browser` para iniciar sem abrir o navegador. Também há um menu no terminal:

```powershell
python "Motor de regras/main.py"
```

Esta versão do motor é mais completa que a versão inicial pública: contempla habilidades negativas ou ausentes, defesas, perícias especializadas, vantagens, componentes de poderes, arranjos alternativos, equipamento, armas, veículos, QGs e complicações. Recalcula custos e bônus, verifica orçamento e diversos limites de NP, e separa erros, pendências e avisos. Ainda exige revisão do mestre para interações e casos não implementados. Os detalhes e comandos de teste estão no [README do motor](Motor%20de%20regras/readme.md).

### Importação opcional de textos

Para estruturar textos próprios de poderes, coloque arquivos `.txt` em `data/poderes_txt/` e execute:

```powershell
python scripts/importar_poderes.py
```

O script usa Ollama, grava `data/poderes_prontos.json` e move os textos processados para diretórios locais ignorados pelo Git.

## Limites conhecidos

- Os custos calculados são os custos base conhecidos pelo motor. Extras, falhas e custos variáveis podem exigir preenchimento ou conferência manual.
- A revisão final não certifica conformidade com todas as regras do jogo; o estado da criação mantém `validacao_completa: false`.
- O criador manual implementa mais validações, mas também mantém `validacao_completa: false` quando ainda há regras ou interações que exigem conferência.
- A qualidade da sugestão depende dos dados locais, dos resumos indexados e do modelo escolhido.
- A aplicação e o motor local não substituem o livro de regras nem reproduzem seu texto integral.

## Desenvolvimento

```text
src/mm_ia/config.py       Configuração e caminhos locais
src/mm_ia/indexing.py     Leitura dos JSONs e indexação
src/mm_ia/database.py     Coleções persistentes do ChromaDB
src/mm_ia/pipeline.py     Busca e análise de pedidos
src/mm_ia/creation.py     Etapas, aprovação e persistência da criação
src/mm_ia/rules_engine.py Adaptador do motor de regras local
src/mm_ia/sheets.py       Cálculo e armazenamento das fichas
src/mm_ia/web.py          Servidor HTTP local
src/mm_ia/static/         Interface HTML, CSS e JavaScript
Motor de regras/          Criador manual e motor de cálculos mais completo
tests/                    Testes automatizados
```

Para executar os testes do pacote público:

```powershell
python -m unittest discover -s tests -p "test_retrieval.py" -v
python -m unittest discover -s tests -p "test_chatgpt_plan.py" -v
python -m unittest discover -s tests -p "test_creation_chat.py" -v
```

Para testar também o criador manual incluído neste repositório:

```powershell
python -m unittest discover -s tests -p "test_manual_*.py" -v
```

