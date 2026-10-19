# Teste intermitente

Teste intermitente é aquele cujo veredito depende de algo além do código que ele cobre. A lei
de ferro vale aqui: nenhuma reexecução, timeout maior, retry ou skip antes de nomear a causa e
prová-la. "Intermitente" é sintoma, nunca causa.

## Procedimento

1. **Reproduzir na base.** Em um worktree da branch base (`git worktree add <dir> <base>`),
   rodar o arquivo de teste sozinho N vezes (N ≥ 10) com o comando de teste do projeto. Anotar
   `falhas/N` na base e depois na branch. Falha que reproduz na base está fora da mudança;
   falha que só aparece na branch está dentro dela.
2. **Nomear a dependência.** Comparar os logs de uma execução boa e de uma ruim até a primeira
   divergência e dar nome ao que muda: tempo, ordem de arquivos, estado compartilhado entre
   testes, rede, relógio, limite de recurso.
3. **Datar a regressão** quando a CI guarda histórico: comparar duração, número de retries e
   o teste que falha nas últimas execuções verdes da base e da branch. A primeira execução em
   que o número mudou aponta o commit.
4. **Sonda forçada.** Construir a menor mudança que faz o teste falhar **sempre** pela causa
   alegada: injetar o atraso, fixar a ordem dos arquivos, congelar o relógio, esgotar o
   recurso. Mostrar a sonda falhando antes da correção e passando depois. Sem sonda, não há
   causa.
5. **Nunca afrouxar.** Timeout maior, retry, asserção mais frouxa ou skip é afrouxamento de
   gate (`gate_diff.py`, marca RH-15 ou RH-1). A correção mora no código ou no isolamento do
   teste, não no limiar.
6. **Reexecutar só com causa conhecida e fora da mudança** (infraestrutura, poluidor já
   corrigido na base, indisponibilidade de provedor), dito explicitamente na PR. Reexecução é
   diagnóstico, nunca o verde.

## Asserção de tempo

Quando a linha que falha compara um tempo decorrido com um limite, ou dorme e depois afirma:

1. **Distribuição sob a mesma carga.** Registrar o valor medido em cada execução e rodar o
   arquivo N ≥ 20 vezes na base e na branch, na mesma máquina e concorrência. Comparar mínimo,
   mediana, p95, máximo e falhas contra o limite. Distribuição que mudou na branch é regressão
   da branch; a mesma distribuição nas duas é teste que depende da carga da máquina.
2. **Sonda forçada.** Injetar o atraso que a carga causa e mostrar a asserção falhando sempre.
3. **Corrigir a medição, nunca o limite.** Afirmar sobre o resultado, usar relógio injetado,
   prazo forçado ou espera ativa com prazo.

## Poluidor e ordem

Teste que passa sozinho e falha na suíte: bisseccionar a lista de testes que rodam antes até
achar o poluidor (o teste que deixa estado para trás). Corrigir a limpeza do poluidor ou o
isolamento da vítima, nunca a ordem de execução.

## Evidência na PR

Toda correção de teste intermitente leva na PR: saída da sonda antes e depois, `falhas/N` na
base e na branch e um destino explícito: `corrigido nesta PR`, `reexecutar; causa fora da PR:
<qual>` ou `decisão do dono necessária: <o afrouxamento proposto e por quê>`.
