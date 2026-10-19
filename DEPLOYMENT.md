# Deploy no Render e preparação de dados

O aplicativo disponibiliza o comando Flask `reset-user-data` para apagar os
dados de atividade acumulados pelas equipes. Ele não é executado ao iniciar o
site ou durante o build.

## Publicar no Render

O repositório inclui `render.yaml`. No Render, crie um **Blueprint** conectado
ao repositório GitHub `VBSX/Carbopolis2.0` e confirme a criação do serviço
`carbopolis-2`. O serviço usa o plano gratuito e inicia o Flask com Gunicorn.

Antes de confirmar o Blueprint, preencha as variáveis solicitadas:

- `DATABASE_URL`: URL **pooled** do Neon para as requisições do aplicativo.
- `DATABASE_URL_UNPOOLED`: URL **direta** do Neon, usada pelo seed inicial.
- `GEMINI_API_KEY`: chave da API do Gemini.

O Render gera `SECRET_KEY`. As senhas padrão dos grupos permanecem: TermoBR
`termo`, HydroSul `hidro`, Comunidade `ivai`, Cientistas `energia` e
administração `admin`.

O build não executa o seed nem apaga dados. Para inicializar um banco de
produção novo, configure temporariamente na máquina local as variáveis
`APP_ENV=production` e `DATABASE_URL_UNPOOLED`. Execute o comando abaixo uma
única vez, na raiz do projeto:

```sh
python seed.py
```

O seed usa a URL direta e aplica as senhas padrão às equipes. Não o inclua no
comando de build, start ou pre-deploy: ele também atualiza conteúdo
administrável. A aplicação cria tabelas ausentes no startup; mudanças futuras
de esquema devem ser planejadas como migrações. O plano gratuito do Render não
oferece shell para executar comandos avulsos; por isso, execute o seed
localmente com acesso ao Neon de produção.

O plano gratuito não oferece disco persistente: imagens carregadas no painel
administrativo em `static/uploads` podem desaparecer após reinícios ou novos
deploys. Para preservá-las, será necessário um plano com disco persistente
montado nesse diretório ou storage externo. O serviço gratuito também pode
suspender quando estiver ocioso.

## Limpar os dados antes de liberar o sistema

Configure `APP_ENV=production` e `DATABASE_URL` na máquina local para apontar
ao banco de produção correto. Execute os comandos a seguir na raiz do projeto;
o primeiro apenas mostra a prévia:

```sh
flask --app app reset-user-data
```

Se a prévia estiver correta e você tiver certeza de que está no banco
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
