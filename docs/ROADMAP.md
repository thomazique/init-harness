# Roadmap

O roadmap registra intenção, não compromisso de prazo.

## Atual

- Memória canônica, FTS, handoffs, recuperação híbrida e painel operacional.
- Grafo de trabalho, impacto Graphify, política de frescor e bootstrap revisável.
- Ciclo de evolução de skills: ativação automática, sugestões vivas, fila com recuperação,
  proposta aberta pela aprovação humana, skill `evolve` e runners de referência.

## Futuro — validar antes de construir

### Avaliação em projetos reais

Usar o harness em projetos distintos e registrar qualidade de recuperação,
falsos positivos, tempo de operação e utilidade de sugestões. Embeddings,
reranking ou automação dependem dessa evidência.

### Avaliação comportamental de skills

O `static_eval` só confere o texto da skill (instrução exigida presente, guardrails
preservados). Um runner que execute a skill e meça o resultado depende de casos reais para
definir o que é sucesso; validar com projetos antes de padronizar um formato.

### Volume de experiências por sessão

Cada sessão que usa uma skill gera uma experiência e um job, inclusive as bem-sucedidas, que
o worker encerra como `no_action`. Decidir com uso real se `.init-harness/skills/queue/` deve
ser versionado, ignorado ou podado, e se sessões sem falha precisam virar job.

### Sincronização para equipes e múltiplas máquinas

Investigar compartilhamento controlado de Markdown canônico, conflitos,
permissões e privacidade. SQLite local e artefatos derivados não serão fonte de
verdade distribuída sem desenho explícito.

## Não planejado por padrão

- telemetria;
- envio automático de repositórios ou memória a provedores externos;
- criação automática de frentes, decisões ou relações a partir de sugestões.
