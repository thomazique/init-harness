# Motion, layout e contexto de uso

## Movimento com propósito

Use movimento para comunicar uma mudança que ajuda a entender seleção, expansão, progresso ou resultado. O conteúdo principal deve continuar disponível se a animação for reduzida ou desativada. Prefira propriedades específicas, duração curta e comportamento alinhado à plataforma.

- Respeite as preferências de movimento reduzido do sistema e as convenções da stack.
- Não dependa de movimento para revelar conteúdo essencial ou confirmar uma ação crítica.
- Evite animações contínuas, efeitos repetidos e movimento automático que distraia da tarefa.
- Verifique desempenho e estabilidade durante renderização, navegação e rolagem.

## Layout adaptável

Responsividade inclui hierarquia, conteúdo, interação e navegação, não só encolher a tipografia. Use os breakpoints e padrões do projeto quando existirem. Escolha viewports de validação que representem os dispositivos e usos suportados.

- Preserve a ordem de leitura e a prioridade das ações quando o espaço mudar.
- Reorganize, transforme ou permita rolagem de tabelas conforme a tarefa; evite cortar informação ou provocar rolagem horizontal acidental.
- Permita que texto variável, nomes extensos, zoom e mudanças de idioma se acomodem.
- Garanta que navegação, controles e conteúdo continuem disponíveis em orientação e tamanho de tela suportados.
- Confira sobreposição de conteúdo, barras fixas, foco, menus e overlays em viewports menores.

Teste com dados e textos representativos, incluindo estados de carregamento, erro e ausência de conteúdo quando forem relevantes. Uma tela que funciona apenas com dados de demonstração curtos pode falhar com o conteúdo real.

## Efeitos de apresentação

Parallax, experiências 3D, animação ao rolar e mídia de grande porte podem ser adequados a uma superfície específica de apresentação. Use-os se contribuírem para o objetivo, forem compatíveis com dispositivos e tecnologias assistivas e não degradarem desempenho, legibilidade ou controles. A presença de uma biblioteca ou referência externa, por si só, não justifica introduzi-los.
