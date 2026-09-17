# init-harness

Inicializa repositórios Git para trabalho contínuo com agentes de IA. O kit
combina contexto persistente, frentes e specs, validação, segurança operacional
e adaptadores para Claude Code e Codex.

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

Em um projeto novo que já tenha `graphify-out/graph.json`, o mapa inicial é opt-in e revisável:

```powershell
python init_harness.py install --target C:\projeto --bootstrap
# Se o grafo ainda não existir, o bootstrap apenas informa o próximo passo.
python .claude/hooks/memory.py bootstrap
python .claude/hooks/memory.py bootstrap --accept B-... --note "Área confirmada na arquitetura."
```

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
- `tests/guardrails/`: testes copiados para cada instalação em modo próprio.

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
