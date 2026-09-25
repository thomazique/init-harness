# init-harness 4.0.0

`init-harness` instala e atualiza uma base operacional para trabalhar com agentes de IA em
repositórios Git. Mantém protocolo e contexto do projeto em arquivos versionáveis, registra
o andamento entre sessões, conecta memória local e grafo de código, e adiciona skills e
guardrails ao fluxo de trabalho. O harness serve a projetos diferentes: preserva os arquivos
do projeto e adapta suas instruções ao código e às ferramentas existentes.

A versão **4.0.0** muda o protocolo padrão para trabalho multiagente: o agente principal coordena,
divide a atividade entre executores com escopos explícitos e solicita auditoria independente do
diff agregado. O fluxo tem adaptadores nativos para Claude Code e Codex, protege alterações
preexistentes e encaminha achados do auditor de volta aos executores.

A versão **3.2.2** adicionou testes de contrato para o verificador da skill de frontend,
cobrindo os modos consultivo e `--strict`, avisos, comentários, tokens e descoberta de arquivos.
A versão **3.2.1** adicionou testes de regressão para os caminhos de atualização segura do
instalador: baseline do kit sem baseline anterior, hooks customizados sem `args`, referências
a débitos fora das tabelas e limpeza de candidatos `.new` resolvidos. A versão **3.2.0**
adicionou uma skill de frontend generalizada para qualquer stack: agentes devem consultá-la em
toda tarefa de interface, descobrir primeiro o contexto do projeto e seguir seus próprios
padrões de produto. O analisador é consultivo por padrão e só falha quando o projeto opta por
`--strict`.

## O que o harness oferece

- **Instalação e atualização seguras:** `install`, `upgrade` e `doctor`; preserva arquivos
  existentes e apresenta mudanças de arquivos gerenciados para revisão.
- **Continuidade entre sessões:** frentes, checkpoints, specs, decisões, débitos e handoffs
  documentam estado, próximos passos e contexto de implementação.
- **Memória pesquisável local:** índice reconstruível SQLite FTS5 para Markdown, consulta e
  briefing; o texto versionável permanece a fonte de verdade. Integração MCP é opcional.
- **Grafo de código e impacto:** integração com Graphify para consultar estrutura, caminhos e
  arquivos afetados. O modo manual permite instalar sem Graphify.
- **Protocolos e guardrails:** adaptadores para Claude Code e Codex, skills operacionais,
  hooks e verificações Git para reduzir riscos no fluxo de edição.
- **Orquestração multiagente:** agente principal coordena; executores recebem tarefas e arquivos
  delimitados; um auditor independente revisa o diff agregado e aprova ou reprova antes da
  conclusão. Perfis base por atividade permitem usar agentes nativos ou combinar Claude Code e
  Codex por meio dos CLIs autenticados localmente.
- **Aprendizado controlado de skills:** captura experiências locais, agrupa sugestões,
  mantém fila e propostas, avalia candidatas e exige decisão humana antes de promover uma
  skill ativa.
- **Bootstrap revisável:** opcional; mapeia o projeto existente e prepara contexto inicial,
  mantendo hipóteses arquiteturais como propostas revisáveis.
- **Modo de implantação:** `proprio` mantém o método no projeto; `cliente` exclui os arquivos
  de método do versionamento e os remove no offboarding.

## Destaque da versão 3.2: frontend adaptável

A skill `.claude/skills/frontend/` cobre criação, revisão e correção de páginas, telas,
componentes, navegação, estilos, tokens, acessibilidade, estados, layout responsivo e motion.
Ela não exige um framework ou diretório específico. Antes de editar, orienta o agente a ler as
instruções locais, detectar a stack, encontrar o tema e os componentes já usados, entender a
tarefa e escolher as validações do próprio projeto.

As referências dividem o método por decisão visual (Operate/Persuade), sistema de tokens,
componentes e acessibilidade, movimento e layout e revisão. O analisador Python opcional cobre
alguns padrões mecânicos em arquivos web e Dart; seus diagnósticos são heurísticos, não uma
medida universal de qualidade. O modo bloqueante `--strict` só é indicado quando a equipe
decidir que essas regras se aplicam à sua stack.

## Destaque da versão 4.0: execução coordenada por agentes

Em solicitações de implementação, o agente principal atua como coordenador e delega as mudanças
a agentes executores. Cada subtarefa recebe objetivo, critérios de aceite, dependências e arquivos
autorizados. O coordenador controla a ordem, preserva mudanças preexistentes, espera os executores
e compara seus relatórios com os arquivos realmente alterados.

Depois que as escritas terminam, um auditor separado e somente de leitura confere o diff completo
contra o pedido e os critérios de aceite. Uma reprovação devolve os achados aos executores e exige
uma nova auditoria. O coordenador controla a integração por delegação e só conclui com aprovação
do auditor e validações relatadas.

