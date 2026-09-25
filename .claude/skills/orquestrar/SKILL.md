---
name: orquestrar
description: Use em toda solicitação de implementação ou alteração de software no projeto. O agente principal coordena e delega subtarefas a executores, acompanha dependências, integra o trabalho e solicita auditoria independente do diff agregado antes de concluir.
---

# Orquestração de trabalho com agentes

O agente principal atua como **coordenador**. Ele entende o pedido, divide o trabalho, delega a implementação, integra os resultados e conduz uma auditoria independente. Ele não executa diretamente as subtarefas de implementação atribuídas aos executores.

Antes de distribuir trabalho, leia `.init-harness/config.json` e `.init-harness/orquestracao.json`. O segundo arquivo contém os perfis disponíveis, os provedores/modelos por papel e o máximo de chamadas a CLIs externas por atividade. O limite de executores continua em `orquestracao.limite_executores` no primeiro arquivo.

## Escolha da configuração base

1. No começo de cada atividade de implementação, pergunte qual perfil de `.init-harness/orquestracao.json` será a base. Mostre os IDs, a descrição e os três papéis (coordenador, executor, auditor). Se o pedido já escolher explicitamente um ID de perfil, considere-o a resposta para essa atividade.
2. Não defina uma escolha global compartilhada. Registre o perfil selecionado, o modelo real da sessão coordenadora, o limite aplicado e a data na frente daquela atividade. Frentes simultâneas podem usar perfis diferentes sem disputar um campo ativo.
3. Confirme que o provedor do coordenador do perfil corresponde ao cliente da sessão atual. Quando o modelo do coordenador não for `sessao`, confirme também que a sessão está nesse modelo; se não corresponder, pare antes de delegar e peça que o usuário troque de perfil/sessão ou escolha outro perfil. `modelo: sessao` significa manter o modelo ativo e registrá-lo na frente.
4. Perfis `nativo` usam as ferramentas de subagentes do cliente atual. Perfis `cli` usam `.claude/skills/orquestrar/scripts/invocar_agentes.py` para iniciar processos headless de Claude Code ou Codex, conforme o papel. Os CLIs precisam estar instalados e autenticados. Passe um lote JSON com IDs, prompts delimitados e escopos de arquivos; o runner lê o perfil escolhido, aplica `orquestracao.limite_executores` de `.init-harness/config.json`, limita chamadas externas por atividade e não persiste as sessões dos CLIs, não carrega conexões MCP nem grava conteúdo no ledger. Guarde o lote temporário em `.init-harness/state/orquestracao/` e passe `--remover-lote`, para apagar o arquivo após a leitura.
5. O runner só aceita os papéis `executor` e `auditor`. Use o modo de escrita limitado para executores e o modo somente de leitura para auditores. Faça a auditoria depois que todos os executores encerrarem e o diff estiver estável.

## Fluxo obrigatório

