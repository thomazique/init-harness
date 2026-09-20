# init-harness 3.0.0

Inicializa repositórios Git para trabalho contínuo com agentes de IA. A versão
3.0 introduziu um ciclo controlado de aprendizado de skills e a 3.1 o fecha: a skill
usada na sessão é ativada sozinha, o projeto coleta experiências, um agente econômico
faz a triagem em background, um revisor caro só vê o que exige julgamento, a aprovação
humana abre uma proposta, a skill `evolve` escreve a candidata e a promoção só acontece
depois de uma avaliação e de uma decisão humana explícita.

> Estado: projeto em evolução. O harness ajuda a estruturar trabalho com IA,
> mas não substitui revisão humana, sandbox, CI, backups ou controles de acesso.

## Requisitos

- Git
- Python 3.10 ou superior
- `uv` recomendado para execução isolada
- Graphify opcional; use `--graph manual` quando não estiver disponível

## Instalação em um projeto

Clone este repositório e execute, a partir da cópia do kit:

```powershell
python init_harness.py install --target C:\caminho\do\projeto --init-git
```

Somente Claude Code:

```powershell
python init_harness.py install --target C:\projeto --providers claude
```

Visualizar as mudanças sem escrever:

```powershell
python init_harness.py install --target C:\projeto --dry-run
```

Memória MCP é opcional e não altera a configuração do cliente automaticamente:

```powershell
python init_harness.py install --target C:\projeto --memory-mcp
# No cliente MCP escolhido, registre: python .claude/hooks/memory_mcp.py
```

Bootstrap inicial do projeto:

```powershell
python init_harness.py install --target C:\projeto --bootstrap
# Cria o contexto inicial, sincroniza skills e grava .init-harness/bootstrap/report.json
```

O bootstrap preserva arquivos existentes, registra frentes e débitos encontrados,
prepara memória e catálogo de skills e mantém hipóteses arquiteturais como propostas
revisáveis. A análise semântica do Graphify continua uma etapa explícita quando o
projeto ainda não possui `graphify-out/graph.json`.

## Atualização

Atualize primeiro esta cópia com `git pull` e depois execute:

```powershell
python init_harness.py upgrade --target C:\projeto --dry-run
python init_harness.py upgrade --target C:\projeto
python init_harness.py doctor --target C:\projeto
```

O upgrade substitui apenas arquivos gerenciados pelo kit. `CLAUDE.md`,
`AGENTS.md`, `docs/ai/` e a configuração específica do projeto são preservados
e recebem somente migrações de referências conhecidas.

## Arquitetura

- `INIT-HARNESS.md`: protocolo comum e versionado.
- `.init-harness/config.json`: política específica da instalação.
- `.init-harness/schema/`: contrato da configuração.
- `.claude/`: adaptador, hooks, agentes e skills do Claude Code.
- `AGENTS.md`: adaptador do Codex gerado no projeto.
- `docs/ai/` e `specs/`: memória operacional do projeto, pesquisável localmente por SQLite FTS5 reconstruível.
- `docs/ai/memoria/handoffs/`: transições explícitas e versionáveis entre sessões/agentes.
- `.githooks/`: enforcement independente do agente.
- `.init-harness/skills/`: catálogo, experiências, propostas, avaliações e fila de evolução do projeto.
- `.init-harness/bootstrap/report.json`: relatório factual produzido durante o bootstrap.
- `tests/guardrails/`: testes copiados para cada instalação em modo próprio.

## Evolução assíncrona de skills

O fluxo de evolução (introduzido na 3.0, completo na 3.1) é:

```text
uso da skill (ativada automaticamente na sessão)
  → experiência observada
  → sugestão (acumula ocorrências enquanto aberta)
  → fila persistente
  → worker econômico (triagem)
  → revisor caro
  → aprovação humana (review-job)
  → proposta
  → candidata escrita pela skill evolve
  → avaliação
  → promoção por decisão humana (accept)
```

Os hooks não chamam modelos nem bloqueiam a sessão. O kit traz runners de referência em
`.claude/skills/evolve/runners/` (triagem determinística, revisor via `claude -p` e avaliação
estrutural); cada projeto pode substituí-los pelos seus:

```powershell
python .claude/hooks/skill_worker.py --runner .claude/skills/evolve/runners/worker_static.py --interval 30
python .claude/hooks/skill_reviewer.py --runner .claude/skills/evolve/runners/reviewer_claude.py --interval 60
python .claude/hooks/skill_evolution.py status
```

O worker econômico pode propor análises, mas não promove skills. O revisor caro valida
as evidências, e a promoção continua dependendo de uma decisão humana explícita.
Experiências não capturam prompts, credenciais ou raciocínio privado. Um job que falhou
volta à fila com `retry-job`, e o job de um worker encerrado à força é recuperado sozinho.

A candidata de uma proposta é escrita pela skill `/evolve`: ela lê a evidência
(`proposal-context`), edita somente a cópia candidata, registra o resumo
(`submit-candidate`) e leva a proposta até a avaliação. Nunca promove a skill.

## Segurança

Os hooks reduzem risco, mas não substituem sandbox, proteção de branch,
isolamento de credenciais e revisão humana para produção ou ações destrutivas.

Leia [SECURITY.md](SECURITY.md) antes de habilitar MCP, Graphify ou qualquer
integração externa. O projeto não coleta telemetria própria; veja
[PRIVACY.md](PRIVACY.md) para dados locais e integrações opt-in.

## Projeto público

- [Contribuir](CONTRIBUTING.md): ambiente, verificações e regras de mudança.
- [Suporte](SUPPORT.md): dúvidas, bugs e limites de suporte.
- [Código de conduta](CODE_OF_CONDUCT.md): convivência nos espaços oficiais.
- [Roadmap](docs/ROADMAP.md): direção atual e frentes futuras sob validação.
- [Licença MIT](LICENSE): uso, modificação e distribuição.

## Desenvolvimento

```powershell
python -m unittest discover -s tests -p "test_*.py"
ruff check .
ruff format --check .
```

Repositório: https://github.com/thomazique/init-harness
