---
name: orquestrar
description: Use em solicitações de implementação ou alteração de software que envolvam coordenação de agentes, planejamento de frentes, execução paralela ou auditoria independente.
---

# Orquestração hierárquica

O protocolo organiza o trabalho em três níveis: **chefe > supervisores > construtores**. O chefe coordena a iniciativa inteira; cada supervisor planeja e acompanha sua frente; construtores implementam tarefas delimitadas. Supervisores são somente leitura: planejam, consultam e auditam. Construtores escrevem apenas nos arquivos atribuídos e reportam as verificações que de fato realizaram. O chefe faz a auditoria final fora do runner e não roda testes como parte dessa auditoria.

## Configuração e compatibilidade

Escolha o perfil antes de planejar a iniciativa. A separação padrão é deliberada: o chefe usa o modelo de maior capacidade; o supervisor, um modelo intermediário; e os construtores, um modelo mais eficiente. Para Claude + OpenAI, o perfil recomendado é Claude Opus (`opus`) no chefe, Claude Sonnet (`sonnet`) nos supervisores e GPT-5.6 Luna nos construtores. Há também perfis exclusivos de cada provedor. Os aliases `opus`, `sonnet` e `haiku` selecionam as versões disponibilizadas pelo Claude Code; modelos e esforço de raciocínio podem ser ajustados localmente.

O campo `chefe` documenta o modelo esperado para a sessão principal. O runner não troca o modelo dessa sessão: antes de prosseguir, confirme que a sessão atual corresponde ao chefe do perfil escolhido. Se não corresponder ou não for possível confirmar, ajuste o perfil ou esclareça a escolha com o humano. O runner usa `supervisor` e `construtor` para despachar as chamadas CLI.

Leia `.init-harness/orquestracao.json`, `.init-harness/config.json`, as instruções aplicáveis, as specs das frentes e o estado do Git. A configuração de perfis mantém os campos legados `coordenador`, `executor` e `auditor`; os papéis `chefe`, `supervisor` e `construtor` são opcionais. Na ausência deles, use respectivamente coordenador, auditor e executor. A escolha de perfil vale para a iniciativa corrente e não deve ser gravada como estado global compartilhado.

## Apoio opcional do Jev

Quando `.init-harness/config.json` declara `jev.enabled: true`, use Jev como classificador auxiliar em pontos de decisão, nunca como agente conversacional:

1. Depois de entender o pedido, o chefe prepara uma síntese curta em JSON com objetivo, restrições e resultado esperado — sem copiar a conversa inteira, segredos ou conteúdo irrelevante. Salva temporariamente em `.init-harness/state/jev-input.json`, chama `python .claude/hooks/memory.py jev-route --state-file .init-harness/state/jev-input.json` e remove o arquivo temporário. A saída tipada sugere intenção (`research`, `plan`, `implement_single`, `implement_parallel`, `review`, `maintenance`), especialidade predominante, risco e probabilidade de ambiguidade.
2. O chefe compara esses rótulos com o pedido original, instruções, specs e evidências locais. Ele escolhe perfil, abre ou não frentes, define supervisores e escreve o manifesto. Jev não cria subtarefas, não despacha agentes e não envia instruções diretamente a supervisores ou construtores.
3. Após planejamento/reconciliação ou auditoria de uma fase, o chefe pode resumir relatórios e evidências em JSON e chamar `python .claude/hooks/memory.py jev-gate --phase <fase> --state-file <arquivo>`; `<fase>` aceita `planejamento`, `reconciliacao`, `execucao` ou `auditoria`. O rótulo `continue`, `targeted_review` ou `ask_human` é uma recomendação para o chefe validar. A auditoria final continua sendo do chefe e perguntas humanas continuam subindo ao humano.

Use chamadas apenas quando uma decisão puder mudar o plano ou o próximo passo; não chame Jev para cada mensagem ou atualização rotineira. Se Jev estiver desativado, sem chave, inconclusivo ou indisponível, siga exatamente o fluxo normal de raciocínio e FTS5. A síntese e os relatórios enviados ao classificador são dados do projeto enviados ao serviço externo; o opt-in deve ser explícito. Não envie segredos. A busca de contexto, quando Jev está habilitado, usa FTS5 para selecionar trechos e Jev para pontuá-los antes de devolvê-los ao chefe.

Interprete `needs_clarification_probability >= 0.60` como sinal para conferir a ambiguidade no pedido original; `risk_score >= 4` exige aplicar as regras de segurança/autonomia do projeto. `confidence < 0.60` ou `status` diferente de `Jev` invalida o resultado para roteamento e mantém o julgamento normal do chefe. `implement_parallel` e `specialty: mixed` apenas sugerem decomposição: confirme que as frentes são independentes, atribua arquivos e reconcilie interfaces antes de despachar. O classificador não seleciona modelos; use os perfis configurados em `.init-harness/orquestracao.json`.

Uma iniciativa hierárquica usa o contrato versão 1, descrito como `$defs.manifesto_iniciativa` em `.init-harness/schema/orquestracao.schema.json`:

```json
{
  "contract_version": 1,
  "initiative_id": "exemplo-2026-09",
  "profile": "perfil-existente",
  "limits": {
    "max_parallel": 3,
    "max_agents": 8,
    "max_calls": 20,
    "max_builders_per_supervisor": 3
  },
  "fronts": [
    {
      "id": "api",
      "team": "time-api",
      "specialty": "backend",
      "spec": "specs/api.md",
      "repository": "repositorio-api",
      "branch": "feat/api",
      "base_commit": "<commit-base>",
      "dependencies": [],
      "scope": ["src/api/", "tests/api/"]
    }
  ]
}
```

