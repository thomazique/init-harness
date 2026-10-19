# Changelog

## 5.1.3 — retomada de toda pausa, preflight e frente única

Correções vindas da frente de segurança de um projeto com supervisor e construtor Codex no Windows: a frente terminou aprovada, mas precisou de 4 iniciativas porque três pausas não tinham retomada, e mais da metade das chamadas foi para pausas de metadado ou de pergunta derivável da spec.

### Corrigido

- Conflito entre supervisores, colisão de arquivo dentro da frente e conflito de arquivos entre frentes pausavam sem `pending_checkpoint`, e `--retomar` mandava abrir outra iniciativa. Agora voltam ao plano: `--retomar` refaz os planos afetados lendo a spec atual e refaz o alinhamento. Com `--respostas`, cada resposta repete um item de `blockers` e vai ao novo plano.
- Resposta humana no alinhamento só refazia o alinhamento, que acusava conflito com o plano antigo. Agora refaz o plano da frente com as decisões humanas e o plano anterior no prompt, e depois o alinhamento de todas as frentes.
- Auditoria de supervisor reprovada pausava sem caminho de volta. Agora todas as frentes são auditadas e a iniciativa vai para `aguardando_auditoria_chefe` com `auditorias_reprovadas` e os achados em `blockers`. O chefe usa `revise` com os achados para reconstruir e reauditar; a reauditoria recebe as auditorias anteriores e as revisões.
- Limites excedidos, arquivos atribuídos que já tinham alterações e arquivos fora do escopo no fim da construção também ganham retomada, do ponto em que pararam.
- Pausas gravadas pela 5.1.2 sem etapa recebem uma pelo motivo quando retomadas, então as iniciativas já pausadas não precisam ser refeitas.
- Com duas frentes no mesmo repositório, a conferência final acusava os arquivos da outra frente como fora do escopo.
- A auditoria via `graphify-out/` como diff da tarefa. O prompt agora lista os arquivos da iniciativa, os caminhos ignorados (padrão e `caminhos_ignorados`) e os arquivos já alterados antes da iniciativa, e diz para não usar `git status` cru. O diff e a varredura de gates cobrem só os arquivos atribuídos.
- `memory.py briefing` falhava com `unable to open database file` no worktree temporário ou em sandbox somente leitura. Agora imprime o contexto do Markdown e avisa que o índice está indisponível.
- O runner (`invocar_agentes.py`) e os CLIs de evolução de skills quebravam com `'charmap' codec can't encode` ao imprimir JSON em console cp1252. Agora forçam UTF-8 como os hooks.

### Adicionado

- Preflight determinístico antes da primeira chamada. Recusa sem criar estado quando o `base_commit` da spec difere do manifesto ou quando `files` da spec tem glob, seta ou path fora do scope. Arquivo da frente fora do scope vira aviso no prompt do plano e em `preflight` do relatório. O prompt do plano diz que o scope do manifesto prevalece sobre o texto da spec e da frente e que esses metadados não são motivo de pergunta.
- Com uma frente só, o alinhamento é pulado sem chamada; o mínimo de `max_calls` cai para 3 por frente mais os construtores.
- Mesmo arquivo em duas tarefas da frente e fechamento que muda tarefas ou arquivos do plano viram erro de formato com reparo gratuito, em vez de pausa.

## 5.1.2 — orquestração com Codex, reparo de formato e retomada

Correções vindas de uma execução real no Windows com supervisor e construtor Codex, em que duas iniciativas e 14 chamadas terminaram sem nada integrado.

### Corrigido

- `codex exec` atual recusa `--ask-for-approval`; o runner passa `--config approval_policy="never"`.
- A integração copiava o arquivo do próprio repositório principal, e não do worktree do construtor, e por isso nenhuma tarefa concluída chegava ao repositório. Existia desde a 5.0.0 e não era visível porque nenhum teste percorria a iniciativa inteira; agora um teste de ponta a ponta com CLI falso cobre o fluxo.
- `git status -z` traz a origem de uma renomeação numa entrada sem prefixo de status; o runner cortava esse caminho e acusava arquivo inexistente fora do escopo depois de um `git mv`.
- Saídas do ambiente (`graphify-out/`, `.init-harness/skills/`, `__pycache__`, além de `.init-harness/state/`) não pausam mais a construção como "repositório principal mudou" nem contam no worktree do construtor. `caminhos_ignorados` em `orquestracao.json` acrescenta outras.
- Hooks escrevem e leem UTF-8 também em console Windows com outra página de código; mensagens como "Há código alterado" chegavam com acentos quebrados.
- JSON em cerca de código com fim de linha CRLF não era reconhecido.

### Adicionado

