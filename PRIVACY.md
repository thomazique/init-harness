# Privacidade e dados locais

O init-harness não possui telemetria, conta de usuário ou serviço remoto
próprio. Por padrão, a memória é Markdown no repositório e índices SQLite
reconstruíveis sob `.init-harness/memory/`.

Frentes, specs, decisões, débitos, handoffs e feedback de bootstrap podem ser
versionados pelo projeto. Não use esses arquivos para segredos ou dados pessoais
desnecessários. A detecção de padrões é defesa em profundidade, não garantia.

Graphify, clientes MCP e provedores de IA são integrações opt-in com suas
próprias políticas. Revise permissões, arquivos ignorados e o que será enviado
a ferramentas externas antes de habilitá-las.
