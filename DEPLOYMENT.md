# Limpeza de dados antes de iniciar o Carbópolis em produção

O aplicativo disponibiliza o comando Flask `reset-user-data` para apagar os
dados de atividade acumulados pelas equipes. Ele não é executado ao iniciar o
site ou durante o build.

## Uso no Render

1. Faça o deploy normal e confirme que o serviço está conectado ao banco de
   produção correto por meio de `DATABASE_URL`.
2. Abra o **Shell** do serviço web no Render.
3. No diretório do aplicativo (`codigo/ivai_carbopolis`), confira primeiro a
   prévia:

   ```sh
   flask --app app reset-user-data
   ```

4. Se a prévia estiver correta e você tiver certeza de que está no banco
   desejado, confirme a exclusão:

   ```sh
   flask --app app reset-user-data --yes
   ```

Execute a confirmação uma única vez antes de liberar o sistema para as equipes.
Não adicione o comando ao **Build Command**, **Start Command** nem ao comando de
pre-deploy: esses comandos podem ser executados novamente em futuras
implantações e apagariam dados que os usuários criarem depois.

## O que será apagado

- Conversas com os personagens do módulo de entrevistas.
- Laudos e amostras do laboratório.
- Depoimentos salvos no Dossiê.
- Resultados do simulador.
- Rascunhos e perguntas do Dossiê.
- Respostas e progresso das missões.
- Sessões das equipes, incluindo os nomes dos integrantes. Todos precisarão
  entrar novamente.

## O que será preservado

- Grupos e senhas configuradas.
- Missões e configurações de atividade das missões.
- Textos, imagens e personalizações do painel administrativo.
- Pontos do mapa eventualmente armazenados e parâmetros do simulador.

O comando mostra as quantidades que seriam removidas sem alterar nada quando
executado sem `--yes`. A exclusão confirmada ocorre em uma única transação:
se houver falha no banco, ela é revertida.
