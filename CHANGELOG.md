# Changelog

Todas as mudanças relevantes do init-harness são registradas neste arquivo.

## [Unreleased]

### Adicionado

- Documentação pública de licença, segurança, privacidade, contribuição, suporte e conduta.
- Templates de issue e pull request para relatos reproduzíveis e revisão de segurança.
- Roadmap com avaliação em projetos reais e sincronização de equipes explicitamente registradas para o futuro.

## [2.3.2] - 2026-09-17

### Corrigido

- Upgrade mantém baseline do kit para instalações antigas, reconhece hooks shell customizados e limpa candidatos de atualização já resolvidos.
- `doctor` ignora referências textuais de débitos e mostra atualizações de kit pendentes de revisão.

## [2.3.1] - 2026-09-17

### Corrigido

- Upgrade preserva conteúdo local de arquivos gerenciados e oferece a versão nova para revisão, sem sobrescrita silenciosa.
- Diagnósticos de branch, IDs duplicados, UTF-8 no Windows, sugestões de relação e modo cliente.
- Bootstrap filtra comunidades pequenas e de documentação por padrão; o limite é configurável.

### Alterado

- `doctor` orienta a correção de `uv` ausente do PATH sem assumir caminhos específicos da máquina.

## [2.3.0] - 2026-09-17

### Adicionado

- Painel operacional `memory.py status`, somente leitura, para contexto, diagnóstico, impacto e itens de revisão.
- Mapa inicial opt-in por comunidades do Graphify, com feedback local versionável em Markdown.
- Opção `init_harness.py install --bootstrap`, que prepara e executa apenas a leitura do mapa existente; não executa Graphify nem cria estrutura automaticamente.

## [2.2.0] - 2026-09-16

### Adicionado

- Memória local: documentos Markdown canônicos indexados por SQLite FTS5 reconstruível.
- Briefing de recuperação de contexto no `SessionStart` e comando portátil `memory.py query`.
- Handoffs explícitos, versionáveis e pesquisáveis em `docs/ai/memoria/handoffs/`.
- Aceite único de handoff, com estado tipado no índice local e registro auditável no Markdown.
- Servidor MCP stdio opcional e sem dependências para briefing, busca e handoffs.

### Segurança

- A memória não captura prompts, comandos ou tool calls; handoffs rejeitam padrões fortes de segredo.
- Conteúdo recuperado é apresentado como evidência histórica, nunca como instrução executável.

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
