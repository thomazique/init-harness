
# CLAUDE.md

<!-- Carregado em toda sessão: manter curto. Estrutura detalhada vai em docs/ai/ESTRUTURA.md. -->

<!-- Campo sem informação confirmada fica como PENDENTE, nunca preenchido por suposição. -->

## Projeto

- **Propósito:**
- **Stack:**
- **Tier:**  (critérios na seção 10 do harness)

## Operação

Ponto de entrada de toda sessão:

1. `.init-harness/config.json`: modo, grafo, ambientes, limite de inatividade de frente.
2. `INIT-HARNESS.md`, se existir: protocolo completo.
3. `docs/ai/ESTADO.md` e a frente da branch atual em `docs/ai/frentes/`.
4. Git: `git status` e `git log --oneline -15`. Em conflito com os arquivos, o git vence.
5. Grafo antes de ler código: `graphify query`, `graphify explain`, `graphify affected`.

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
