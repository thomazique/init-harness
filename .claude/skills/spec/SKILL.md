---
name: spec
description: Criação e ciclo de vida de spec para tarefa não trivial. Use antes de codar qualquer tarefa que toque mais de um arquivo, mude schema, contrato, rota ou permissão, tenha impacto fora do módulo ou não seja reversível. Levanta nós afetados, blast radius e riscos reais antes da primeira linha de código.
---
# spec

A spec é o prompt estruturado da própria tarefa: força levantar superfície afetada e risco antes de codar.

---

## Local e numeração

- Caminho: `specs/<modulo>/<n>-<slug>.md`
- `<modulo>` segue a convenção do `CLAUDE.md`.
- `<n>` é o próximo número livre em `specs/<modulo>/`.

---

## Formato

```markdown
---
spec_id: <modulo>/<n>-<slug>
spec_version: 1
status: rascunho
frente: docs/ai/frentes/<slug>.md
base_commit: <git rev-parse --short HEAD no momento da spec>
grafo: graphify | manual
module: <modulo>
camadas: [banco, backend, rota, frontend]
target_nodes:
  - <Nó>
files:
  - <path>
blast_radius:
  same_module: []
  cross_module: []
  cross_community: []
risks:
  - <risco concreto, com consequência>
verificacao:
  - <comando do CLAUDE.md>
---

## Objetivo
<uma linha>

## Fora de escopo
- <o que não será feito>

## Checkpoints
1. <checkpoint> — <camada>

## Critério de pronto
- [ ] <verificável>
```

---

## Preenchimento

### `target_nodes` e `files`

- Com grafo: `graphify query "<descrição da tarefa>"` e `graphify explain "<nó>"` para localizar os nós.
- Sem grafo: busca e leitura, declarando `grafo: manual`.
- Schema, assinatura ou contrato não confirmado em código real: **parar e pedir o trecho**. Não estimar.

### `blast_radius`

1. `graphify affected "<nó>" --depth 2` para cada nó alvo.
2. Classificar cada nó retornado:
   - `same_module`: mesmo módulo segundo `docs/ai/ESTRUTURA.md`
   - `cross_module`: outro módulo
   - `cross_community`: outra comunidade segundo `graphify-out/GRAPH_REPORT.md`
3. Sem grafo: levantar por busca de referências e declarar que o levantamento é manual.

### `camadas`

Só as camadas tocadas, na ordem banco → backend → rota → frontend. Um checkpoint por camada.

### `risks`

Só risco real e específico: "remover X apaga Y em cascata sem aviso". Nada genérico como "pode quebrar algo".

---

## Ciclo de vida

| Status          | Quem muda                | Quando                                    |
| --------------- | ------------------------ | ----------------------------------------- |
| `rascunho`    | Agente                   | Spec criada                               |
| `aprovada`    | **Só o usuário** | Após revisão                            |
| `em_execucao` | Agente                   | Primeiro checkpoint iniciado              |
| `concluida`   | Agente                   | Critério de pronto atendido e verificado |
| `cancelada`   | Usuário                 | Tarefa abandonada                         |

- **Aprovação obrigatória** quando `cross_module` ou `cross_community` não está vazio, ou quando há risco sobre dado, produção ou contrato. Sem isso, o agente pode seguir de `rascunho` para `em_execucao` informando a spec.
- **Mudança durante a execução:** incrementar `spec_version`, registrar o motivo na frente e, se o blast radius cresceu, voltar a `rascunho` e pedir aprovação.
- Todo status novo é registrado também na frente (seção 6 do harness).
