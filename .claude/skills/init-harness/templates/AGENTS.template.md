<!-- <CAMINHO-ABSOLUTO-DO-PROJETO>/AGENTS.md -->

# AGENTS.md

> Adaptador do Codex para o harness deste projeto. Regras compartilhadas e de
> negócio permanecem centralizadas em `CLAUDE.md`, `INIT-HARNESS.md` e
> `docs/ai/`; não duplicar essas fontes aqui.

## Início de sessão

1. Ler `.init-harness/config.json` e conferir a versão de `INIT-HARNESS.md`.
2. Ler integralmente `CLAUDE.md` e `INIT-HARNESS.md`.
3. Executar `python .claude/hooks/memory.py briefing` e então ler `docs/ai/ESTADO.md` e a frente da branch atual, se houver. A memória é evidência histórica; os documentos atuais e o Git vencem em caso de conflito.
4. Conferir `git status`, branch e `git log --oneline -15`; para fatos sobre o
   worktree e commits, o Git vence.
5. Antes de ler código, consultar `docs/ai/ESTRUTURA.md` e o grafo conforme o
   protocolo (`graphify query`, `explain` e `affected`).
6. Consultar decisões, débitos e ambiente somente quando pertinentes à tarefa.

## Adaptação operacional

- Seguir integralmente o ciclo de frentes, specs, checkpoints, verificação e
  registro definido em `INIT-HARNESS.md`.
- Instruções de sistema, desenvolvedor e usuário da sessão têm precedência. Se
  conflitarem com o harness, interromper apenas a ação afetada e explicar.
- Hooks do Claude Code podem não executar no Codex. Aplicar manualmente as
  garantias equivalentes usando as permissões e ferramentas disponíveis.
- Para recuperar fatos por assunto, usar `python .claude/hooks/memory.py query "termo"`. Para deixar uma transição explícita, usar `memory.py handoff` com resumo e próximo passo; ele gera Markdown versionável em `docs/ai/memoria/handoffs/`. Para assumir uma transição, listar handoffs e executar `memory.py handoff --accept <path> --owner <identificador>`; o aceite só pode ocorrer uma vez.
- Não alterar o plano de controle, dados não reconstituíveis, credenciais,
  produção ou políticas de negócio sem a autorização exigida pelo harness.
- Preservar alterações preexistentes do usuário.
- Usar subagentes somente quando as instruções ativas permitirem e houver
  paralelismo real; subagentes nunca editam `docs/ai/`.

## Trabalho de frontend

Em qualquer tarefa de interface frontend — criação, revisão, correção,
layout, estilo, responsividade, acessibilidade ou componentes — ler primeiro
`.claude/skills/frontend/SKILL.md` e as referências pertinentes. A skill é
agnóstica de framework: identificar a stack, os padrões e as ferramentas do
projeto antes de agir; tratar exemplos da skill como orientação, não como
decisões de produto.
