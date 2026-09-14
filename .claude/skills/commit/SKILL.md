
---
name: commit
description: Convenção de commits, branches e pull requests do harness. Use sempre que for criar commit, nomear branch, abrir ou descrever PR, ou revisar o que está staged. A mensagem nasce do diff real, nunca da memória da conversa.
---
# commit

## Regra de ouro

Antes de escrever qualquer mensagem: `git status` e `git diff --staged`. Mensagem depois, nunca antes.

Se a sessão fez mais do que a tarefa original, a mensagem reflete o diff real, não o pedido inicial.

---

## Antes de commitar

1. `git diff --staged --stat` e revisar cada arquivo. Nome inocente pode conter segredo.
2. O commit do checkpoint inclui as atualizações de `docs/ai/` e `specs/` desse checkpoint.
3. Modo `cliente` (`.init-harness/config.json`): `INIT-HARNESS.md` e as skills de método **nunca** em stage.
4. Não usar `--no-verify`. Pre-commit falhou: corrigir a causa ou reportar ao usuário.

---

## Mensagem (Conventional Commits)

```
<tipo>(<escopo opcional>): <resumo no imperativo, minúsculo, sem ponto final>

- <o que mudou, por arquivo ou área, lido do diff>
- <por que, se não for óbvio>
```

| Tipo         | Quando                                            |
| ------------ | ------------------------------------------------- |
| `feat`     | Funcionalidade nova                               |
| `fix`      | Correção de bug                                 |
| `refactor` | Estrutura muda, comportamento externo não        |
| `perf`     | Melhoria de performance mensurável               |
| `docs`     | Só documentação                                |
| `test`     | Só teste                                         |
| `chore`    | Manutenção: dependência, config,`.gitignore` |
| `style`    | Só formatação ou lint                          |
| `build`    | Build, empacotamento, Dockerfile                  |
| `ci`       | Pipeline de CI/CD                                 |
| `revert`   | Desfaz commit; corpo cita o hash                  |

- Tipos genuinamente diferentes sem relação entre si: considerar dois commits.
- Mudanças dependentes contam como um tipo só. Um `fix` que exige ajustar teste continua sendo `fix`.
- Atualização de `docs/ai/` junto do código do checkpoint não muda o tipo do commit.
- Mudança pequena, corpo curto. Não inflar.

---

## Branches

`<tipo>/<slug>` com os mesmos tipos da tabela. Idioma do slug consistente com o projeto.

Uma frente corresponde a uma branch. Fluxo de PR obrigatório ou commit direto: conforme o `CLAUDE.md`.

---

## Pull Requests

Título na mesma convenção de tipo. Corpo:

```markdown
## Summary
- <lido do diff completo do PR, todos os commits>

## Test plan
- [ ] <o que foi executado para validar>

## Contexto
- Frente: docs/ai/frentes/<slug>.md
- Specs: specs/<modulo>/<n>-<slug>.md
```
