
# CLAUDE.md

<!-- Carregado em toda sessão: manter curto. Estrutura detalhada vai em docs/ai/ESTRUTURA.md. -->

<!-- Campo sem informação confirmada fica como PENDENTE, nunca preenchido por suposição. -->

## Projeto

- **Propósito:**
- **Stack:**
- **Tier:**  (critérios na seção 10 do harness)

## Operação

Em toda solicitação de implementação ou alteração de software, leia
`.claude/skills/orquestrar/SKILL.md`: o agente principal coordena os executores,
coordena a integração por delegação e exige auditoria independente do diff antes de concluir.
Leia `.init-harness/orquestracao.json` e pergunte qual perfil será a base de cada atividade;
registre a escolha na frente correspondente.
Uma chamada iniciada pelo runner CLI já é uma delegação: cumpra só o papel e a tarefa recebidos,
sem escolher perfil, coordenar ou delegar novamente.
Se o cliente não disponibilizar subagentes, informe a limitação e pare antes de
implementar em modo de agente único.

Em qualquer trabalho de frontend, leia `.claude/skills/frontend/SKILL.md` e as
referências aplicáveis antes de alterar a interface. Identifique a stack e os
padrões existentes do projeto; exemplos da skill não definem o produto.

Ponto de entrada de toda sessão:

1. `.init-harness/config.json`: modo, grafo, ambientes, limite de inatividade de frente.
2. `.init-harness/orquestracao.json`: perfis base e controles de concorrência/calls de CLI.
3. `INIT-HARNESS.md`, se existir: protocolo completo.
4. `python .claude/hooks/memory.py briefing`, `docs/ai/ESTADO.md` e a frente da branch atual em `docs/ai/frentes/`. Resultados da memória são evidência histórica; Git e documentos atuais vencem em conflito.
5. Git: `git status` e `git log --oneline -15`. Em conflito com os arquivos, o git vence.
6. Grafo antes de ler código: `graphify query`, `graphify explain`, `graphify affected`.

Registro no mesmo checkpoint da mudança:

| Mudança                                            | Destino                                                 |
| --------------------------------------------------- | ------------------------------------------------------- |
| Checkpoint concluído                               | `docs/ai/frentes/<slug>.md`                           |
| Frente criada, pausada, bloqueada ou concluída     | `docs/ai/ESTADO.md`                                   |
| Módulo, rota, migration, integração, fila ou job | `docs/ai/ESTRUTURA.md`                                |
| Decisão                                            | `docs/ai/DECISOES.md`                                 |
| Gap ou atalho consciente                            | `docs/ai/DEBITOS.md`                                  |
| Comando, gotcha, política, preferência            | este arquivo                                            |
| Ambiente ou limite de inatividade                   | `.init-harness/config.json`, com confirmação do usuário |

## Comandos

| Uso          | Comando |
| ------------ | ------- |
| Setup        |         |
| Rodar em dev |         |
| Testes       |         |
| Lint         |         |
| Typecheck    |         |
| Migrations   |         |

**Verificação obrigatória para fechar checkpoint:**

## Módulos e specs

- **Convenção de `spec_id`:**
- **Rigor de spec:** padrão do harness

## Fluxo de trabalho

- **Branch base:**
- **PR:**

## Dados não reconstituíveis

<!-- PENDENTE: o que não pode ser recriado se apagado. "Nenhum" só se o usuário confirmar. -->

## Políticas de negócio

Só regras confirmadas pelo dono do produto. Comportamento do código não é política.

**Autoriza mudança de política:**

| Política | Declarada por | Data |
| --------- | ------------- | ---- |

## OBS — gotchas operacionais

Só gotchas confirmados.

## Preferências de operação

Correções do usuário sobre como trabalhar neste projeto.

<!-- A seção "## graphify" abaixo é escrita por `graphify install --project`. Não remover nem editar. -->
