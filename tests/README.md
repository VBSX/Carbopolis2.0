# Testes do Carbópolis

Execute a suíte a partir da raiz do repositório:

```sh
npm test
```

Ou, diretamente com Python, dentro de `codigo/ivai_carbopolis`:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

Os testes usam um banco SQLite em memória, criam grupos e dados de demonstração e
limpam o banco ao final de cada caso. Não é necessário configurar `DATABASE_URL`
nem uma chave Gemini. As chamadas ao Gemini são simuladas; um teste verifica a
resposta amigável quando `GEMINI_API_KEY` está ausente.

Para habilitar entrevistas e tutor no ambiente local, defina `GEMINI_API_KEY`
no arquivo `.env.local` na raiz do projeto ou como variável de ambiente do
servidor. O modelo principal é `gemini-3.8-flash`; se a API responder com
sobrecarga HTTP 503, o servidor tenta uma vez com `gemini-3.5-flash-lite`.
Ambos podem ser ajustados por `GEMINI_MODEL` e `GEMINI_FALLBACK_MODEL`.
O aplicativo informa quando a chave está ausente. Nunca adicione a chave ao
código-fonte nem a compartilhe. Reinicie o servidor depois de atualizar a
configuração.

A suíte cobre login/logout, acesso por grupo, páginas compartilhadas e restritas,
tela inicial com imagem configurável e sem mapa interativo, laboratório, missões, dossiê,
simulador, entrevistas, tutor e ações principais do painel administrativo.

## Limpar dados de atividade para produção

Antes de abrir o sistema às equipes, o administrador pode executar
`flask --app app reset-user-data` no Shell do serviço Render para ver a prévia
e `flask --app app reset-user-data --yes` para confirmar a limpeza. O comando
remove conversas, laudos, amostras, depoimentos, resultados do simulador,
rascunhos, progresso e sessões com nomes de integrantes. Preserva grupos/senhas,
missões e conteúdo administrativo. Execute manualmente uma vez; não inclua a
limpeza no Build Command, Start Command ou pre-deploy. Consulte
[DEPLOYMENT.md](../DEPLOYMENT.md) para detalhes.
