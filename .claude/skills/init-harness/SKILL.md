---
name: init-harness
description: Implantação do harness em projeto sem `.init-harness/config.json`. Use ao entrar em projeto novo ou existente que ainda não tem o harness implantado, ou quando o usuário pedir para implantar, inicializar ou mapear o projeto. Instala e gera o grafo, entende o projeto gastando o mínimo de contexto, pergunta só o que não é derivável do código e termina com CLAUDE.md, docs/ai/ e harness.json reais.
---
# init-harness

Objetivo: sair de um projeto desconhecido para um projeto em que qualquer agente, em qualquer sessão, sabe o que o sistema é, onde está e como operar.

**Nenhum código de produto é alterado durante esta skill.**

Cada passo é um checkpoint. Ao final de cada um: o que foi feito e qual o próximo.

---

## Passo 0 — Pré-condições

1. `git rev-parse --is-inside-work-tree`. Fora de repositório git: parar e perguntar.
2. `git status`. Working tree com alterações não commitadas: parar e perguntar como tratar. Não fazer stash nem commit por conta própria.
3. Registrar branch atual e branch base.
4. Perguntar o **modo** se não foi informado: `proprio` ou `cliente`.
5. Modo `cliente`: adicionar a `.git/info/exclude` antes de criar qualquer arquivo:
   ```
   INIT-HARNESS.md
   .claude/skills/init-harness/
   .claude/skills/frontend/
   .claude/skills/spec/
   .claude/skills/pilares/
   .claude/skills/commit/
   .claude/skills/offboarding/
   tests/guardrails/
   ```

---

## Passo 1 — Instalar o grafo

1. `python3 --version`. Menor que 3.10: pular para **Sem grafo**.
2. Se `graphify --version` falhar:
   - `uv --version` disponível: `uv tool install graphifyy`
   - senão, `pipx --version` disponível: `pipx install graphifyy`
   - nenhum dos dois: perguntar ao usuário como prefere instalar. Não instalar gerenciador de pacote sem aval.
3. `graphify: command not found` após instalar: `uv tool update-shell` (ou `pipx ensurepath`) e informar que o terminal precisa ser reaberto. Alternativa imediata: `python3 -m graphify --version`.
4. `graphify install --project --platform claude` (sem `--strict`).
5. `graphify hook install` e confirmar com `graphify hook status`.
6. Adicionar `graphify-out/cache/` ao `.gitignore` (modo `proprio`) ou a `.git/info/exclude` (modo `cliente`).

**Sem grafo:** registrar para o passo 7 `"grafo": "manual"` e o débito correspondente. A estrutura do passo 3 passa a ser levantada por listagem de diretórios, manifests e busca.

---

## Passo 2 — Gerar o grafo sem custo de LLM

```
graphify extract . --code-only
graphify cluster-only . --no-label
```

Semântica de documentação (`/graphify . --update`) consome tokens: só com aval do usuário e só se a documentação do projeto for relevante para entender o sistema.

---

## Passo 3 — Ler a estrutura pelo grafo

Não abrir subagente para mapear arquivo por arquivo: o grafo já fez esse trabalho.

1. `graphify god-nodes --top 15`: hubs arquiteturais.
2. `graphify-out/GRAPH_REPORT.md`: comunidades e fronteiras naturais.
3. `graphify explain "<hub>"` nos hubs principais.
4. Anotar: módulos candidatos, pontos centrais, fronteiras entre comunidades.

---

## Passo 4 — Leitura manual mínima

Leitura direta, sem agente:

- Manifests: `package.json`, `composer.json`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `Cargo.toml`, conforme existirem
- Entrypoints
- `docker-compose*.yml`, `Dockerfile*`
- `README*`
- `.env.example` (**nunca** `.env`)
- Listagem (não conteúdo) de migrations
- Configuração de CI, se houver
- Configuração de testes e lint, se houver

Subagente de pesquisa só se o projeto for grande demais para essa leitura caber no contexto.

---

## Passo 5 — Resumo de entendimento

Apresentar ao usuário, antes de qualquer pergunta:

- Stack e versões lidas nos manifests
- Módulos identificados e hubs
- Propósito aparente do sistema
- Ambientes aparentes (compose, arquivos de config, CI)
- Testes existentes e comandos aparentes de teste, lint e typecheck
- Riscos visíveis: sem testes, sem `.env.example`, credencial no código, conexão hardcoded, migrations sem controle, sem CI

Não perguntar nada que este resumo já responde.

---

