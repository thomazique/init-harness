# Política de segurança

## Reportar uma vulnerabilidade

Não abra issue pública para vulnerabilidades, segredos expostos ou formas de
contornar os guardrails. Abra uma [GitHub Private Security Advisory](https://github.com/thomazique/init-harness/security/advisories/new).

Inclua reprodução, versões afetadas e impacto. Relatos de boa-fé serão tratados
de modo privado; não há SLA ou programa de recompensa.

## Modelo de ameaça

O init-harness é um kit local para repositórios Git. Ele não é um serviço
hospedado e não fornece autenticação, isolamento entre usuários ou proteção de
rede.

Em escopo: evitar captura automática de prompts, comandos ou tool calls;
rejeitar padrões fortes de segredo em handoffs e notas; manter Markdown como
fonte de verdade e SQLite como índice reconstruível; e tratar memória
recuperada como histórico não confiável, nunca como instrução executável.

Fora de escopo: agente ou máquina já comprometidos; criptografia em repouso;
isolamento de segredos; segurança de Git, MCP, Graphify ou provedores externos;
prevenção perfeita de prompt injection; e substituição de revisão humana,
sandbox, CI ou proteção de branch.

## Uso seguro

Não registre segredos em docs, specs, handoffs, issues ou logs. Revise
permissões de hooks, clientes MCP e integrações externas; confirme decisões de
segurança contra o checkout e instruções atuais.

## Versões suportadas

Correções de segurança são aplicadas somente à versão mais recente publicada.
