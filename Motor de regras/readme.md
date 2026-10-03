# Criador manual de fichas — Mutantes & Malfeitores 3ª edição

## Interface no navegador

```powershell
python "Motor de regras/web.py"
```

A tela abre em `http://127.0.0.1:8766/`, com seções para personagem, habilidades,
defesas, perícias, vantagens, poderes, equipamento, complicações e revisão.
Os pontos são recalculados durante a edição pelo mesmo motor do terminal.
**Salvar ficha** grava na biblioteca local; **Exportar texto** baixa a ficha em `.txt`.
Um rascunho automático no navegador permite retomar uma edição após recarregar.
O servidor precisa continuar aberto para calcular, salvar e abrir fichas.

Os arquivos da interface estão em `static/index.html`, `static/app.css` e
`static/app.js`. O servidor usa somente a biblioteca padrão do Python.
Opções: `--port 8767` e `--no-browser`.

## Interface de terminal

Execute a partir da raiz do projeto:

```powershell
python "Motor de regras/main.py"
```

O criador usa a biblioteca padrão do Python e os catálogos locais desta pasta.
O menu inicial permite criar um personagem ou escolher uma ficha salva pela lista.

## Preenchimento

- **Habilidades:** defina a graduação total, inclusive valores negativos até -5.
  Digite `ausente` para representar uma habilidade inexistente; o relatório pede
  aprovação do mestre para esse caso.
- **Defesas:** compre graduações de Esquiva, Aparar, Fortitude e Vontade. A base
  vem das habilidades. Resistência aumenta com poderes, vantagens ou armadura.
- **Perícias:** compre graduações, não apenas pontos inteiros. Cada graduação
  custa meio ponto; o relatório sinaliza um total de compras com meio ponto.
  Especialidade e perícias de combate têm especializações independentes.
- **Vantagens:** o menu diferencia vantagens únicas de graduadas e permite
  registrar as escolhas necessárias, como idiomas e benefícios.
- **Poderes:** nomeie o conjunto, adicione e edite componentes, graduações,
  detalhes, ação, alcance, duração e resistência. Informe descritores e notas.
  Extras e falhas de componente aceitam intervalos inclusivos; custos fixos
  não são multiplicados pela graduação do efeito.
- **Arranjos:** crie o efeito primário antes das alternativas. Cada alternativa
  deve caber no custo do primário. O menu permite escolher a variante usada no
  perfil calculado e definir se o arranjo é dinâmico.
- **Equipamento:** registre itens e armas, armaduras e escudos, veículos e QGs.
  O orçamento de equipamento é separado dos pontos de poder e vem da vantagem
  Equipamento. Movimento de veículos, características e efeitos adicionais
  precisam de seus custos informados. Armas podem registrar um ataque para
  entrar nos cálculos de bônus, efeito e CD.
- **Identidade:** nome civil, identidade pública/secreta, gênero, idade, altura,
  peso, olhos, cabelo, grupo, base, origem, aparência, personalidade, objetivos
  e histórico.
- **Complicações:** registre pelo menos duas, incluindo uma Motivação.
- **NP/pontos:** ajuste o NP, pontos adicionais concedidos pelo mestre e os
  pontos heroicos. Também há espaço para notas.

As listas aceitam números ou texto para filtrar, inclusive sem acentos.
`0` volta. Enter mantém um valor sugerido e `-` limpa um campo de texto.
Perícias, vantagens, componentes, modificadores, poderes e equipamento podem
ser editados ou removidos. Remoções e reduções reembolsam o custo recalculado.

## Validação e cálculos

Toda alteração é feita em uma cópia e só é aplicada quando o cálculo termina.
Uma compra sem pontos suficientes preserva a ficha anterior. O relatório
verifica:

- Orçamento e distribuição entre habilidades, defesas, perícias, vantagens e poderes.
- Limite de bônus total de perícia, incluindo habilidades e poderes.
- Ataque + efeito e efeitos que não exigem teste de ataque.
- Esquiva + Resistência, Aparar + Resistência e Fortitude + Vontade.
- Graduações de vantagens, duplicatas e especializações faltantes.
- Orçamento de equipamento e custo básico de armadura/escudo.
- Arranjos alternativos, inclusive combinações entre arranjos até 512 perfis.

As estatísticas incluem iniciativa, ataques, CD, defesas e perícias sem
treinamento. Proteção, Campo de Força, Crescimento, Encolhimento,
Característica Aumentada e vantagens comuns alimentam esses valores.
Característica Aumentada permite habilidades, defesas, perícias e vantagens;
no caso de perícias, uma graduação do componente concede duas graduações.

Removível é calculado sobre o conjunto, com arredondamento para cima e opção
Indestrutível. Efeitos Ligados precisam do mesmo alcance. Extras fixos globais
são cobrados uma vez. Modificadores específicos de efeitos podem ser
cadastrados com nome, tipo de custo, valor, justificativa e página impressa.

## Limites atuais

O relatório distingue **erros**, **pendências** e **avisos**. Limites de NP
excedidos podem ser salvos como rascunho para ajustes posteriores.
`validacao_completa` permanece falso: o programa não substitui a aprovação do
mestre nem valida automaticamente todos os requisitos e interações do livro.

Poderes variáveis, formas e poderes compostos especiais ainda precisam de
conferência dos bônus concedidos. A distribuição simultânea dos pontos de
um arranjo dinâmico não é simulada. Custos de armas e efeitos adicionais
de veículos/QGs são informados manualmente. Modificadores personalizados,
opções de efeitos, condições situacionais e imunidades de habilidades
ausentes ficam registrados para revisão.

## Salvar, carregar e exportar

As fichas manuais usam `schema_manual: 2` e são gravadas em `.local/fichas/`.
Regravar preserva a versão anterior em `.local/fichas/.historico/`. Salvar
uma ficha antiga cria a versão atual na pasta local, preservando o original
da pasta do motor. Ao carregar, custos, pontos disponíveis e bônus são
recalculados a partir das compras; caches antigos não são confiados.
Uma interrupção do editor preserva um rascunho.

A opção Exportar texto gera uma ficha legível em `.txt`, com todos os campos,
componentes, custos, bônus e relatório de validação.

Antes de alterações importantes, faça uma cópia de segurança das fichas em
`.local/fichas/`.

## Testes

```powershell
python -m unittest discover -s tests -p test_manual_sheet.py -v
```

Os testes cobrem cálculos, alterações rejeitadas, reembolsos, fichas antigas,
persistência, arranjos, especializações e uma criação pelo menu até salvar e
exportar. Não acessam serviços externos.

