# AgendAí

Plataforma web em Python 3.10+ com SQLite. Usa apenas a biblioteca padrão; não precisa instalar pacotes.

## Executar

```powershell
cd C:\Users\Matheus\Desktop\AgendAi
python app.py
```

Abra http://127.0.0.1:8765. Mantenha o terminal aberto. Ctrl+C encerra o servidor. Para outra porta: `python app.py --port 8766`.

Na primeira execução, o banco é criado e uma **senha inicial aleatória** aparece no terminal para as seis contas de exemplo. Guarde-a e altere-a em **Alterar senha**. Ela não é exibida nas próximas execuções.

| Perfil | E-mail |
|---|---|
| Admin | admin@agendai.com |
| Profissional — Marina | marina@agendai.com |
| Profissional — Rafael | rafael@agendai.com |
| Profissional — Beatriz | beatriz@agendai.com |
| Atendente | atendente@agendai.com |
| Paciente — Ana | ana@email.com |

O perfil é identificado pela conta. Profissionais e atendentes começam com a senha `SenhaPadraoFunc` e podem trocá-la em **Alterar senha**. Essa senha também é aplicada uma única vez aos funcionários anteriores; trocas posteriores são preservadas. Admin e paciente de exemplo usam a senha aleatória exibida na primeira execução. Cadastros exigem entre 8 e 128 caracteres. Dados antigos que existiam apenas na memória não são migrados.

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

## Dados e manutenção

O banco fica em `data/agendai.sqlite3`. Contas, consultas, disponibilidade e sessões válidas sobrevivem ao reinício. A pasta `data/` não entra no Git. Não a apague para atualizar o programa.

Backup consistente, mesmo com o servidor aberto:

```powershell
python manage.py backup
```

As cópias ficam em `data/backups/`. Para restaurar, encerre o servidor e restaure a cópia com uma ferramenta SQLite, preservando primeiro o banco atual. Use o comando de backup: copiar apenas o arquivo principal com o servidor aberto pode omitir alterações do WAL.

Se esquecer a senha, o responsável com acesso ao computador pode redefini-la pelo terminal. A senha é solicitada sem aparecer na tela:

```powershell
python manage.py reset-password admin@agendai.com
```

O banco pode ser configurado pela variável `AGENDAI_DB`. Datas e horários usam o relógio local do computador da clínica; configure-o para São Paulo.

## Estrutura

- `app.py`: servidor local, rotas e telas.
- `backend.py`: banco, autenticação, permissões e regras de negócio.
- `manage.py`: backup e recuperação local de senha.
- `static/`: estilos e retratos fictícios.

## Escopo

Backend funcional para execução local, restrito a 127.0.0.1. Para hospedagem pública ainda é necessário preparar servidor de produção, HTTPS, gestão de segredos, backups externos e políticas de tratamento de dados. Recuperação e confirmação de e-mail e lembretes automáticos não estão integrados. Google Fonts é opcional.

