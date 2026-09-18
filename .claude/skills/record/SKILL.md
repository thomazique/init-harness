---
name: record
description: Registra uma experiência relevante da sessão para alimentar a evolução de uma skill do projeto. Use quando uma skill falhar, exigir correção humana, produzir um resultado inesperado ou revelar uma melhoria clara.
---
# record

Use esta skill quando houver uma experiência que não deve se perder entre sessões.

Registre somente fatos observáveis: tarefa, resultado, resumo do erro ou acerto,
correção humana, ferramentas, arquivos e métricas. Não registre prompts completos,
credenciais nem raciocínio privado.

```powershell
python .claude/hooks/skill_evolution.py record <skill> `
  --task-id <id> `
  --outcome success|failure|partial|blocked `
  --summary "fato observado" `
  [--score 0..1] [--failure-type <tipo>] [--human-correction] `
  [--tool <nome>] [--file <caminho>] [--metric nome=valor] [--tag <tag>]
```

Depois do registro, o harness procura padrões recorrentes e grava sugestões em
`.init-harness/skills/<skill>/suggestions.jsonl`. Consulte-as com:

```powershell
python .claude/hooks/skill_evolution.py suggestions <skill>
```

Uma sugestão nunca altera a skill automaticamente. Ela é evidência para uma futura
proposta, avaliação e aprovação.
