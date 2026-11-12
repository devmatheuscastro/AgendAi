"""Manutenção do AgendAí com PostgreSQL."""
import argparse
import getpass
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import backend
from config import ROOT, database_options


def main():
    parser = argparse.ArgumentParser(description='Manutenção do AgendAí')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init-db', help='Criar tabelas e contas iniciais, se o banco estiver vazio')
    reset = commands.add_parser('reset-password', help='Redefinir senha localmente')
    reset.add_argument('email')
    commands.add_parser('backup', help='Criar backup PostgreSQL com pg_dump')
    args = parser.parse_args()
    if args.command == 'init-db':
        backend.initialize()
        password = backend.seed_demo()
        print('Tabelas PostgreSQL criadas/verificadas.')
        if password:
            print('Senha inicial de admin e paciente de exemplo:', password)
            print('Funcionários: SenhaPadraoFunc')
        return
    if args.command == 'backup':
        executable = shutil.which('pg_dump')
        if not executable:
            parser.error('pg_dump não encontrado. Adicione a pasta bin do PostgreSQL ao PATH.')
        dsn, options = database_options()
        params = conninfo_to_dict(dsn, **options)
        environment = os.environ.copy()
        password = params.pop('password', '')
        if password:
            environment['PGPASSWORD'] = password
        directory = ROOT / 'backups'
        directory.mkdir(exist_ok=True)
        target = directory / f'agendai-{datetime.now():%Y%m%d-%H%M%S-%f}.dump'
        try:
            subprocess.run([executable, '--dbname', make_conninfo(**params), '--no-password',
                            '--format=custom', '--file', str(target)], env=environment,
                           check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            raise SystemExit('Falha no backup. Confira o .env, o acesso ao banco e a versão do pg_dump. O arquivo parcial não deve ser usado.')
        print(f'Backup criado: {target}')
        return
    email = backend.email_address(args.email)
    password = getpass.getpass('Nova senha (mínimo 8 caracteres): ')
    if password != getpass.getpass('Confirme a senha: '):
        parser.error('As senhas não coincidem.')
    hashed = backend.password_hash(password)
    with backend.connect(write=True) as db:
        user = db.execute('SELECT id FROM users WHERE email=%s', (email,)).fetchone()
        if not user:
            parser.error('Conta não encontrada.')
        db.execute('UPDATE users SET password=%s WHERE id=%s', (hashed,user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=%s', (user['id'],))
        backend.audit(db,user['id'],'password.reset.local',user['id'])
    print('Senha redefinida. Sessões anteriores foram encerradas.')


if __name__ == '__main__':
    try:
        main()
    except backend.DomainError as exc:
        raise SystemExit(str(exc))
    except (backend.DatabaseError, ValueError):
        raise SystemExit('Não foi possível acessar o PostgreSQL. Confira o .env e se o banco está iniciado.')
