# Avisos de terceiros

O init-harness adapta práticas de outros projetos abertos. Esta página registra a origem e as
licenças.

## gstack

<https://github.com/garrytan/gstack>, licença MIT.

Adaptados para Python e para o protocolo do harness:

- `.claude/hooks/gate_diff.py`: classificação de caminhos e marcas RH do `lib/gate-diff` e o
  catálogo `review/gate-integrity.md`.
- `.claude/hooks/guard_bash.py`: famílias de padrões do `careful/bin/check-careful.sh`
  (ofuscação, PowerShell e cmd, bloqueio duro da raiz e de force-push na branch padrão,
  exceções de pastas de build).
- `.claude/skills/investigar/`: método do `investigate/` (lei de ferro, regra das 3
  tentativas, receita de teste intermitente).
- Princípios de evidência e status de conclusão do `INIT-HARNESS.md`: preâmbulo comum das
  skills do gstack ("Claims Need Evidence", "Completion Status Protocol") e `ETHOS.md`.
- Supervisor de segurança e pilares: `review/specialists/security.md` e fases do `cso/`.

```text
MIT License

Copyright (c) 2026 Garry Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Anthropic-Cybersecurity-Skills

<https://github.com/mukul975/Anthropic-Cybersecurity-Skills>, licença Apache-2.0. Projeto da
comunidade, sem vínculo com a Anthropic.

Nenhum arquivo foi copiado. Inspiraram, reescritos em português:

- O lint de roteamento de skills do `doctor.py` (gatilho, gatilho negativo, limites de
  tamanho, colisão entre descriptions), a partir de `tools/lint-descriptions.py` e
  `tools/detect-collisions.py`.
- Os pilares de MCP de terceiro (envenenamento de ferramenta, rug pull, token passthrough),
  a partir de `skills/auditing-mcp-servers-for-tool-poisoning`.

O catálogo completo, com 818 skills de SOC, forense, red team e conformidade, não é
distribuído pelo kit. Projetos de segurança podem instalá-lo à parte, seguindo o README dele.
