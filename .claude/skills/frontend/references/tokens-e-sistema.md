# Tokens e sistema visual

## Fonte de verdade

Antes de criar estilos, localize o tema, design system, componentes e convenções existentes. Amplie a fonte de verdade já usada pelo projeto. Se não houver sistema, comece no escopo necessário e mantenha os valores compartilhados num lugar coerente com a arquitetura da stack.

Uma separação útil, quando apropriada, é:

| Camada | Significado | Uso |
| --- | --- | --- |
| Primitiva | valor bruto de cor, espaço, raio ou duração | tema ou módulo central de tokens |
| Semântica | texto principal, superfície, foco, perigo ou sucesso | telas e componentes base |
| Componente | fundo do botão, altura do campo, padding de uma tabela | componente reutilizável |

Os nomes, arquivos e camadas variam entre tecnologias; não crie a estrutura se o projeto já tiver outra convenção adequada.

## Aplicação

- Evite repetir valores visuais em telas se eles pertencem ao tema ou a um componente partilhado.
- Nomeie tokens pelo papel semântico ou pelo lugar apropriado na escala, conforme a convenção local.
- Preserve os modos de cor e temas já suportados; não introduza variações que o produto não precisa.
- Mantenha estados como foco, erro, aviso e sucesso distinguíveis e legíveis sobre suas superfícies reais.
- Centralize uma nova decisão visual quando ela será reutilizada ou precisa ser consistente; não transforme cada valor local em abstração prematura.
- Documente exceções quando forem necessárias por conteúdo, plataforma ou requisito confirmado.

## Escalas e consistência

Use as escalas de tipografia, espaçamento, raio, elevação e duração que já existirem. Sem escalas existentes, derive novos valores dos componentes adjacentes e limite o conjunto introduzido. Densidade, tamanho de texto e espaçamento devem servir ao conteúdo e ao ambiente de uso do projeto.

Uma troca de identidade deve alterar as primitivas ou seus mapeamentos centrais sempre que a arquitetura permitir, em vez de exigir mudanças inconsistentes em cada tela.

## Exemplos de implementação

Variáveis CSS, arquivos de tema, objetos de estilo, recursos de plataforma e tokens de ferramentas visuais são opções possíveis, não recomendações para uma stack específica. Siga a tecnologia já instalada e evite adicionar dependências só para representar tokens.
