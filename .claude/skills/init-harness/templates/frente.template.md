
---
slug: <slug>
status: ativa
dono: <id da sessão ou agente>
atualizado_em: <AAAA-MM-DDTHH:MM>
branch: <branch>
worktree: <path ou ->
objetivo: <uma linha>
specs: <specs/modulo/n-slug.md, separadas por vírgula, ou ->
depende_de: <docs/ai/frentes/outra-frente.md, separadas por vírgula, ou ->
bloqueia: <docs/ai/frentes/outra-frente.md, separadas por vírgula, ou ->
relaciona_com: <docs/ai/frentes/outra-frente.md, separadas por vírgula, ou ->
decisoes: <D-0001, separadas por vírgula, ou ->
debitos: <DB-0001, separadas por vírgula, ou ->
modulos: <auth, users, separados por vírgula, ou ->
files: <app/auth/service.py, separados por vírgula, ou ->
tags: <segurança, api, separadas por vírgula, ou ->
---
<!-- Frontmatter plano (chave: valor, uma linha cada): lido pelos hooks sem parser YAML. Não aninhar. -->
<!-- As relações acima são opcionais. Preencha apenas quando ajudam a coordenação ou a recuperação de contexto. -->

<!-- status: ativa | pausada | bloqueada | concluida -->

# Frente: <slug></slug>

## Checkpoints

| # | Checkpoint    | Status   |
| - | ------------- | -------- |
| 1 | <descrição> | pendente |

<!-- Status do checkpoint: pendente | em_andamento | feito -->

## Próximo passo

<!-- Ação concreta, executável por quem chegar agora, com paths. -->

## Bloqueios

- nenhum

## Handoff

<!-- Só o que quem chega precisa saber e não está em nenhum outro arquivo. -->

## Transferências

| Data | De | Para | Motivo |
| ---- | -- | ---- | ------ |