## Passo 6 — Perguntar só o não derivável

Uma rodada, agrupada, objetiva:

1. Objetivo de negócio do sistema.
2. Ambientes existentes e **como detectar cada um**: arquivo, chave e valores (formato de `ambientes.regras` no harness), e se comando destrutivo é permitido, confirmado ou bloqueado em cada um.
3. Dados não reconstituíveis.
4. Tier (T0–T3) conforme a seção 10 do harness.
5. Convenção de nome de módulo para `spec_id`.
6. Confirmação dos comandos de teste, lint e typecheck.
7. Fluxo de branch e PR (PR sempre ou commit direto).
8. Limite de inatividade para uma frente poder ser assumida por outro agente.
9. Políticas de negócio já conhecidas e quem autoriza mudá-las.
10. Nível de rigor de spec, se diferente do padrão do harness.

---

## Passo 7 — Gerar os arquivos de contexto

A partir dos templates em `.claude/skills/init-harness/templates/` (`CLAUDE.template.md`, `AGENTS.template.md`, `ESTADO.template.md`, `ESTRUTURA.template.md`, `DECISOES.template.md`, `DEBITOS.template.md`, `config.template.json`), preenchidos só com o que foi lido nos passos 2–5 e confirmado no passo 6. `frente.template.md` é usado ao criar a primeira frente, não aqui:

| Arquivo                  | Conteúdo inicial                                                                                                                                                           |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CLAUDE.md`            | Stack, tier, comandos, convenção de módulo, fluxo de branch, dados não reconstituíveis, políticas, gotchas confirmados.**Preservar a seção `## graphify`.** |
| `AGENTS.md`            | Adaptador curto para o Codex; referencia as fontes compartilhadas sem duplicar regras de negócio. Se já existir, mesclar sem sobrescrever instruções válidas. |
| `docs/ai/ESTADO.md`    | Fase atual, nenhuma frente ativa                                                                                                                                            |
| `docs/ai/ESTRUTURA.md` | Módulos, fronteiras, fluxos e integrações do passo 3 confirmados no passo 6                                                                                              |
| `docs/ai/DECISOES.md`  | Decisões da implantação: modo, tier, convenções escolhidas                                                                                                             |
| `docs/ai/DEBITOS.md`   | Riscos visíveis do passo 5 e "auditoria de pilares pendente"                                                                                                               |
| `.init-harness/config.json` | Versão, modo, data, grafo,`frente_inativa_horas`, regras de `ambientes`                                                                                                |

Nada genérico: campo sem informação confirmada mantém o marcador `PENDENTE` do template. Em `config.json`, sem confirmação, `frente_inativa_horas` fica `null` e `regras` fica vazio (tudo cai em `se_indeterminado: bloquear`).

---

## Passo 8 — Enforcement

Aplicar `.claude/settings.json`, `.claude/hooks/` e `.githooks/` do kit.

- **Mesclar** com o `.claude/settings.json` existente (inclusive os hooks do graphify). Nunca sobrescrever.
- `git config core.hooksPath .githooks`
- `uv run --no-project --python ">=3.10" tests/guardrails/test_guardrails.py`
- `uv run --no-project --python ">=3.10" .claude/hooks/doctor.py`
- Registrar em `DEBITOS.md` qualquer guardrail ou diagnóstico que não passou.

---

## Passo 9 — Auditoria de pilares

Rodar a skill `pilares` com o tier declarado. Resultado em `DEBITOS.md`.

---

## Passo 10 — Versionamento

- Modo `proprio`: commit `chore(harness): implanta harness <versão>` com tudo gerado.
- Modo `cliente`: conferir `git status` para garantir que nenhum arquivo de método aparece. Commit só da camada residual.

---

## Critério de pronto

- [ ] `.init-harness/config.json` existe e está correto
- [ ] Grafo gerado e git hooks do graphify ativos (ou `grafo: manual` com débito)
- [ ] `CLAUDE.md` com tier, comandos de verificação e seção `## graphify`
- [ ] `config.json` com regras de ambiente, autonomia e `frente_inativa_horas` confirmados
- [ ] `docs/ai/ESTADO.md`, `ESTRUTURA.md`, `DECISOES.md`, `DEBITOS.md` preenchidos com informação confirmada
- [ ] Enforcement mesclado e guardrails testados
- [ ] `AGENTS.md` criado ou mesclado para compatibilidade com Codex
- [ ] `harness doctor` sem erro
- [ ] Auditoria de pilares registrada
- [ ] Nenhum código de produto alterado
