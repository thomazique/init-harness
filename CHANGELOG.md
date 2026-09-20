# Changelog

## Não lançado

- Corrigida a listagem da fila: `J-<id>.analysis.json` e `.review.json`, saídas dos runners gravadas na mesma pasta, eram lidos como jobs e apareciam em `jobs` e no `total` de `status` sem `job_id` nem `status`.
- Corrigido o destino de um job cujo revisor sinaliza `needs_human: true`: ele era marcado `rejected` e sumia entre os rejeitados. Passa ao novo status `human_required`, que `review-job` aceita, junto com `review_approved`. `status` agora também conta `analyzed`, `human_required` e `promoted`.
- Sugestões de evolução passam a ser vivas: novas ocorrências do padrão atualizam `occurrences` e `evidence_event_ids` em vez de ficarem congeladas na primeira. A sugestão ganha ciclo de vida (`proposed`, `in_progress`, `addressed`); depois de promovida, só ocorrências posteriores abrem uma nova. `record` informa também `updated_suggestions`.
- Adicionados runners de referência em `.claude/skills/evolve/runners/`: `worker_static.py` (triagem determinística), `reviewer_claude.py` (revisor via `claude -p`, opt-in) e `static_eval.py` (avaliação estrutural que não mede comportamento). O exemplo de `init-evaluation` passa a trazer `"example": true`. Os testes cobrem também a fila, o worker, o revisor e a decisão humana, que não tinham nenhum.
- O instalador deixou de distribuir `__pycache__` e `.pyc` das árvores gerenciadas (`managed_paths`).
- Corrigida a fila de evolução: os jobs eram processados em ordem aleatória (ordenados pelo UUID do arquivo) e passam a seguir a ordem de criação.
- Adicionada a skill `evolve` e os comandos `proposal-context` e `submit-candidate`, que fecham o passo entre `propose` e `evaluate`: um agente lê a evidência, escreve a candidata, registra o resumo e leva a proposta até a avaliação, sem promover a skill. Testes cobrem o contexto, a validação da candidata e o registro das skills de método no instalador.
- Corrigida a promoção de propostas: `accept` agora recusa uma candidata alterada depois da avaliação, que antes podia virar a skill ativa sem ter sido avaliada.
- Corrigido frontmatter das skills `commit` e `spec`, que começava com linha em branco e ficava sem `description` no catálogo e no cliente. Adicionado teste contra as skills reais do kit.
- Adicionada ativação automática da skill da sessão: `PreToolUse` na ferramenta `Skill` chama `skill_observe.py`, que ativa skills do catálogo do projeto. Ao trocar de skill, a experiência da anterior é fechada antes da troca.
- `doctor.py` passou a exigir os hooks de evolução de skills, o registro de `skill_observe.py` em `settings.json` (incluindo o matcher `Skill`) e a validar o frontmatter de cada `SKILL.md` (começa na linha 1, `name` igual ao diretório, `description` não vazia).

## 3.0.0 — evolução assíncrona de skills

- Adicionado catálogo local de skills com manifestos, experiências, sugestões, propostas, avaliações e promoção versionada.
- Adicionado registro manual por `/record` e captura estruturada via `capture-hook`.
- Adicionado contexto de skill por sessão com `activate`, `active` e `deactivate`.
- Adicionada observação de `PostToolUse` e `PostToolUseFailure`, com agregação de chamadas, falhas, duração e arquivos.
- Adicionada consolidação automática de experiências no hook `Stop`.
- Adicionado dataset de avaliação versionável, schema de casos e `validate-cases`.
- Adicionada fila persistente de jobs de evolução.
- Adicionados worker econômico e revisor caro como runners configuráveis e executados sem shell.
- Adicionado gate de decisão humana com `review-job` e painel `status`.
- Adicionado bootstrap inicial do projeto com sincronização do catálogo e `bootstrap/report.json`.
- Sessões passam a exibir o estado da fila e das revisões no briefing inicial.

O harness permanece agnóstico de provedor: cada projeto conecta seus próprios runners
econômico e caro. Nenhum worker promove uma skill ou altera o `SKILL.md` ativo sem
avaliação e aprovação explícitas.

## [Unreleased]

Próximas melhorias permanecem condicionadas à validação em projetos reais.

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
- Opção `init_harness.py install --bootstrap`, que prepara e executa apenas a leitura do mapa existente.

## [2.2.0] - 2026-09-16

### Adicionado

- Memória local com SQLite FTS5 reconstruível, briefing de recuperação de contexto, handoffs versionáveis e MCP stdio opcional.
- Testes unitários e de integração para memória e transferência entre sessões.

### Segurança

- A memória não captura prompts, comandos ou tool calls; conteúdo recuperado é apresentado como evidência histórica.

## [2.1.0] - 2026-09-14

### Adicionado

- CLI idempotente para instalação, atualização, migração e diagnóstico.
- Configuração neutra em `.init-harness/config.json`, adaptador Codex, níveis de autonomia, guardrails e CI multiplataforma.

### Alterado

- Projeto renomeado de `claude-harness` para `init-harness`.
- Documento principal renomeado para `INIT-HARNESS.md`.
