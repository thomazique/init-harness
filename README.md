# init-harness

Inicializa repositórios Git para trabalho contínuo com agentes de IA. O kit
combina contexto persistente, frentes e specs, validação, segurança operacional
e adaptadores para Claude Code e Codex.

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
- `docs/ai/` e `specs/`: memória operacional do projeto.
- `.githooks/`: enforcement independente do agente.
- `tests/guardrails/`: testes copiados para cada instalação em modo próprio.

## Segurança

Os hooks reduzem risco, mas não substituem sandbox, proteção de branch,
isolamento de credenciais e revisão humana para produção ou ações destrutivas.

## Desenvolvimento

```powershell
python -m unittest discover -s tests -p "test_*.py"
ruff check .
ruff format --check .
```

Repositório: https://github.com/thomazique/init-harness
