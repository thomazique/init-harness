# Privacidade e dados locais

O init-harness não possui telemetria, conta de usuário ou serviço remoto
próprio. Por padrão, a memória é Markdown no repositório e índices SQLite
reconstruíveis sob `.init-harness/memory/`.

Frentes, specs, decisões, débitos, handoffs e feedback de bootstrap podem ser
versionados pelo projeto. Não use esses arquivos para segredos ou dados pessoais
desnecessários. A detecção de padrões é defesa em profundidade, não garantia.

Graphify, clientes MCP e provedores de IA são integrações opt-in com suas
próprias políticas. Revise permissões, arquivos ignorados e o que será enviado
a ferramentas externas antes de habilitá-las. O runner `reviewer_claude.py`, quando usado,
envia ao provedor do seu cliente Claude o resumo de uma experiência e o texto da skill revisada.

O fluxo multiagente pode enviar contexto da tarefa e trechos ou arquivos necessários a mais de
uma chamada do mesmo provedor de IA. Perfis `cli` iniciam o executável local de Claude Code ou
Codex com a conta já autenticada e enviam o prompt delimitado ao provedor indicado no perfil.
Isso pode usar outra cota ou faturamento do provedor. A escolha do perfil é feita por atividade;
somente metadados de provedor, modelo, papel, frente e quantidade de chamadas ficam no ledger
SQLite local. O runner desativa a persistência local de sessões no Claude Code e no Codex; prompts
e respostas não são gravados pelo ledger, e o lote temporário pode ser apagado após a leitura.
As conexões MCP não são carregadas nesses subprocessos. Isso não altera retenção ou processamento
pelo provedor. O limite de chamadas não é um teto monetário.