- Codex recebe `--output-schema` por etapa (plano, alinhamento, consulta, fechamento, construtor e auditoria), gerado a partir de `$defs` de `orquestracao.schema.json`; o schema ganhou `consulta_construtor` e `auditoria_supervisor`.
- Todos os prompts de etapa dizem que os campos descritivos são listas de strings, com exemplo; objetos nessas listas são convertidos em texto JSON em vez de reprovar a resposta.
- Resposta reprovada na validação recebe um reparo de formato somente leitura, que não conta em `max_calls` (fica em `repair_calls`). Um trecho truncado da resposta reprovada fica em `invalid_responses` do estado.
- Construtor recusado ou bloqueado deixa em `build_attempts` o motivo, os arquivos fora do escopo e `risks`/`questions`; ao retomar, a tentativa vai para `build_history`. Arquivo que o Git ignora e o construtor relata fica em `generated_files_ignored`.
- O manifesto é copiado para `.init-harness/state/orquestracao/<id>/manifesto.json`; `--retomar <initiative_id>` retoma sem o arquivo original e, sem perguntas pendentes, refaz a etapa pausada (construtor bloqueado, repositório que mudou).
- Depois dos planos, o runner confere se `max_calls` cobre o restante do fluxo e para com a conta antes de gastar chamadas. Mudar só `limits` não troca a identidade da iniciativa; aumente o valor e rode de novo.
- Prompt do supervisor e skill `spec` exigem em `files` paths explícitos, um por item, sem glob nem seta; mover arquivo declara origem e destino.
- `gate_diff`: linha com `gate-ok: <motivo>` sai da marcação e o motivo vira nota do trecho; blocos do `graphify hook install` não são marcados.

## 5.1.1 — correções do agente auditor, do esforço via CLI e do doctor

### Corrigido

- `auditor-pilares` não iniciava: o frontmatter listava as ferramentas em minúsculas (`[read, grep, glob, bash]`); agora usa os nomes exatos do Claude Code (`Read, Grep, Glob, Bash`).
- O runner CLI ignorava `raciocinio` nos perfis do Claude; agora passa `--effort <nível>`. O valor é validado contra o enum do schema (`low`, `medium`, `high`, `xhigh`) para Claude e Codex, porque o CLI do Claude ignora em silêncio um valor desconhecido.
- O `doctor` contava o modelo de entrada comentado do `DECISOES.md` como ID duplicado da primeira decisão real; IDs dentro de comentário HTML deixam de contar. O exemplo do template passou a usar `D-XXXX`.

## 5.1.0 — integridade de gates, depuração por causa raiz e guardrails mais amplos

Práticas adaptadas do gstack (MIT) e do Anthropic-Cybersecurity-Skills (Apache-2.0); origem em `NOTICE.md`.

### Adicionado

- `.claude/hooks/gate_diff.py`: lista no diff os trechos que afrouxam um gate (RH-1 teste removido ou pulado, RH-3 snapshot sem o teste dono, RH-4 placeholder, RH-12 código que detecta teste/CI, RH-13 supressão de lint, RH-14 gate contornado, RH-15 limiar ou timeout relaxado, RH-16 exceção engolida). Modos árvore de trabalho, `--staged` e `--base`; caminhos extras em `guardrails.gates`.
- Pre-commit avisa, sem falhar, sobre gates afrouxados no que está em stage.
- Orquestração: a auditoria do supervisor recebe a seção GATES do escopo da frente e o `relatorio_para_chefe.json` traz o campo `gates` por frente.
- Skill `investigar`: depuração por causa raiz com hipótese testável, regra das 3 tentativas, teste de regressão que falha antes da correção, limite de 5 arquivos e receita para teste intermitente.
- Princípios 7 (afirmação exige evidência) e 8 (gate não se afrouxa para passar) e status de conclusão (CONCLUÍDO, CONCLUÍDO_COM_RESSALVAS, BLOQUEADO, FALTA_CONTEXTO) no `INIT-HARNESS.md`.
- `doctor` avisa description de skill sem gatilho ou sem gatilho negativo, acima de 1024 caracteres, `SKILL.md` acima de 500 linhas e pares de skills que concorrem pelo mesmo pedido.
- Pilares: autorização em todo caminho, comando/caminho/desserialização, segredo fora de log e URL, uso correto de criptografia, sessão e troca de identidade, webhook, CI/CD, memória do agente, MCP de terceiro, skills e hooks de fora revisados como código, gates íntegros; rubrica de consequência, confiança e evidência; referências OWASP 2025, API 2023 e LLM 2025.
- Supervisor de segurança com modelo da mudança, STRIDE por fronteira, checklist de autorização, injeção, criptografia, LLM/MCP e CI/CD e rubrica do achado.

### Alterado

- `guard_bash`: pede confirmação para `git checkout .`, `git restore .`, `git stash clear|drop`, force-push por refspec `+`, remoção de branch remota, `kubectl delete`, `helm uninstall`, `terraform destroy`, `docker rm -f`, aliases de PowerShell (`ri -r -fo`), `rd /s` do cmd, `Clear-Disk`/`Format-Volume` e comandos ofuscados ou não inspecionáveis (`${IFS}`, base64 para shell, `iex`, `-EncodedCommand`). Nega remoção recursiva da raiz ou da home e force-push na branch padrão em comando simples. Remoção só de pastas de build conhecidas (`node_modules`, `dist`, `__pycache__`...) deixa de pedir confirmação. `guardrails.bash_extras` acrescenta padrões do projeto.
- Descriptions das skills do kit ganharam gatilho negativo apontando a skill vizinha.

