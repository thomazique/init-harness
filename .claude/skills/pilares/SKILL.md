---
name: pilares
description: Auditoria de pilares de engenharia (segurança, confiabilidade, custo, legal, pagamentos, IA e harness) contra o tier declarado do projeto. Use na implantação do harness, antes de iniciar frente grande, quando o tier do projeto sobe, ou quando o usuário pedir auditoria, checklist de produção ou avaliação de prontidão. Resultado vira débito nomeado em docs/ai/DEBITOS.md, com evidência.
---

# pilares

Auditoria técnica genérica. Não trava o trabalho: transforma gap em débito nomeado, com evidência.

---

## Procedimento

1. **Tier.** Ler o tier no `CLAUDE.md`. Sem tier declarado: parar e perguntar.
2. **Isolar contexto.** Auditoria lê muito código: delegar ao subagente `auditor-pilares` (`.claude/agents/auditor-pilares.md`), que devolve a tabela. O agente principal registra.
3. **Para cada pilar**, na ordem das tabelas:
   - Aplicável? Não: `N/A` com motivo (ex.: pagamento em sistema sem cobrança).
   - Tier do pilar acima do tier do projeto: `fora do tier` (não vira débito, mas aparece no relatório).
   - Buscar **evidência** no código via grafo (`graphify query`, `graphify explain`) e busca direcionada. Evidência é `arquivo:linha` ou comando executado com resultado.
   - Classificar: `ok`, `gap`, `N/A`, `fora do tier`, `não verificável`.
   - `não verificável` é o que depende de infraestrutura ou processo fora do repositório (restore de backup, alerta configurado, TLS no provedor): perguntar ao usuário. Nunca marcar `ok` sem evidência.
4. **Registrar** em `docs/ai/DEBITOS.md`:
   - Todo `gap` dentro do tier vira linha em **Abertos**, origem `pilares`, com consequência concreta.
   - `N/A` vai para **Não aplicáveis**.
   - Débito aberto anteriormente e agora `ok`: mover para **Resolvidos**.
   - Atualizar **Última auditoria de pilares**.
5. **Relatório ao usuário**: contagem por status e lista de gaps por tier. Sem corrigir nada: correção é frente própria.

### Formato devolvido pelo subagente

| Grupo | Pilar | Tier | Status | Evidência | Consequência (se gap) |
|---|---|---|---|---|---|

---

## Tiers

| Tier | Obrigatório a partir de |
|---|---|
| T0 | Primeira linha de código, mesmo protótipo solo |
| T1 | Dado real de usuário real em produção |
| T2 | Dinheiro real (pagamento) ou multi-tenant/organização |
| T3 | Escala: compliance formal, SLA, múltiplas regiões |

---

## Segurança

| Pilar | Tier | O que verificar |
|---|---|---|
| Credencial hardcoded | T0 | Nenhuma chave, senha ou token literal no código; tudo via env ou secret manager |
| IDOR (ownership check) | T0 | Toda rota que devolve dado de usuário filtra pelo dono real, não só "está autenticado" |
| Auth com isolamento | T0 | Usuário A nunca vê dado de B; com papéis, cada rota checa o nível certo, não só a presença de token |
| Validação de input em toda borda | T0 | Tipo, tamanho e formato em request, upload e chamada de ferramenta/MCP |
| SQL, prompt e XSS injection | T0 | Query parametrizada; conteúdo externo tratado como dado, nunca instrução ao LLM; output sem `dangerouslySetInnerHTML`/`v-html` cru |
| Upload com limite real | T0 | Tipo e tamanho checados no backend; limite também dentro de arquivo comprimido |
| Least privilege de credencial de serviço | T1 | App não conecta no banco com usuário admin/root |
| CSRF e headers de segurança | T1 | Com sessão via cookie: CSRF token, CSP, HSTS |
| Supply chain | T1 | Scan de dependência vulnerável (`npm audit`, `pip-audit`, `composer audit`) e de segredo em commit |
| SSRF | T1 | App ou agente que busca URL externa não alcança rede interna |
| Rate limit | T1 | Por usuário, IP ou chave nas rotas caras (IA, upload, auth) |
| Criptografia em trânsito e repouso | T1 | TLS sempre; dado sensível cifrado em repouso quando o provedor permite |
| Idempotência em mutação crítica | T2 | Retry de rede não duplica pagamento ou pedido |