Os limites são globais à iniciativa: `max_parallel` limita agentes simultâneos, `max_agents` limita agentes alocados, `max_calls` limita chamadas planejadas e `max_builders_per_supervisor` limita construtores por supervisor. Respeite também limites menores do cliente e do perfil. Não interprete esses valores como limite financeiro nem como capacidade implementada pelo runner.

O formato antigo de lote com `frente_id`, `perfil`, `papel` (`executor` ou `auditor`) e `tarefas[].prompt` continua compatível com `--lote`. Use-o para os papéis legados suportados; não envie papéis hierárquicos novos ao runner como se ele os aceitasse. Para esses papéis, siga as instruções e os recursos de agentes disponíveis no cliente.

## Fases da iniciativa

1. **Preparação pelo chefe.** Registre `HEAD`, branch e `git status`; não atribua arquivos que já estavam alterados sem autorização explícita. Leia as specs de todas as frentes, identifique dependências e faça uma manifestação com `initiative_id`, `profile`, limites globais e os campos exigidos em cada frente. Persista o estado operacional em `.init-harness/state/orquestracao/<initiative_id>/`. Registre estado, identificadores, planos e resumos; prompts e respostas completas dos agentes não são gravados. Respostas humanas de checkpoint são preservadas no estado local para permitir retomada.
2. **Planejamento pelos supervisores.** Envie a cada supervisor somente a spec e o escopo de sua frente. Supervisor não edita: consulta, planeja e depois audita a própria spec. Cada um retorna JSON estrito com esta forma:

   ```json
   {"tasks":[{"id":"T1","objective":"...","files":["..."],"depends_on":[],"acceptance":["..."],"pair_with":["T2"]}],"interfaces":[],"questions":[]}
   ```

   `pair_with` é opcional e lista pares recíprocos dentro da mesma frente. Os planos devem atribuir dono claro aos arquivos e explicitar dependências e critérios verificáveis. Se houver pergunta humana sem resposta, pause a iniciativa.

3. **Reconciliação entre supervisores.** Antes de iniciar qualquer construtor, compartilhe com cada supervisor os planos de todas as frentes. Cada supervisor retorna JSON estrito `{ "agreements": [], "conflicts": [], "questions": [] }`. Considere as especialidades ao identificar conflitos de contratos e implantação. Qualquer conflito bloqueia o despacho até ser resolvido.
4. **Execução pelos construtores.** Cada tarefa executa em um worktree Git temporário próprio. O runner rejeita alterações fora dos arquivos atribuídos, confere que o repositório principal não mudou durante a construção e integra em sequência somente os arquivos autorizados. Despache apenas tarefas sem dependências pendentes e dentro dos limites globais; perguntas e bloqueios sobem ao supervisor/chefe.
5. **Auditoria das frentes.** Após a escrita, cada supervisor especialista audita sua spec e o diff em modo somente leitura; não roda testes.
6. **Auditoria final do chefe.** Com as frentes aprovadas, o chefe confere o diff agregado, manifesto, specs, reconciliação e auditorias, sem rodar testes. Ele pode concluir com `approve`, pedir esclarecimento humano com `ask_human` ou apontar tarefas específicas com `revise`. Revisões limpam resultados afetados e suas dependências para nova execução e auditoria.

## Git, estado e validação

Git é a fonte de verdade para alterações efetivas, branches e commits-base; os registros em `.init-harness/state/orquestracao/<initiative_id>/` guardam o andamento operacional local. O runner valida branch e commit-base, cria um worktree descartável por construtor e integra apenas seus arquivos atribuídos. Prepare branches/repositórios para cada frente e confira `git status` antes de iniciar para preservar trabalho preexistente.

O construtor executa as verificações definidas pelo pedido, pela spec e pelas instruções do projeto, e reporta comando e resultado sem alegar execuções que não ocorreram. Supervisor e chefe auditam por leitura e comparação; o chefe não roda testes na auditoria final. Pergunta humana pendente, conflito de arquivo, dependência não concluída ou limite excedido impede avanço da etapa correspondente.

Diálogo moderado: questões humanas podem ser retomadas com `--respostas`; decisões finais usam `--decisao-chefe` conforme `decisao_chefe` no schema.

## Especialidades de supervisor

Cada frente declara `specialty`: `frontend`, `backend`, `security`, `deploy_cicd` ou `database`. O chefe escolhe a especialidade pelo trabalho predominante; trabalhos multidisciplinares podem usar frentes distintas com interfaces reconciliadas. Os presets estão em `templates/supervisores/`. Frontend referencia a skill local existente. No fechamento, o supervisor entrega um `builder_context` específico por tarefa. O construtor recebe sua tarefa, critérios, esse contexto, instruções do projeto, dependências concluídas e consultas dos pares.

## Perfis e limites

Perfis existentes permanecem válidos. Se os papéis novos estiverem ausentes, aplique o fallback documentado acima; não reescreva os perfis para iniciar uma iniciativa. O executor legado corresponde ao construtor e o auditor legado pode fornecer a configuração de modelo do supervisor. A hierarquia atual do runner exige perfis CLI; modos nativos continuam disponíveis no fluxo conversacional do cliente, mas ainda não são despachados pelo manifesto. Modelos, chamadas CLI e concorrência dependem do que o cliente e as ferramentas realmente oferecem. `--lote` mantém o formato antigo e não implica suporte do runner a manifesto, supervisores, reconciliação ou estado hierárquico.
