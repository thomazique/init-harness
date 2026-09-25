---
name: frontend
description: Orienta qualquer trabalho de frontend em qualquer framework ou plataforma, incluindo criação, revisão e correção de interfaces, componentes, estilos, navegação, responsividade, acessibilidade, temas e design systems. Use antes de iniciar toda tarefa que altere ou avalie uma interface; descubra primeiro o contexto, a stack, os padrões e as ferramentas do projeto.
---

# Frontend

Crie interfaces que resolvam o trabalho real do produto e pareçam parte do sistema existente. Contexto, conteúdo e padrões do projeto orientam as decisões; tendências visuais e exemplos desta skill não definem o produto.

## Quando usar

Use esta skill para qualquer tarefa que crie, revise ou altere uma interface: páginas, telas, componentes, formulários, tabelas, navegação, layout, estilos, temas, tokens, acessibilidade, estados, responsividade ou movimento. Ela se aplica a aplicações web, mobile, desktop e outras superfícies de frontend, independentemente de framework.

Antes de mexer na interface:

1. Leia as instruções locais (`AGENTS.md`, `CLAUDE.md` e equivalentes relevantes).
2. Identifique a stack e a estrutura a partir dos manifests, da documentação e dos arquivos próximos ao alvo. Não presuma nomes de diretório, framework, comandos ou arquitetura.
3. Examine telas e componentes semelhantes, tokens, tema, convenções de conteúdo e decisões já existentes.
4. Descubra quem usa a interface, qual tarefa está tentando concluir e quais dispositivos, ambientes ou restrições importam. Use o que o repositório confirma; pergunte somente se uma informação ausente puder mudar materialmente a solução.
5. Confira os comandos de desenvolvimento, lint, testes e validação visual que o próprio projeto documenta.

Leia apenas as referências que ajudam na tarefa:

- [modos](references/modos.md): interface de trabalho ou superfície de apresentação;
- [tokens e sistema](references/tokens-e-sistema.md): tema, escalas e componentes reutilizáveis;
- [componentes e acessibilidade](references/componentes-acessibilidade.md): interação, estados e acesso;
- [motion e layout](references/motion-e-layout.md): movimento e adaptação aos viewports;
- [revisão e verificador](references/revisao-e-verificador.md): revisão e uso opcional do analisador incluído.

## Princípios de decisão

- Preserve a linguagem visual, os componentes, a arquitetura e a tecnologia já adotados quando forem adequados à tarefa.
- Dê a cada decisão visual uma razão ligada a conteúdo, hierarquia, orientação, interação ou identidade confirmada do produto.
- Não instale uma dependência, introduza um framework, crie tokens paralelos ou substitua um padrão existente sem necessidade demonstrável.
- Trate exemplos desta skill como ilustrações transferíveis, não como valores, copy, estrutura ou requisitos obrigatórios.
- Mantenha conteúdo, métricas, promessas e dados coerentes com fontes do projeto; não invente informações para preencher uma tela.

## Operate e Persuade

Classifique a superfície antes de escolher a composição:

| Modo | Serve a | Prioridades |
| --- | --- | --- |
| **Operate** | concluir tarefas, consultar ou editar informação, controlar um sistema | familiaridade, eficiência, hierarquia clara, feedback e estados completos |
| **Persuade** | explicar, apresentar, divulgar ou ajudar alguém a decidir | narrativa, identidade visual, conteúdo honesto, acessibilidade e ação compreensível |

Se a interface for principalmente de trabalho, prefira padrões aprendíveis e consistência às novidades decorativas. Uma superfície de apresentação pode ser mais autoral quando isso serve ao objetivo e à identidade já sustentada pelo produto. Nenhum modo dispensa acessibilidade, responsividade, desempenho ou conteúdo verdadeiro. Consulte [modos](references/modos.md) quando uma superfície combinar os dois.

## Piso de qualidade

Adapte a revisão à plataforma, ao escopo e aos usuários do projeto. Para as partes relevantes, confirme que:

- a tarefa principal e a hierarquia da tela são compreensíveis;
- conteúdo realista, nomes longos e estados menos comuns não quebram o layout;
- componentes interativos têm os estados aplicáveis, como foco, seleção, desabilitado, carregamento, erro e ausência de dados;
- feedback explica o que aconteceu e oferece um próximo passo quando necessário;
- teclado, leitor de tela, toque ou outros modos de entrada pertinentes funcionam;
- contraste, zoom, tamanho de texto, orientação e viewports relevantes ao produto foram considerados;
- a implementação segue o tema e os componentes existentes, sem valores visuais espalhados;
- texto, rótulos, métricas e ações descrevem o comportamento real.

Nem toda alteração exige rever toda a aplicação. Escolha verificações proporcionais à mudança, usando os recursos disponíveis no projeto. Renderização, navegação e interação são evidências da experiência; análise estática sozinha não as substitui.

## Padrões que pedem justificativa

Revise criticamente padrões que frequentemente criam interfaces genéricas ou menos utilizáveis:

- hero de tela inteira, fileiras repetidas de cards ou hierarquia promocional em fluxos de trabalho;
- cards aninhados, decoração, blur, sombras ou acentos sem função;
- fonte, paleta ou iconografia escolhida sem relação com o produto ou com o sistema existente;
- transições genéricas, animação contínua ou movimento que atrasa a tarefa;
- ícones ambíguos, emoji ou mistura de bibliotecas sem uma convenção consistente;
- controles personalizados quando padrões nativos ou componentes existentes atendem melhor;
- placeholders como substituto de conteúdo e mensagens vagas para erro, ação ou estado vazio;
- estilos, cores, espaçamentos ou raios duplicados fora do sistema de tema.

Esses sinais são convites para avaliar a decisão, não proibições universais. Uma exceção pode ser correta quando resolve uma necessidade do produto e respeita os padrões da plataforma.

## Tema, interação e movimento

Consulte [tokens e sistema](references/tokens-e-sistema.md), [componentes e acessibilidade](references/componentes-acessibilidade.md) e [motion e layout](references/motion-e-layout.md) conforme o trabalho. Reutilize o sistema do projeto e respeite preferências de movimento reduzido e os mecanismos de acessibilidade da plataforma. Não aplique valores universais de breakpoint, tipografia ou tamanho de alvo sem considerar a tecnologia, o conteúdo e os requisitos locais.

## Revisão antes da entrega

1. Compare a alteração com componentes e padrões adjacentes.
2. Confira as partes relevantes da interface renderizada, incluindo um viewport estreito se houver suporte a telas pequenas.
3. Revise os estados e modos de entrada afetados pela mudança.
4. Execute a validação do projeto quando aplicável e solicitada ou exigida pelas instruções ativas.
5. Use o analisador desta skill somente se os tipos de arquivo e heurísticas forem pertinentes; ele é opcional e não substitui as ferramentas do projeto nem a revisão visual.
6. Registre qualquer limite de validação relevante na entrega.

## Créditos e licenças

Esta skill sintetiza e reescreve orientações de `impeccable-craft-floor.md` e `impeccable-operate.md` (Apache 2.0), além de `hallmark-slop-test.md`, `uiux-design-system.md` e `uiux-styling.md` (MIT). Os princípios foram generalizados para serem aplicados conforme o contexto de cada projeto.
