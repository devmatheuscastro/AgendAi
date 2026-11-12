"""Manutenção local do AgendAí."""
import argparse
import getpass
import sqlite3
from datetime import datetime
import backend


def main():
    parser = argparse.ArgumentParser(description='Manutenção local do AgendAí')
    commands = parser.add_subparsers(dest='command', required=True)
    reset = commands.add_parser('reset-password', help='Redefinir senha localmente')
    reset.add_argument('email')
    commands.add_parser('backup', help='Criar cópia consistente do banco')
    args = parser.parse_args()
    if not backend.DB_PATH.exists():
        parser.error('Execute python app.py primeiro para criar o banco.')
    if args.command == 'backup':
        directory = backend.DB_PATH.parent / 'backups'
        directory.mkdir(exist_ok=True)
        target = directory / f'agendai-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3'
        with backend.connect() as source:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
            finally:
                destination.close()
        print(f'Backup criado: {target}')
        return
    email = backend.email_address(args.email)
    password = getpass.getpass('Nova senha (mínimo 8 caracteres): ')
    if password != getpass.getpass('Confirme a senha: '):
        parser.error('As senhas não coincidem.')
    hashed = backend.password_hash(password)
    with backend.connect(write=True) as db:
        user = db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if not user:
            parser.error('Conta não encontrada.')
        db.execute('UPDATE users SET password=? WHERE id=?', (hashed,user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
        backend.audit(db,user['id'],'password.reset.local',user['id'])
    print('Senha redefinida. Sessões anteriores foram encerradas.')


if __name__ == '__main__':
    try:
        main()
    except backend.DomainError as exc:
        raise SystemExit(str(exc))