Claude Code usa `.claude/agents/executor.md` e `.claude/agents/revisor.md`. Codex usa
`.codex/agents/harness_executor.toml` e `.codex/agents/harness_auditor.toml`. O protocolo comum
está em `.claude/skills/orquestrar/SKILL.md` e em `INIT-HARNESS.md`. O coordenador mantém uma fila
de tarefas com dependências e donos de arquivos, inicia tarefas independentes até o limite e
preenche vagas quando um executor termina. A configuração inicial permite até três executores
ativos. Tarefas que dependem umas das outras ou alteram os mesmos arquivos seguem em sequência;
uma única auditoria confere o diff consolidado.

As subtarefas de uma atividade ficam no quadro `Tarefas delegadas` de uma única frente. O quadro
registra quem executa, dependências, arquivos e resultado. Não é necessário abrir uma frente por
executor. Frentes de produto separadas continuam em branches e worktrees próprias para manter o
isolamento já exigido pelo harness.

### Modelos, concorrência e custo

`orquestracao.limite_executores` em `.init-harness/config.json` define o limite usado pelo
protocolo. Para mudar o limite máximo efetivo, ajuste também
`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` em `.claude/settings.json` ou
`agents.max_concurrent_threads_per_session` em `.codex/config.toml`, conforme o cliente. Os modelos
são configuráveis nos perfis nativos: `model` nos arquivos `.claude/agents/*.md`; `model` e
`model_reasoning_effort` em `.codex/agents/*.toml`.

No início de cada atividade, o coordenador pergunta qual perfil usar em
`.init-harness/orquestracao.json` e registra a escolha na frente daquela atividade. Tarefas
simultâneas podem escolher perfis diferentes sem sobrescrever uma configuração global. O arquivo
define provedor e modelo para coordenador, executores e auditor e pode ser editado pelo projeto.

Os perfis iniciais incluem `claude_opus_codex_luna` (Claude Opus coordena e audita; Codex GPT-6
Luna executa) e `codex_luna_claude_opus` (Codex GPT-6 Luna coordena e executa; Claude Opus audita),
além de opções nativas para cada cliente. Os perfis híbridos chamam os CLIs instalados localmente,
que precisam estar autenticados na conta de cada provedor. Uma configuração só é usada quando
escolhida para a atividade.
Em perfis nativos do Codex, alinhe o modelo do arquivo com `model` em `.codex/agents/*.toml`; os
perfis `cli` aplicam diretamente o modelo escolhido no arquivo de orquestração.

O arquivo `.init-harness/state/orquestracao.sqlite3` guarda metadados das chamadas CLI, sem prompts
ou respostas. O runner desativa a persistência local de sessões nos dois CLIs. `limite_chamadas_cli_por_atividade`
limita quantas invocações externas são iniciadas; `--remover-lote` apaga o JSON temporário com as
instruções depois que o runner o lê. Isso não altera a retenção ou o uso de dados pelo provedor.

Os perfis iniciais usam Sonnet para execução e Opus para auditoria no Claude Code. No Codex, usam
GPT-6 Luna com raciocínio `high` para execução e auditoria. O modelo do coordenador é o selecionado
na sessão. Escolha modelos disponíveis na conta e no cliente em uso.

O coordenador abre só executores com tarefas independentes e contexto delimitado, e o auditor revisa
o diff consolidado uma vez. Subagentes geram chamadas extras e podem elevar o consumo. O limite de
concorrência controla quantos rodam ao mesmo tempo; ele não estabelece um teto de custo nem garante
que a conta final não aumente. Os controles financeiros dependem do plano e do provedor.

Os perfis híbridos usam as contas, cotas e políticas de dados dos provedores selecionados. O limite
de concorrência reduz o pico de chamadas e o limite por atividade controla o número de processos
CLI; nenhum deles define um teto monetário ou garante que o custo final não aumente.

O fluxo depende das ferramentas de subagentes disponíveis no cliente e na sessão ativa. As
instruções e os perfis configuram os papéis; eles não substituem permissões, sandbox, revisão de
código ou os gates de commit e deploy do projeto.

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
e recebem somente migrações conhecidas. No `AGENTS.md`, a instrução padrão antiga
de delegação condicional é atualizada para o protocolo multiagente 4.0; instruções
personalizadas que não correspondam ao bloco padrão permanecem intactas.

## Arquitetura

- `INIT-HARNESS.md`: protocolo comum e versionado.
- `.init-harness/config.json`: política específica da instalação.
- `.init-harness/schema/`: contrato da configuração.
- `.claude/`: adaptador, hooks, agentes e skills do Claude Code.
- `.codex/agents/`: perfis nativos de executor e auditor para Codex.
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