1. Leia o pedido, as instruções do projeto, a spec aplicável, `.init-harness/config.json`, `.init-harness/orquestracao.json` e o estado do Git. Registre mentalmente `HEAD`, branch e arquivos já alterados para preservar trabalho anterior à sessão.
2. Identifique o objetivo, os critérios de aceite, riscos, dependências e validações necessárias. Use o grafo e buscas determinísticas para localizar as áreas antes de delegar; não passe exploração aberta como tarefa de implementação.
3. Divida uma solicitação com múltiplas tarefas em itens identificados e mantenha uma tabela de estado: `pendente`, `pronta`, `em andamento`, `bloqueada`, `concluída` e `auditada`. Para cada item, registre objetivo, contexto suficiente, critérios de aceite, dependências, arquivos permitidos, dono, validação e formato de retorno.
4. Use o menor número de executores que permita paralelismo seguro, limitado por `orquestracao.limite_executores` em `.init-harness/config.json` e pelos limites do cliente. Inicie todas as tarefas `prontas` e independentes até preencher as vagas; quando um executor terminar, atribua a próxima tarefa pronta sem aguardar os outros. Tarefas dependentes só começam após suas dependências. Um executor pode cuidar de um grupo coeso de tarefas ou arquivos; não crie um agente por arquivo.
5. Atribua um dono exclusivo para cada arquivo editável durante cada etapa. Não permita edição simultânea do mesmo arquivo. Se tarefas diferentes precisarem do mesmo arquivo, sequencie essas tarefas ou una-as sob um executor.
6. Preserve arquivos que já estavam modificados antes do trabalho. Não os atribua a executores sem autorização explícita e sem uma forma clara de separar o diff preexistente.
7. Delegue a implementação conforme o perfil escolhido: subagentes nativos quando o modo é `nativo`, ou processos CLI via runner quando é `cli`. Não finja que houve delegação. Se o recurso configurado estiver indisponível, informe o bloqueio e pare antes de implementar em modo de agente único.
8. Aguarde todos os executores e recolha seus relatórios. Confirme o estado de cada tarefa e compare a lista de arquivos relatada com `git status --short`, `git diff` e `git diff --staged`. Abra diretamente todo arquivo untracked listado pelo status, pois ele não aparece no diff comum. Arquivo fora do escopo exige nova atribuição; não o aceite silenciosamente.
9. Só coordene a integração depois que as escritas terminarem. Em worktree compartilhada, confirme que os escopos não se sobrepõem e compare o diff agregado. Em worktrees isoladas ou diante de conflito, delegue a integração a um executor com a base, os arquivos e os critérios registrados; não faça a implementação da integração diretamente.
10. Antes da auditoria, atualize os registros operacionais que pertencem ao coordenador, incluindo checkpoints e a tabela `Tarefas delegadas` em `docs/ai/frentes/<slug>.md`. Registre estado e resumo de cada executor concluído. Esses registros fazem parte do diff da atividade e entram na revisão.
11. Quando o conjunto final estiver estável, delegue a revisão de todo o diff a um auditor separado, somente leitura. O auditor não pode ser um dos executores daquela alteração.
12. Se o auditor reprovar, delegue os ajustes ao executor adequado, aguarde a nova conclusão e peça uma nova auditoria do diff completo. O coordenador não encerra a tarefa com achados bloqueantes pendentes.
13. Depois da aprovação, não altere arquivos. Se uma validação ou etapa final exigir mudança, delegue a edição a um executor e faça nova auditoria. Ao concluir, relate arquivos, verificações, decisão do auditor e limitações.

## Controles para evitar problemas de integração

- O escopo de arquivos é exclusivo por fase; manter tarefas diferentes não significa permitir escrita concorrente nos mesmos arquivos.
- Várias tarefas executoras dentro de uma atividade usam uma única frente e um único quadro de tarefas. Não crie uma frente por subagente. Frentes de produto distintas continuam isoladas em branches e worktrees diferentes, conforme as regras da seção 4 do harness.
- Cada executor deve parar e pedir redistribuição quando descobrir um arquivo necessário que não esteja autorizado.
- O coordenador compara `git status --short`, `git diff` e `git diff --staged` com a fotografia inicial e com o mapa de donos. Abre diretamente os arquivos untracked. Mudanças preexistentes ficam fora da auditoria desta tarefa, salvo se o usuário as incluir expressamente.
- Integrações em worktrees são aplicadas em sequência sobre a mesma base registrada. Se houver conflito textual ou semântico, reabra uma subtarefa de integração com arquivos e critérios explícitos; não aceite a junção automática como prova de correção.
- Nenhum executor ou auditor faz commit, push, merge de branch, release, deploy ou ação destrutiva. Permanecem válidas as autorizações e gates existentes no harness.

## Seleção de modelos e custo

- `.init-harness/orquestracao.json` é a fonte por projeto para os perfis. Ajuste `coordenador`, `executor` e `auditor` nos perfis existentes ou acrescente um perfil; cada papel declara `provedor`, `modelo` e `modo` (`sessao`, `nativo` ou `cli`).
- Em perfis nativos do Codex, mantenha `modelo` alinhado com o campo `model` do agente correspondente em `.codex/agents/*.toml`. Para aplicar um modelo escolhido somente em `.init-harness/orquestracao.json`, configure esse papel com `modo: cli`.
- A sessão atual precisa usar o provedor/modelo declarados para o coordenador. Perfis iniciais: `claude_opus_codex_luna` (Opus coordena e audita; Codex GPT-6 Luna executa), `codex_luna_claude_opus` (Codex GPT-6 Luna coordena/executa; Claude Opus audita), e opções nativas para cada cliente.
- `orquestracao.limite_executores` em `.init-harness/config.json` é a fonte do limite simultâneo do runner CLI; o limite nativo também fica no cliente: `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` em `.claude/settings.json` e `agents.max_concurrent_threads_per_session` em `.codex/config.toml`. Mantenha-os alinhados. O runner bloqueia novas chamadas externas quando `limite_chamadas_cli_por_atividade` em `.init-harness/orquestracao.json` é atingido para aquele ID de frente.
- Execute uma única auditoria do diff agregado depois dos executores; reaudite apenas após correções. Forneça aos agentes só o contexto e os arquivos necessários. Não abra executor para análise pequena ou sequencial que o coordenador consiga concluir com menos chamadas e sem implementação.
- Agentes fazem chamadas adicionais e podem elevar consumo ou custo. Limitar concorrência reduz o pico, mas não garante uma conta final igual ou menor. O teto financeiro disponível depende da conta e do cliente. Não prometa um orçamento monetário se a plataforma não oferecer um controle efetivo para a sessão.
- Chamadas CLI cruzadas exigem o executável do provedor no `PATH`, autenticação já configurada e uso da cota/conta desse provedor. O runner limita o número simultâneo e as chamadas externas por atividade; não define um teto monetário nem garante custo final. Modos nativos continuam disponíveis para evitar processos CLI externos.

