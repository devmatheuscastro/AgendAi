"""Configuração compartilhada pelo servidor e pelos comandos de manutenção."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False, encoding='utf-8-sig')


def database_options():
    """Variáveis do sistema têm prioridade sobre o arquivo .env."""
    url = os.getenv('DATABASE_URL', '').strip()
    options = {'connect_timeout': 10, 'application_name': 'agendai', 'options': '-c timezone=UTC'}
    if url:
        return url, options
    values = {'host': os.getenv('DB_HOST', '127.0.0.1'),
              'port': os.getenv('DB_PORT', '5432'),
              'dbname': os.getenv('DB_NAME', 'agendai'),
              'user': os.getenv('DB_USER', 'agendai'),
              'password': os.getenv('DB_PASSWORD', ''),
              'sslmode': os.getenv('DB_SSLMODE', 'prefer')}
    if not values['password']:
        raise ValueError('Configure DB_PASSWORD ou DATABASE_URL no arquivo .env.')
    return '', dict(options, **values)
