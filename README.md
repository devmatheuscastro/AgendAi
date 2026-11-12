# AgendAí

Plataforma web em Python 3.10+ com PostgreSQL 14 ou superior. Usa Psycopg 3 para conexão e python-dotenv para ler a configuração.

## Preparar o PostgreSQL

No pgAdmin, conectado ao banco `postgres` como administrador, execute os comandos de [sql/create_database.sql](sql/create_database.sql), um por vez. Substitua a senha de exemplo. O comando `CREATE DATABASE` deve ser executado fora de uma transação.

```sql
CREATE ROLE agendai WITH LOGIN PASSWORD 'sua_senha';
CREATE DATABASE agendai OWNER agendai ENCODING 'UTF8';
```

Se já possui um banco e usuário, use-os na configuração abaixo; não precisa criá-los novamente.

## Configurar e executar

```powershell
cd C:\Users\Matheus\Desktop\AgendAi
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Copie o exemplo apenas se ainda não tiver `.env`. Edite esse arquivo com o host, porta, banco, usuário e senha do seu PostgreSQL:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=agendai
DB_USER=agendai
DB_PASSWORD=sua_senha
DB_SSLMODE=prefer
```

Alternativamente, use `DATABASE_URL=postgresql://usuario:senha@host:5432/banco`. A URL tem prioridade sobre `DB_*`; caracteres especiais da senha precisam ser codificados na URL. Com `DB_PASSWORD`, não é necessário codificá-los. Variáveis do sistema têm prioridade sobre `.env`. O arquivo é lido pelo caminho do projeto, mesmo executando de outra pasta, e não entra no Git.

Para criar todas as tabelas e inicializar as contas:

```powershell
.\.venv\Scripts\python.exe manage.py init-db
.\.venv\Scripts\python.exe app.py
```

O SQL completo das tabelas está em [sql/schema.sql](sql/schema.sql). Também pode executá-lo manualmente no Query Tool do pgAdmin, conectado ao banco `agendai` como seu proprietário. Pelo terminal, se `psql` estiver no PATH:

```powershell
psql -h 127.0.0.1 -p 5432 -U agendai -d agendai -W -v ON_ERROR_STOP=1 -f sql/schema.sql
```

O servidor aplica esse mesmo script ao iniciar; as instruções são idempotentes e não apagam dados. O usuário precisa ter permissão para criar tabelas no banco.

Se preferir o comando curto, ative o ambiente virtual antes:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Abra http://127.0.0.1:8765. Mantenha o terminal aberto. Ctrl+C encerra o servidor. Para outra porta: `python app.py --port 8766`.

Na primeira inicialização de um banco vazio, as contas de exemplo são criadas. Uma **senha inicial aleatória** para admin e paciente aparece no terminal. Guarde-a e altere-a em **Alterar senha**. Ela não é exibida nas próximas execuções.

| Perfil | E-mail |
|---|---|
| Admin | admin@agendai.com |
| Profissional — Marina | marina@agendai.com |
| Profissional — Rafael | rafael@agendai.com |
| Profissional — Beatriz | beatriz@agendai.com |
| Atendente | atendente@agendai.com |
| Paciente — Ana | ana@email.com |

O perfil é identificado pela conta. Profissionais e atendentes começam com a senha `SenhaPadraoFunc` e podem trocá-la em **Alterar senha**. Trocas posteriores são preservadas. Cadastros exigem entre 8 e 128 caracteres.

## Funcionalidades

- Cadastro público apenas de pacientes. Admin cadastra profissionais e atendentes com senha inicial.
- Login, logout e alteração de senha. Hash PBKDF2-SHA256, salt individual, sessões de 8 horas, limitação de tentativas e proteção CSRF.
- Paciente consulta profissionais, agenda, cancela e vê apenas suas consultas.
- Profissional acessa sua própria agenda e disponibilidade.
- Atendente escolhe o médico, consulta o calendário e configura sua rotina ou exceções. Agenda para pacientes existentes ou cria uma conta com senha inicial para pacientes novos. A senha inicial deve ser entregue ao paciente fora da plataforma.
- Admin desliga funcionários, revogando sessões e retirando profissionais da busca. Consultas existentes são preservadas para a recepção.
- Horários de 08h a 18h, de hora em hora, com cores para livre, indisponível e agendado.
- Transações e índices únicos impedem duas consultas para o mesmo médico ou paciente no mesmo horário. Cancelamento preserva histórico e libera o horário.
- Validações no servidor, SQL parametrizado e auditoria de alterações.
- Médico abre **Registro do atendimento** na consulta da agenda e salva comentário/evolução, quadro do paciente e encaminhamento. Pode salvar um rascunho ou marcar a consulta como realizada após o horário de início.
- **Histórico de consultas** pesquisa atendimentos realizados pelo nome ou e-mail do paciente. Anotações clínicas são acessíveis apenas ao médico responsável; pacientes, atendentes, admin e outros médicos não têm acesso pela aplicação.
- Registros são persistidos com controle de versão e cópia da versão anterior a cada alteração. Consultas realizadas não podem ser canceladas. O banco é atualizado automaticamente ao iniciar, preservando os dados existentes.

## Dados e manutenção

Os dados ficam no servidor PostgreSQL configurado no `.env`. Contas, consultas, disponibilidade e sessões válidas sobrevivem ao reinício da aplicação. As tabelas podem ser consultadas pelo pgAdmin ou `psql`.

O arquivo SQLite antigo em `data/agendai.sqlite3` foi preservado, mas não é mais usado. Os dados dele **não são transferidos automaticamente** para PostgreSQL. `AGENDAI_DB` deixou de ser utilizado.

Backup consistente, mesmo com o servidor aberto:

```powershell
.\.venv\Scripts\python.exe manage.py backup
```

As cópias ficam em `backups/`, no formato customizado do `pg_dump`. Adicione a pasta `bin` do PostgreSQL ao PATH (neste computador: `C:\Program Files\PostgreSQL\18\bin`). Use `pg_dump` da mesma versão principal ou mais recente que o servidor. A senha é enviada pela variável de ambiente do subprocesso, não como argumento do comando.

Para restaurar em um banco vazio, use `pg_restore -h 127.0.0.1 -U agendai -d banco_destino -W backups/arquivo.dump`. Preserve os dados atuais antes de uma restauração.

Se esquecer a senha, o responsável com acesso ao computador pode redefini-la pelo terminal. A senha é solicitada sem aparecer na tela:

```powershell
.\.venv\Scripts\python.exe manage.py reset-password admin@agendai.com
```

Datas de consultas e horários da clínica usam o relógio local do computador; configure-o para São Paulo. Timestamps de auditoria são armazenados como `TIMESTAMPTZ`, com conexões em UTC.

## Estrutura

- `app.py`: servidor local, rotas e telas.
- `backend.py`: banco, autenticação, permissões e regras de negócio.
- `manage.py`: backup e recuperação local de senha.
- `config.py`: leitura do `.env` e configuração PostgreSQL.
- `sql/create_database.sql`: criação do usuário e banco.
- `sql/schema.sql`: tabelas, relacionamentos e índices.
- `.env.example`: exemplo de configuração sem credenciais reais.
- `static/`: estilos e retratos fictícios.

## Escopo

Backend funcional para execução local, restrito a 127.0.0.1. Para hospedagem pública ainda é necessário preparar servidor de produção, HTTPS, gestão de segredos, backups externos e políticas de tratamento de dados. Recuperação e confirmação de e-mail e lembretes automáticos não estão integrados. Google Fonts é opcional.

