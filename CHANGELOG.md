# Changelog

## 3.2.2 — verificador de frontend protegido por testes

### Testes

- Adicionada cobertura de contrato para os modos consultivo e `--strict`, avisos sem bloqueio, remoção de comentários, exclusão de arquivos gerados/minificados e cores definidas em tokens.

## 3.2.1 — regressões de upgrade cobertas por testes

### Testes

- Adicionados quatro testes para as correções de #13 a #16: baseline do conteúdo do kit após upgrade sem baseline, hook customizado sem `args`, referência textual a débito fora da tabela e ciclo de vida do candidato `.new`.
- O teste de IDs duplicados também confirma que duas declarações em linhas da tabela continuam sendo detectadas.

## 3.2.0 — skill de frontend adaptável ao projeto

### Adicionado

- Skill de frontend agnóstica de framework, acionada para criar, revisar ou alterar interfaces web, mobile e desktop. Antes de propor mudanças, identifica stack, padrões de produto e ferramentas do repositório.
- Integração da skill ao instalador, ao catálogo de skills do harness e aos templates de `AGENTS.md` e `CLAUDE.md`, para ser consultada em qualquer tarefa de frontend.
- Analisador de padrões de frontend em modo consultivo por padrão, com opção `--strict` quando as regras forem adotadas pelo projeto.

### Alterado

- As referências de modos de interface, tokens, componentes, acessibilidade, motion, layout e revisão foram generalizadas para projetos e plataformas diferentes.
- As heurísticas do analisador deixam de bloquear por padrão; formatos e diretórios gerados comuns foram ampliados para uso em stacks diversas.

## [Unreleased]

## 3.1.0 — ciclo de evolução de skills completo

- Ajustes apontados por testes com um agente real (`claude -p`) e com `upgrade` de projetos 3.0: a skill `evolve` traz a sintaxe do `accept`, pede `--owner` sem e-mail (o campo é versionado) e manda decisões de política ao usuário; o `doctor` aponta o `.new` do kit quando uma skill editada localmente está quebrada; e `configure-usage` grava o risco também no manifesto, que divergia do contrato.
- Corrigida a falha de jobs: `retry-job` devolve um job `failed` à fila (à revisão, se já havia análise); um job `processing` de um worker morto é marcado `failed` sozinho após 30 minutos (`recover-jobs` faz isso sob demanda); um `.worker.lock` com mais de 60 s deixa de bloquear a fila; e os arquivos de job passam a ser gravados de forma atômica. O revisor conta `review_attempts`.
- Corrigida a validação de caminhos relativos: `..\segredo.txt` era aceito no Linux, onde a barra invertida não é separador para `Path`. `record --file`, os arquivos observados nos hooks e o arquivo de resultados de avaliação agora recusam `..` e caminhos absolutos escritos com `/` ou `\` em qualquer sistema. Esse teste já falhava nos 4 jobs de Linux da CI da `main`.
- Ligada a fila às propostas: `review-job --decision approved` abre a proposta de evolução (reusando ou criando a sugestão da experiência), o job guarda `proposal_id` e `suggestion_id`, e `accept` marca os jobs vinculados como `promoted`. A decisão não é gravada se a proposta não puder ser criada. `review-job` ganhou `--owner`; o ciclo de status dos jobs está documentado no `INIT-HARNESS.md`.
- Corrigida a listagem da fila: `J-<id>.analysis.json` e `.review.json`, saídas dos runners gravadas na mesma pasta, eram lidos como jobs e apareciam em `jobs` e no `total` de `status` sem `job_id` nem `status`.
- Corrigido o destino de um job cujo revisor sinaliza `needs_human: true`: ele era marcado `rejected` e sumia entre os rejeitados. Passa ao novo status `human_required`, que `review-job` aceita, junto com `review_approved`. `status` agora também conta `analyzed`, `human_required` e `promoted`.
- Sugestões de evolução passam a ser vivas: novas ocorrências do padrão atualizam `occurrences` e `evidence_event_ids` em vez de ficarem congeladas na primeira. A sugestão ganha ciclo de vida (`proposed`, `in_progress`, `addressed`); depois de promovida, só ocorrências posteriores abrem uma nova. `record` informa também `updated_suggestions`.
- Adicionados runners de referência em `.claude/skills/evolve/runners/`: `worker_static.py` (triagem determinística), `reviewer_claude.py` (revisor via `claude -p`, opt-in) e `static_eval.py` (avaliação estrutural que não mede comportamento). O exemplo de `init-evaluation` passa a trazer `"example": true`. Os testes cobrem também a fila, o worker, o revisor e a decisão humana, que não tinham nenhum.
- O instalador deixou de distribuir `__pycache__` e `.pyc` das árvores gerenciadas (`managed_paths`).
- Corrigida a fila de evolução: os jobs eram processados em ordem aleatória (ordenados pelo UUID do arquivo) e passam a seguir a ordem de criação, dada por um campo `sequence` (o horário sozinho empata no Windows).
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