## Papéis

### Coordenador — agente principal

- Decompõe o pedido, define a ordem e os limites de concorrência.
- Mantém a tabela de tarefas, dependências e donos dos arquivos.
- Não escreve código nem implementa subtarefas. Se uma integração exigir edição, delega-a a um executor.
- Aguarda os executores, coordena a integração e verifica a correspondência entre relatórios e diffs.
- Chama o auditor após estabilizar o diff e trata a aprovação como gate obrigatório.
- Não rebaixa um achado bloqueante nem apresenta aprovação parcial como aprovação final.

### Executor — subagente com escrita limitada

- Implementa uma subtarefa e só edita os arquivos atribuídos.
- Não amplia escopo, não delega e não altera a documentação operacional `docs/ai/`.
- Devolve resultado, arquivos alterados, verificações, riscos e bloqueios.

### Auditor — subagente independente, somente leitura

- Inspeciona os arquivos realmente alterados depois do encerramento dos executores.
- Compara o diff completo com o pedido, a spec, os critérios, os limites de arquivos e os resultados de validação.
- Responde `APROVADA` ou `REPROVADA`, com evidências `arquivo:linha` e lacunas.
- Não corrige arquivos nem define escopo novo.

## Formato de delegação

```text
Tarefa: <id e título>
Objetivo: <resultado esperado>
Contexto: <arquivos, símbolos, decisões e evidências relevantes>
Critérios de aceite: <condições verificáveis>
Dependências: <tarefas que devem terminar antes>
Arquivos autorizados: <lista explícita>
Fora do escopo: <limites explícitos>
Validação: <comandos permitidos e resultados esperados>
Retorno: conclusão, resumo, arquivos alterados, validação, riscos e bloqueios
```

Para executar um lote por CLI, o JSON tem esta forma (um lote por papel):

```json
{
  "frente_id": "2026-09-pesquisa",
  "perfil": "claude_opus_codex_luna",
  "papel": "executor",
  "tarefas": [
    {"id": "T1", "prompt": "Objetivo, critérios de aceite e arquivos exclusivos desta tarefa."},
    {"id": "T2", "prompt": "Outra tarefa independente com arquivos exclusivos."}
  ]
}
```

Invoque `python .claude/skills/orquestrar/scripts/invocar_agentes.py --lote <caminho-do-lote> --remover-lote` a partir da raiz. O runner limita a concorrência, aplica sandbox de escrita aos executores e sandbox de leitura ao auditor, reserva chamadas no ledger SQLite local e devolve um resultado por ID. O arquivo de lote precisa estar em `.init-harness/state/orquestracao/` quando `--remover-lote` for usado.

## Adaptadores de cliente

- **Claude Code:** para modo nativo use `executor` e `revisor` em `.claude/agents/`; para modo CLI use o runner com `claude -p`/`codex exec` conforme o perfil.
- **Codex:** para modo nativo use `harness_executor` e `harness_auditor` em `.codex/agents/`; para modo CLI use o mesmo runner. O auditor sempre permanece somente leitura.
- Use ferramentas reais do cliente e confirme modelo/provedor antes da chamada. O runner recebe tarefas em lote, respeita o limite do projeto e devolve resultado por ID para integrar ao quadro da frente.

## Uso de recursos

Subagentes usam chamadas de modelo e ferramentas adicionais. Evite criar agentes sem uma subtarefa própria. Respeite a quantidade pedida pelo usuário e os limites do cliente; sem quantidade explícita, use `orquestracao.limite_executores` e não preencha vagas sem trabalho independente.
