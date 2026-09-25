# Revisão e verificador

## Validação da interface

Comece pelos comandos e ferramentas documentados pelo próprio projeto. Eles conhecem a stack, os padrões, os arquivos gerados e a política de qualidade local. Execute verificações proporcionais à mudança e às instruções ativas. Uma alteração visual também pede revisão da interface renderizada quando essa capacidade estiver disponível.

Revise, conforme aplicável:

- composição e conteúdo em viewports representativos;
- navegação por teclado e foco;
- texto ampliado, contraste e tecnologia assistiva;
- estados normais, selecionados, desabilitados, carregando, erro e vazio;
- overflow, sobreposição, conteúdo longo e comportamento dos controles;
- consistência com tema, componentes e telas próximas;
- mensagens e rótulos em relação ao comportamento real.

## Analisador incluído nesta skill

`scripts/verificar_frontend.py` é um auxiliar **opcional e consultivo** para padrões mecânicos em fontes CSS e JavaScript/TypeScript, componentes Vue/Svelte/Astro e arquivos Dart. Ele pode sugerir inspeção de cores literais, valores de espaçamento, fontes, transições, movimento e foco. Suas heurísticas não conhecem necessariamente o design system, as exceções, os preprocessadores ou a arquitetura do projeto.

Use-o somente quando:

1. o repositório contém a cópia desta skill;
2. os formatos que ele lê cobrem os arquivos relevantes;
3. as regras são úteis ao projeto e o resultado puder ser interpretado como diagnóstico consultivo.

Comando, a partir da raiz do projeto:

```text
python .claude/skills/frontend/scripts/verificar_frontend.py <arquivo-ou-diretorio>
```

O comando aceita também `--strict` para devolver código de erro diante das violações heurísticas. Use esse modo apenas quando a equipe decidiu que as regras servem ao projeto. Sem `--strict`, os achados não bloqueiam o comando. Códigos não substituem lint, build, testes, checagem de acessibilidade ou revisão visual.

O analisador não interpreta de forma confiável toda sintaxe, configuração, utilitário de estilo ou token. Ele não prova conformidade nem qualidade e não deve ser adicionado como gate universal do build.

## Limites

Análise estática não determina se uma interface é compreensível, se o layout serve às pessoas, se uma cor tem contraste suficiente no contexto final, se um estado está bem explicado ou se a experiência renderizada funciona. Ao reportar validação, diferencie o que foi executado, observado ou não pôde ser conferido.