## 5.0.2 — Jev opcional para contexto e triagem de orquestração

### Adicionado

- Opt-in global `jev.enabled` na configuração do projeto e opção `--jev` no instalador; o padrão segue em FTS5/LLM local.
- FTS5 reúne candidatos Markdown e Jev pontua até oito snippets em uma chamada; ausência de chave, baixa confiança, erro ou timeout mantém o ranking FTS5.
- CLI de triagem permite ao orquestrador enviar um estado estruturado ao Jev antes do despacho e nos gates de fase; Jev devolve rótulos tipados, nunca texto livre nem tarefas executáveis.
- `JEVMODEL_API_KEY` pode vir do ambiente ou de `.env` local; `.env.example` documenta a variável vazia e o instalador o cria apenas quando ainda não existe.
- Pergunta de opt-in na implantação descreve quais dados vão ao serviço externo; candidatos com padrões locais de segredo são excluídos do payload.

### Segurança

- `.env` e variantes locais são ignorados pelo Git; chaves não aparecem em logs, documentação gerada nem estado operacional.

## 5.0.1 — perfis de agentes por nível e provedor

### Adicionado

- Perfis iniciais separam chefe, supervisor e construtor por capacidade/custo: Opus/Sonnet/Luna no uso combinado, Sol/Terra/Luna no Codex e Opus/Sonnet/Haiku no Claude.
- Instalador filtra perfis conforme os provedores selecionados em `--providers`, sem substituir a configuração de orquestração já existente no projeto.
- Documentada a limitação do chefe: seu perfil descreve a sessão interativa esperada; o runner despacha apenas supervisores e construtores por CLI.

### Corrigido

- O supervisor deixa de usar o mesmo modelo de maior capacidade configurado para o chefe nos perfis iniciais.

## 5.0.0 — supervisores especialistas e orquestração revisável

### Adicionado

- Especialidades obrigatórias por frente: frontend, backend, segurança, deploy/CI/CD e banco de dados, com presets próprios; frontend reutiliza a skill existente.
- Contexto técnico específico por tarefa, preparado pelo supervisor para limitar o escopo recebido por cada construtor.
- Decisão final do chefe via `--decisao-chefe`: aprovação, pergunta humana ou revisão direcionada com reexecução das tarefas afetadas e dependências.
- Schemas do manifesto, retomada humana e decisão final passam a ser distribuídos pelo instalador.

### Corrigido

- Dependências entre frentes agora aguardam a conclusão de todas as tarefas da frente dependente.
- Instalação no modo cliente inclui a skill de orquestração na lista de conteúdo metodológico.
- A proposta de consolidação prioriza arquivos declarados pela frente ao resumir alterações extensas.

## 4.0.0 — orquestração multiagente padrão

### Alterado

- Agente principal passa a coordenar e delegar tarefas de implementação a executores; deixa de implementar diretamente as subtarefas delegadas.
- Auditoria independente e somente de leitura do diff agregado passa a ser gate antes da conclusão. Achados bloqueantes retornam aos executores e exigem nova auditoria.
- Subtarefas recebem arquivos autorizados e donos exclusivos por etapa; dependências são sequenciadas e mudanças anteriores do usuário são preservadas.
- O fluxo agora é distribuído pelos adaptadores nativos de cada cliente: `.claude/agents/` para Claude Code e `.codex/agents/` para Codex.
- Concorrência padrão limitada a três executores ativos; número maior de tarefas segue em etapas para reduzir escrita simultânea e sobreposição.
- Adicionada fila explícita de tarefas prontas, em andamento, bloqueadas, concluídas e auditadas; vagas são preenchidas conforme executores terminam.
- Limite configurável de executores em `.init-harness/config.json`, com controles nativos equivalentes em `.claude/settings.json` e `.codex/config.toml`.
- Perfis iniciais configuram Sonnet/Opus no Claude Code e GPT-6 Luna com raciocínio alto no Codex; modelos podem ser alterados nos arquivos de perfil.
- Adicionado `.init-harness/orquestracao.json`: o coordenador pergunta o perfil base em cada atividade e registra a escolha somente na frente correspondente, permitindo configurações diferentes em frentes simultâneas.
- Adicionados perfis híbridos configuráveis para Claude Opus + Codex GPT-6 Luna em ambas as direções, com execução via CLI headless e autenticação/cotas próprias de cada cliente.
- Adicionado runner de lotes com concorrência configurável, sandbox de escrita para executores, leitura para auditor e limite de chamadas CLI externas por atividade; o ledger local guarda metadados sem prompts ou respostas.
- Execução econômica: uma auditoria por diff consolidado e contexto restrito por subtarefa; concorrência limita o pico, sem garantir custo monetário fixo.
- Documentada a separação entre perfis nativos do cliente e perfis híbridos executados pelos CLIs autenticados localmente.
- Upgrade migra a regra padrão antiga de delegação no `AGENTS.md`, preservando o restante do arquivo e instruções personalizadas.

### Adicionado

- Skill de coordenação `orquestrar`, definições de executor para Claude Code e Codex, e perfis de auditor somente leitura para ambos.

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
