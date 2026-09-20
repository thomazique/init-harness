---
name: evolve
description: Escreve a candidata de uma proposta de evolução de skill a partir da evidência registrada, valida e leva até a avaliação. Use quando existir uma sugestão em suggestions.jsonl ou uma proposta em draft para uma skill, quando o usuário pedir para corrigir ou melhorar uma skill com base em falhas recorrentes, ou depois de /record revelar um padrão. Nunca promove a skill: a aceitação é do humano.
---
# evolve

Fecha o meio do ciclo de evolução: transforma a evidência de uma sugestão em uma candidata de `SKILL.md` avaliável. Não altera a skill ativa.

Comandos: `python .claude/hooks/skill_evolution.py <comando>`.

---

## Limites

- Escrever somente em `candidate_path` (a `SKILL.md` candidata da proposta) e em `.init-harness/skills/<skill>/eval/cases/`. Nunca em `.claude/skills/<skill>/SKILL.md`.
- Nunca inventar score, resultado de avaliação ou caso que "passou". A nota vem do runner do projeto ou do humano.
- Nunca rodar `accept` por conta própria. O usuário decide depois de ver o resultado.
- Mudança mínima: só o que a evidência sustenta. Não reescrever a skill, não ampliar o escopo, não enfraquecer regra de segurança, confirmação ou guardrail existente.

---

## Procedimento

1. **Escolher.** `suggestions <skill>`: uma com `status: proposed` (`in_progress` já tem proposta; `addressed` já foi promovida). Sem sugestão aberta, não há evidência para evoluir: parar. Um job aprovado com `review-job` já abriu a proposta (`proposals <skill>`); sem proposta ainda: `propose <skill> --suggestion <S-ID> --owner <quem pediu>`.
2. **Ler.** `proposal-context <skill> --proposal <P-ID>` devolve evidência, política e contrato. Ler também a `SKILL.md` em `base_path`.
   - `active_matches_base: false`: a skill ativa mudou. Recriar a proposta.
   - `usage_contract_ready: false`: o contrato de uso é do humano. Propor um a partir da description e da evidência, pedir confirmação e só então `configure-usage`. Não seguir sem ele.
3. **Diagnosticar.** Para cada evidência: que instrução da skill faltou, foi ambígua ou foi seguida e deu errado? Parar e dizer ao usuário, sem editar, quando:
   - `explained_evidence` é 0. Falha automática (`source: system`) só diz que houve falha, não o motivo. Pedir `/record` com o fato observado.
   - a causa é ambiente, ferramenta ou permissão, não uma instrução da skill.
4. **Caso de regressão.** `init-evaluation <skill>` se `case_files` estiver vazio. Criar `eval/cases/<case_id>.json` que reproduz o cenário da evidência (`task`, `input`, `expected`), sem dados reais nem segredos. Para o runner de referência, `expected` traz `must_mention` (a instrução que a candidata deve ter), `must_not_mention` e `guardrails` (trechos da base que não podem sumir). Depois `validate-cases <skill>`.
5. **Escrever a candidata.** Editar `candidate_path`. O frontmatter continua na linha 1 com `name` igual ao da skill; `description` só muda se a evidência for de disparo errado.
6. **Registrar.** `submit-candidate <skill> --proposal <P-ID> --summary "<o que mudou e por quê, ligado à evidência>"`. Erro de validação: corrigir a candidata e repetir.
7. **Avaliar.** `run-evaluation <skill> --proposal <P-ID> --runner .claude/skills/evolve/runners/static_eval.py` (ou o runner do projeto). O `static_eval` só verifica o texto da skill: ao reportar, dizer que a avaliação é estrutural e não mede comportamento. Sem casos com asserções: parar e reportar "candidata pronta, avaliação pendente". `evaluate` com números só quando o humano os fornecer.
8. **Entregar.** Reportar a sugestão de origem, o que mudou, o resultado da avaliação e o comando `accept` para o usuário decidir. Resultado `rejected`: revisar a candidata (passo 5) e repetir a partir do 6, ou parar e reportar.

---

## Skill de método

Skills com `scope: method` (`inspect <skill>`) vêm do kit. Promover uma mudança local faz o próximo `upgrade` tratá-la como edição local: preserva a versão do projeto e entrega a do kit em `.init-harness/updates/*.new`. Avisar o usuário e sugerir levar a melhoria ao kit.
