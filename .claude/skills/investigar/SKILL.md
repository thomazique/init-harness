---
name: investigar
description: Depuração por causa raiz, com hipótese testável, reprodução, teste de regressão que falha antes da correção e relatório com status. Use quando o usuário relatar erro, stack trace, teste falhando, comportamento inesperado, regressão ("funcionava ontem") ou teste intermitente, ou pedir para depurar ou achar a causa de algo. Não use para funcionalidade nova ou mudança de comportamento pedida, que seguem spec e orquestrar, nem para auditoria de segurança, que é pilares.
---

# investigar

## Lei de ferro

**Nenhuma correção sem causa raiz confirmada.** Corrigir o sintoma esconde o defeito e torna o
próximo bug mais difícil de achar. Primeiro a causa, depois a correção.

A investigação é leitura e experimento. A correção segue o ciclo normal do harness: trivial
vai direto, com registro na frente; não trivial passa por `spec` e, quando houver
implementação delegada, por `orquestrar`.

---

## Fase 1: coletar evidência

1. **Sintoma.** Ler a mensagem de erro, o stack trace e os passos de reprodução. Faltando
   contexto, fazer **uma** pergunta por vez.
2. **Caminho do código.** Do sintoma até as causas possíveis: grafo primeiro
   (`graphify query`, `graphify explain`), depois leitura dirigida. Antes de chamar dois
   trechos de duplicados, ler quem chama cada um: a diferença costuma estar no chamador
   (guarda, transação, escopo).
3. **Mudança recente.** `git log --oneline -20 -- <arquivos afetados>`. Se funcionava antes,
   a causa está no diff entre o estado bom e o ruim (`git bisect` quando o intervalo é longo).
4. **Reprodução determinística.** Sem reproduzir, coletar mais evidência; não pular para a
   correção.
5. **Histórico.** `uv run --no-project --python ">=3.10" .claude/hooks/memory.py retrieve "<componente>"`
   e `docs/ai/DEBITOS.md`. Bug recorrente na mesma área é sinal de problema estrutural, não
   coincidência.

Saída da fase: **"Hipótese de causa raiz: ..."**, afirmação específica e testável sobre o
que está errado e por quê.

## Fase 2: padrão conhecido

| Padrão | Assinatura | Onde olhar |
|---|---|---|
| Condição de corrida | Intermitente, depende de tempo | Estado compartilhado acessado em paralelo |
| Nulo propagado | `TypeError`, `NoneType`, `undefined` | Valor opcional sem guarda |
| Estado corrompido | Dado inconsistente, atualização parcial | Transação, callback, hook |
| Falha de integração | Timeout, resposta inesperada | Chamada externa, fronteira de serviço |
| Deriva de configuração | Funciona local, falha em homologação ou produção | Variável de ambiente, flag, estado do banco |
| Cache velho | Dado antigo que some ao limpar cache | Redis, CDN, cache do navegador ou do build |

Teste intermitente, falha só na CI, dependência de ordem ou de relógio: ler
`references/intermitente.md` antes da fase 3. Rerodar, aumentar timeout ou pular o teste
nunca é hipótese.

Pesquisa externa só com o erro **sanitizado**: sem host, IP, caminho, SQL, dado de cliente
ou identificador interno. Pesquisar a categoria do erro e a versão do framework, não a
mensagem crua.

## Fase 3: testar a hipótese

1. **Confirmar antes de corrigir.** Log temporário, asserção ou experimento no ponto suspeito;
   rodar a reprodução. A evidência bate com a hipótese?
2. **Hipótese errada:** voltar à fase 1 com o que foi aprendido. Não chutar.
3. **Regra das 3 tentativas.** Três hipóteses refutadas: **parar** e perguntar ao usuário,
   com as opções:
   - continuar com uma hipótese nova, descrita;
   - escalar para quem conhece o sistema;
   - instrumentar a área e esperar a próxima ocorrência.

Sinais de que é hora de desacelerar: "correção rápida por enquanto"; correção proposta antes
de rastrear o fluxo de dados; cada correção revela um problema em outro lugar (camada errada,
não código errado).

## Fase 4: corrigir

1. **Causa raiz, não sintoma.** A menor mudança que elimina o problema real.
2. **Diff mínimo.** Sem refatorar o vizinho (seção 7 do protocolo).
3. **Teste de regressão** que **falha sem a correção** (prova que o teste mede algo) e
   **passa com ela**. Mostrar as duas execuções.
4. **Suíte completa** com os comandos de teste, lint e typecheck do `CLAUDE.md`.
5. **Mais de 5 arquivos:** perguntar antes de seguir (seguir, dividir em parte crítica agora
   e resto depois, ou repensar uma abordagem mais localizada).

Nunca afrouxar o gate para passar: apagar ou pular teste, aumentar timeout ou retry, trocar
contagem exata por limite, adicionar `# noqa`/`@ts-ignore` ou engolir exceção. Antes de
encerrar, `uv run --no-project --python ">=3.10" .claude/hooks/gate_diff.py` mostra esses
trechos; cada um precisa de justificativa visível ou volta atrás.

## Fase 5: verificar e relatar

Reproduzir o cenário original e confirmar que o defeito sumiu. Rodar a suíte e citar comando
e resultado observados. Depois, o relatório:

```text
RELATÓRIO DE INVESTIGAÇÃO
Sintoma:        <o que o usuário observou>
Causa raiz:     <o que estava errado de fato>
Correção:       <o que mudou, com arquivo:linha>
Evidência:      <comando executado e resultado; tipo de evidência>
Regressão:      <arquivo:linha do teste; falhou antes, passa depois>
Relacionado:    <débito, bug anterior na mesma área, nota estrutural>
Status:         CONCLUÍDO | CONCLUÍDO_COM_RESSALVAS | BLOQUEADO | FALTA_CONTEXTO
```

Registrar na frente (seção 6 do protocolo). Bug recorrente ou causa estrutural vira débito em
`docs/ai/DEBITOS.md`; gotcha operacional confirmado vai para o `CLAUDE.md`. Assim a próxima
investigação na mesma área o encontra por `memory.py retrieve`.

---

## Regras

- 3 tentativas falhas: parar e questionar a arquitetura, não testar a quarta variação.
- Nunca aplicar correção que não dá para verificar. Sem reproduzir e confirmar, não entregar.
- Nunca dizer "isso deve resolver". Verificar e mostrar.
- Status (seção 5 do protocolo):
  - **CONCLUÍDO**: causa raiz achada, correção aplicada, teste de regressão escrito, suíte verde;
  - **CONCLUÍDO_COM_RESSALVAS**: corrigido sem verificação completa (intermitente, depende de homologação);
  - **BLOQUEADO**: causa raiz incerta depois da investigação; escalado;
  - **FALTA_CONTEXTO**: falta informação; dizer exatamente qual.

Método adaptado do `/investigate` do gstack (MIT).
