# Changelog

Todas as mudanças relevantes do init-harness são registradas neste arquivo.

## [2.1.0] - 2026-09-14

### Adicionado

- CLI idempotente para instalação, atualização, migração e diagnóstico.
- Configuração neutra em `.init-harness/config.json` e respectivo JSON Schema.
- Adaptador Codex por meio de `AGENTS.md`.
- Níveis explícitos de autonomia para tarefas seguras e ações de risco.
- Testes unitários e de integração dos guardrails e do instalador.
- Workflow de CI em Windows e Linux com Python 3.10–3.13.
- Diagnóstico de integridade, portabilidade, Graphify e conflitos de frentes.

### Alterado

- Projeto renomeado de `claude-harness` para `init-harness`.
- Documento principal renomeado para `INIT-HARNESS.md`.
- Skill de implantação renomeada para `init-harness`.
- Conteúdo editorial e artefatos deixam de ser classificados como código.
- Uma branch passa a aceitar no máximo uma frente não concluída.

### Migração

O comando `python init_harness.py upgrade --target <projeto>` migra instalações
2.0.0/2.1.0 legadas, preservando arquivos específicos do projeto.
