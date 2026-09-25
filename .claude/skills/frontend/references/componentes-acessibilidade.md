# Componentes, estados e acessibilidade

## Estados

Identifique os estados que fazem sentido para cada componente interativo. Dependendo da interface, podem incluir:

| Estado | Revisão |
| --- | --- |
| Normal e selecionado | rótulo, affordance, hierarquia e seleção atuais |
| Hover e pressionado | feedback breve sem deslocar conteúdo ou ocultar informação |
| Foco | localização clara ao navegar por teclado ou mecanismo equivalente |
| Desabilitado | motivo compreensível e estado anunciado pela plataforma |
| Carregamento | progresso e proteção contra ações duplicadas quando pertinente |
| Erro | problema ligado ao campo ou ação e forma de recuperação |
| Vazio | causa conhecida e próximo passo útil, se houver |

Revise apenas os estados aplicáveis à mudança. Evite mudança de layout involuntária entre normal, foco e erro.

## Formulários e feedback

- Use nomes persistentes e visíveis para controles; placeholder sozinho raramente substitui um rótulo.
- Associe instruções e erros ao controle correspondente usando o mecanismo semântico da plataforma.
- Preserve a entrada do usuário ao apresentar validação.
- Dê feedback para ações demoradas, falhas e conclusões relevantes.
- Use skeleton apenas quando a forma do conteúdo for previsível e ele ajudar a orientar a espera.
- Prefira mensagens específicas que expliquem o resultado ou indiquem como prosseguir.

## Contraste e comunicação

Siga o padrão de acessibilidade aplicável ao produto e à plataforma. Para interfaces web, considere os critérios WCAG aplicáveis a texto, elementos gráficos, controles, estados e indicadores de foco. Confira combinações nas superfícies reais. Não comunique seleção, perigo ou resultado apenas por cor: use também texto, forma, ícone conhecido ou posição.

Verifique também ampliação de texto, tema claro/escuro se suportado e conteúdo com diferentes comprimentos. Alvos de entrada e espaçamento entre ações devem considerar o padrão da plataforma e a forma como as pessoas usam o dispositivo.

## Navegação e semântica

Use componentes e elementos semânticos da stack quando disponíveis. Confira ordem de foco, rótulos acessíveis, nomes de ações, anúncio de mudanças relevantes, gerenciamento de foco em overlays e retorno do foco ao fechar. Ícones decorativos não devem poluir a árvore de acessibilidade; ícones funcionais precisam de nome compreensível.

Listas tabulares devem expor relações entre cabeçalhos e dados. Menus, diálogos, popovers e conteúdo rolável precisam continuar alcançáveis e operáveis. Não deixe que recorte ou posicionamento ocultem controles essenciais.

## Entrada e plataforma

Suporte os modos de entrada relevantes: teclado, ponteiro, toque, leitor de tela e navegação assistiva. Não dependa de hover em superfícies de toque nem reduza a área interativa abaixo das diretrizes da plataforma. Mantenha gestos com alternativa visível quando forem necessários para uma ação importante.