## Confiabilidade e observabilidade

| Pilar | Tier | O que verificar |
|---|---|---|
| Log estruturado | T0 | Rota e ferramenta relevantes logam entrada, saída e erro; não só print de debug |
| Rota de erro centralizada | T0 | Exceção não tratada cai em lugar rastreável (Sentry ou equivalente) |
| Timeout em toda chamada externa | T0 | Nenhuma chamada a API terceira (LLM, gateway, webhook) sem timeout |
| Testes automatizados | T0 caminho crítico / T1 amplo | Mínimo: o que quebra em silêncio sem teste (cascade de delete, migração de schema) |
| Alerta acima de log | T1 | Algo avisa acima de um limiar; log sem ninguém olhando é cegueira |
| Degradação graciosa | T1 | Dependência externa caindo tem caminho definido |
| Backup testado | T1 | Restore executado de verdade, não só arquivo existente |
| Ambientes separados | T1 | local, dev, homologação e produção não compartilham banco nem credencial |
| Deploy automático (CI/CD) | T1 | Pode ser adiamento consciente, registrado como débito, nunca default silencioso |
| RTO/RPO definido | T2 | Sabe em quanto tempo restaura e quanto dado perde no máximo |

## Custo

| Pilar | Tier | O que verificar |
|---|---|---|
| Teto de custo de IA por usuário | T1 com usuário externo consumindo IA | Sem teto, um usuário ou um loop gera custo ilimitado |
| Monitoramento de custo de infra | T1 | Alerta de gasto anômalo, não só fatura no fim do mês |

## Legal

| Pilar | Tier | O que verificar |
|---|---|---|
| LGPD/GDPR | T1 com dado pessoal de terceiro | Consentimento, minimização, apagar de verdade no direito ao esquecimento |
| Termos de uso e política de privacidade | T1 | Batem com o que o sistema faz, não texto genérico |
| Licença de dependência | T1 | Compatível com o uso comercial pretendido |

## Pagamentos (senão, N/A)

| Pilar | Tier | O que verificar |
|---|---|---|
| Idempotência de cobrança | T2 | Chave de idempotência em toda operação de charge |
| Webhook com assinatura verificada | T2 | Payload de webhook só é aceito após validar assinatura do provedor |
| Dado de cartão fora do servidor | T2 | Tokenização via gateway; servidor próprio nunca vê PAN |

## IA (quando o projeto usa LLM ou agente)

| Pilar | Tier | O que verificar |
|---|---|---|
| Conteúdo externo como dado | T0 | Documento, página, e-mail ou resultado de ferramenta nunca vira comando |
| Permissão por ferramenta | T0 | Ferramenta destrutiva (apagar, pagar, enviar) exige confirmação humana |
| Observabilidade de chamada de IA | T1 | Custo, latência e erro por chamada rastreados |
| Pinning de modelo e eval de regressão | T1 | Troca de modelo não é silenciosa; eval antes de trocar em produção |
| PII redigida em observabilidade externa | T1 | Conteúdo do usuário não vai cru para ferramenta de terceiro |
| Guardrails de output | T1 | Structured output validado |
| Governança de agente | T2 | Claro quem autoriza o agente a fazer o quê, com qual ferramenta |

## Harness (enforcement deste protocolo)

| Pilar | Tier | O que verificar |
|---|---|---|
| Hooks do harness ativos | T0 | `.claude/settings.json` contém os hooks de `.claude/settings.init-harness.json`; scripts em `.claude/hooks/` existem |
| `uv` disponível | T0 | `uv --version` responde; sem ele os hooks falham abertos |
| Pre-commit ativo | T0 | `git config --get core.hooksPath` = `.githooks` e `.githooks/pre-commit` executável |
| Grafo atualizado automaticamente | T0 | `graphify hook status` mostra hooks em `.githooks/` (ou `grafo: manual` com débito) |
| Credencial de produção fora do ambiente do agente | T1 | Máquina ou container onde o agente roda não tem credencial de produção |
| Proteção de branch no remoto | T1 | Branch base exige PR ou bloqueia push forçado |
| Guardrails testados | T1 | `tests/guardrails/` executado com sucesso na plataforma do projeto |