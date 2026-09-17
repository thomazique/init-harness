# Contribuindo

Requer Python 3.10+ e Git. Antes de abrir um pull request, execute:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```

- Não inclua segredos, dados de clientes, prompts completos ou logs sensíveis.
- Preserve Markdown/Git como fonte canônica e índices como artefatos derivados.
- Sugestões e recuperações devem indicar evidência; não podem criar relações canônicas automaticamente.
- Mudanças visíveis exigem teste e entrada no `CHANGELOG.md`.
- Descreva impactos em segurança, privacidade, migração e compatibilidade.

Para vulnerabilidades, siga [SECURITY.md](SECURITY.md), nunca issue ou PR público.
