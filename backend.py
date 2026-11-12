"""Persistência e regras de negócio do AgendAí (SQLite, sem dependências)."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get('AGENDAI_DB', Path(__file__).parent / 'data' / 'agendai.sqlite3'))
HOURS = [f'{hour:02d}:00' for hour in range(8, 19)]
ROLES = {'paciente', 'profissional', 'atendente', 'admin'}
EMPLOYEE_INITIAL_PASSWORD = 'SenhaPadraoFunc'


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@contextmanager
def connect(write=False):
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        if write:
            db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def email_address(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise DomainError('Informe um e-mail válido.')
    return value


def text(value, label, maximum=120, required=True):
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise DomainError(f'Confira o campo {label} (máximo de {maximum} caracteres).')
    return value


def password_hash(password):
    if not 8 <= len(password) <= 128:
        raise DomainError('A senha deve ter entre 8 e 128 caracteres.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000)
    return f'pbkdf2_sha256$600000${salt}${digest.hex()}'


def password_matches(password, encoded):
    try:
        _, rounds, salt, expected = encoded.split('$')
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password TEXT, role TEXT NOT NULL CHECK(role IN ('paciente','profissional','atendente','admin')),
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS doctors (
            id TEXT PRIMARY KEY REFERENCES users(id), specialty TEXT NOT NULL,
            price INTEGER NOT NULL CHECK(price>=0), photo TEXT NOT NULL DEFAULT 'default.svg'
        );
        CREATE TABLE IF NOT EXISTS availability (
            doctor TEXT NOT NULL REFERENCES doctors(id), day TEXT NOT NULL,
            hours TEXT NOT NULL, PRIMARY KEY(doctor,day)
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id TEXT PRIMARY KEY, doctor TEXT NOT NULL REFERENCES doctors(id),
            patient_id TEXT NOT NULL REFERENCES users(id), patient TEXT NOT NULL,
            date TEXT NOT NULL, time TEXT NOT NULL, reason TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Confirmado'
                CHECK(status IN ('Confirmado','Cancelado')),
            created_by TEXT NOT NULL REFERENCES users(id), cancelled_by TEXT REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, cancelled_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS doctor_slot ON appointments(doctor,date,time) WHERE status='Confirmado';
        CREATE UNIQUE INDEX IF NOT EXISTS patient_slot ON appointments(patient_id,date,time) WHERE status='Confirmado';
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            key TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, until REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, actor TEXT REFERENCES users(id), action TEXT NOT NULL,
            target TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS encounters (
            appointment_id TEXT PRIMARY KEY REFERENCES appointments(id),
            comment TEXT NOT NULL DEFAULT '', condition TEXT NOT NULL DEFAULT '',
            referral TEXT NOT NULL DEFAULT '', completed_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS encounter_revisions (
            id INTEGER PRIMARY KEY, appointment_id TEXT NOT NULL REFERENCES appointments(id),
            actor TEXT NOT NULL REFERENCES users(id), comment TEXT NOT NULL,
            condition TEXT NOT NULL, referral TEXT NOT NULL,
            version INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        PRAGMA user_version=2;
        ''')


def seed_demo():
    """Dados opcionais, criados uma única vez; a senha é gerada localmente."""
    with connect(write=True) as db:
        if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            return None
        password = secrets.token_urlsafe(12)
        hashed = password_hash(password)
        accounts = [('1', 'Marina Costa', 'marina@agendai.com', 'profissional'),
                    ('2', 'Rafael Mendes', 'rafael@agendai.com', 'profissional'),
                    ('3', 'Beatriz Almeida', 'beatriz@agendai.com', 'profissional'),
                    ('4', 'Lucas Oliveira', 'atendente@agendai.com', 'atendente'),
                    ('admin', 'Administrador', 'admin@agendai.com', 'admin'),
                    ('ana', 'Ana Silva', 'ana@email.com', 'paciente')]
        for ident, name, email, role in accounts:
            account_hash = password_hash(EMPLOYEE_INITIAL_PASSWORD) if role in {'profissional', 'atendente'} else hashed
            db.execute('INSERT INTO users(id,name,email,password,role) VALUES(?,?,?,?,?)', (ident,name,email,account_hash,role))
        for ident, specialty, price, photo in [('1','Cardiologia',280,'marina.png'), ('2','Clínica geral',180,'rafael.png'), ('3','Dermatologia',250,'beatriz.png')]:
            db.execute('INSERT INTO doctors VALUES(?,?,?,?)', (ident,specialty,price,photo))
        return password


def audit(db, actor, action, target):
    db.execute('INSERT INTO audit(actor,action,target) VALUES(?,?,?)', (actor,action,target))


def apply_employee_initial_password():
    """Atualiza funcionários existentes uma única vez; preserva futuras trocas."""
    with connect(write=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)')
        marker = 'employee_initial_password_v1'
        if db.execute('SELECT 1 FROM migrations WHERE name=?', (marker,)).fetchone():
            return
        for row in db.execute("SELECT id FROM users WHERE role IN ('profissional','atendente')").fetchall():
            db.execute('UPDATE users SET password=? WHERE id=?', (password_hash(EMPLOYEE_INITIAL_PASSWORD),row['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            audit(db,row['id'],'password.initial.employee',row['id'])
        db.execute('INSERT INTO migrations VALUES(?)', (marker,))


def register(name, email, password):
    name, email = text(name, 'nome'), email_address(email)
    hashed = password_hash(password)
    with connect(write=True) as db:
        existing = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if existing:
            raise DomainError('Este e-mail já está cadastrado. Procure a recepção para obter acesso.')
        ident = secrets.token_hex(16)
        db.execute('INSERT INTO users(id,name,email,password,role) VALUES(?,?,?,?,?)', (ident,name,email,hashed,'paciente'))
        audit(db, ident, 'patient.register', ident)


def authenticate(email, password, address):
    email = email_address(email)
    if len(password) > 128:
        raise DomainError('E-mail ou senha inválidos.', 401)
    key = hashlib.sha256((address + '|' + email).encode()).hexdigest()
    now = time.time()
    with connect(write=True) as db:
        attempt = db.execute('SELECT * FROM login_attempts WHERE key=?', (key,)).fetchone()
        if attempt and attempt['until'] > now and attempt['count'] >= 8:
            raise DomainError('Muitas tentativas. Aguarde 15 minutos e tente novamente.', 429)
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        valid = password_matches(password, user['password'] if user else 'pbkdf2_sha256$600000$00000000000000000000000000000000$00')
        if not user or not valid or not user['active']:
            count = attempt['count'] + 1 if attempt and attempt['until'] > now else 1
            db.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (key,count,now+900))
            # Commit antes da exceção para manter o contador.
            db.commit()
            raise DomainError('E-mail ou senha inválidos.', 401)
        db.execute('DELETE FROM login_attempts WHERE key=?', (key,))
        db.execute('DELETE FROM sessions WHERE expires<?', (now,))
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),user['id'],now+28800))
        return token


def session_user(token):
    if not token:
        return None
    with connect() as db:
        user = db.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1', (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    if not user:
        return None
    return {'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role'], 'doctor': user['id'] if user['role']=='profissional' else ''}


def logout(token):
    with connect(write=True) as db:
        db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))


def snapshot():
    with connect() as db:
        doctors = [dict(r) for r in db.execute('SELECT d.*,u.name,u.active FROM doctors d JOIN users u ON u.id=d.id')]
        staff = [dict(r) for r in db.execute("SELECT id,name,email,role,active FROM users WHERE role IN ('profissional','atendente') ORDER BY created_at,id")]
        appointments = [dict(r) for r in db.execute('SELECT a.*,u.email AS owner FROM appointments a JOIN users u ON u.id=a.patient_id')]
        completed = {r['appointment_id'] for r in db.execute('SELECT appointment_id FROM encounters WHERE completed_at IS NOT NULL')}
        for appointment in appointments:
            if appointment['id'] in completed:
                appointment['status'] = 'Realizado'
        routines, days = {}, {}
        for row in db.execute('SELECT * FROM availability'):
            if row['day'] == '*': routines[row['doctor']] = json.loads(row['hours'])
            else: days[(row['doctor'],row['day'])] = json.loads(row['hours'])
    return doctors, staff, appointments, routines, days


def require(user, roles):
    if not user or user['role'] not in roles:
        raise DomainError('Acesso não permitido.', 403)


def active_doctor(db, ident):
    if not db.execute('SELECT 1 FROM doctors d JOIN users u ON d.id=u.id WHERE d.id=? AND u.active=1', (ident,)).fetchone():
        raise DomainError('Profissional indisponível.', 404)


def validate_day(day):
    try:
        parsed = datetime.strptime(day, '%Y-%m-%d').date()
        if parsed.isoformat() != day:
            raise ValueError()
        return parsed
    except ValueError:
        raise DomainError('Data inválida.')


def book(user, data):
    require(user, {'paciente','atendente'})
    doc, day, hour = data['doctor'], data['date'], data['time']
    validate_day(day)
    if hour not in HOURS or datetime.fromisoformat(day+'T'+hour) <= datetime.now():
        raise DomainError('Escolha um horário futuro dentro do funcionamento da clínica.')
    reason = text(data['reason'], 'motivo', 500)
    description = text(data.get('description',''), 'descrição', 2000, False)
    with connect(write=True) as db:
        active_doctor(db, doc)
        row = db.execute('SELECT hours FROM availability WHERE doctor=? AND day IN (?,\'*\') ORDER BY CASE WHEN day=? THEN 0 ELSE 1 END LIMIT 1', (doc,day,day)).fetchone()
        if hour not in (json.loads(row['hours']) if row else HOURS):
            raise DomainError('O médico não atende neste horário.', 409)
        if user['role'] == 'paciente':
            patient_id, name = user['id'], user['name']
        else:
            name, email = text(data.get('patient',''), 'paciente'), email_address(data.get('patient_email',''))
            patient = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if not patient:
                initial = data.get('patient_password', '')
                if not initial:
                    raise DomainError('Paciente não cadastrado. Informe uma senha inicial para criar a conta dele.')
                patient_id = secrets.token_hex(16)
                db.execute("INSERT INTO users(id,name,email,password,role) VALUES(?,?,?,?, 'paciente')", (patient_id,name,email,password_hash(initial)))
                audit(db,user['id'],'patient.create',patient_id)
            elif patient['role'] != 'paciente' or not patient['active']:
                raise DomainError('Este e-mail não pertence a um paciente ativo.')
            else:
                patient_id, name = patient['id'], patient['name']
        ident = secrets.token_hex(16)
        try:
            db.execute('INSERT INTO appointments(id,doctor,patient_id,patient,date,time,reason,description,created_by) VALUES(?,?,?,?,?,?,?,?,?)', (ident,doc,patient_id,name,day,hour,reason,description,user['id']))
        except sqlite3.IntegrityError:
            raise DomainError('O médico ou o paciente já possui uma consulta neste horário.', 409)
        audit(db,user['id'],'appointment.book',ident)
    return doc


def cancel(user, ident):
    require(user, {'paciente','profissional','atendente'})
    with connect(write=True) as db:
        appointment = db.execute('SELECT * FROM appointments WHERE id=?', (ident,)).fetchone()
        if not appointment:
            raise DomainError('Consulta não encontrada.', 404)
        if user['role']=='paciente' and appointment['patient_id']!=user['id'] or user['role']=='profissional' and appointment['doctor']!=user['id']:
            raise DomainError('Acesso não permitido.', 403)
        if db.execute('SELECT 1 FROM encounters WHERE appointment_id=? AND completed_at IS NOT NULL', (ident,)).fetchone():
            raise DomainError('Consultas realizadas não podem ser canceladas.', 409)
        if appointment['status']=='Confirmado':
            db.execute("UPDATE appointments SET status='Cancelado',cancelled_by=?,cancelled_at=CURRENT_TIMESTAMP WHERE id=?", (user['id'],ident))
            audit(db,user['id'],'appointment.cancel',ident)
        return appointment['doctor']


def save_hours(user, doc, day, scope, hours):
    require(user, {'profissional','atendente'})
    if user['role']=='profissional': doc = user['id']
    if scope not in {'day','routine'} or not set(hours) <= set(HOURS):
        raise DomainError('Configuração de horários inválida.')
    validate_day(day)
    if scope=='day' and day < datetime.now().date().isoformat():
        raise DomainError('Não é possível alterar a disponibilidade de uma data passada.')
    with connect(write=True) as db:
        active_doctor(db,doc)
        selected = set(hours)
        if scope=='day':
            selected.update(r['time'] for r in db.execute("SELECT time FROM appointments WHERE doctor=? AND date=? AND status='Confirmado'", (doc,day)))
        db.execute('INSERT OR REPLACE INTO availability VALUES(?,?,?)', (doc,'*' if scope=='routine' else day,json.dumps(sorted(selected))))
        audit(db,user['id'],'availability.save',doc)
    return doc


def create_employee(user, data):
    require(user, {'admin'})
    name, email = text(data['name'],'nome'), email_address(data['email'])
    role = data['role']
    if role not in {'profissional','atendente'}:
        raise DomainError('Perfil de funcionário inválido.')
    hashed = password_hash(EMPLOYEE_INITIAL_PASSWORD)
    specialty = text(data.get('specialty',''), 'especialidade') if role=='profissional' else ''
    price = data.get('price','180') or '180'
    if role=='profissional' and (not price.isdigit() or int(price)>100000):
        raise DomainError('Informe um valor inteiro válido para a consulta.')
    with connect(write=True) as db:
        ident = secrets.token_hex(16)
        try:
            db.execute('INSERT INTO users(id,name,email,password,role) VALUES(?,?,?,?,?)', (ident,name,email,hashed,role))
        except sqlite3.IntegrityError:
            raise DomainError('Este e-mail já está cadastrado.')
        if role=='profissional':
            db.execute('INSERT INTO doctors(id,specialty,price) VALUES(?,?,?)', (ident,specialty,int(price)))
        audit(db,user['id'],'employee.create',ident)


def dismiss(user, ident):
    require(user, {'admin'})
    with connect(write=True) as db:
        employee = db.execute("SELECT * FROM users WHERE id=? AND role IN ('profissional','atendente')", (ident,)).fetchone()
        if not employee:
            raise DomainError('Funcionário não encontrado.', 404)
        db.execute('UPDATE users SET active=0 WHERE id=?', (ident,))
        db.execute('DELETE FROM sessions WHERE user_id=?', (ident,))
        audit(db,user['id'],'employee.dismiss',ident)


def change_password(user, current, new):
    hashed = password_hash(new)
    with connect(write=True) as db:
        row = db.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()
        if not row or not password_matches(current, row['password']):
            raise DomainError('Senha atual incorreta.', 401)
        db.execute('UPDATE users SET password=? WHERE id=?', (hashed,user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
        audit(db,user['id'],'password.change',user['id'])


def encounter(user, ident):
    require(user, {'profissional'})
    with connect() as db:
        row = db.execute('''SELECT a.*,u.email AS owner,e.comment,e.condition,e.referral,
            e.completed_at,e.updated_at,COALESCE(e.version,0) AS version
            FROM appointments a JOIN users u ON u.id=a.patient_id
            LEFT JOIN encounters e ON e.appointment_id=a.id
            WHERE a.id=? AND a.doctor=?''', (ident,user['id'])).fetchone()
        if not row:
            raise DomainError('Atendimento não encontrado.', 404)
        return dict(row)


def save_encounter(user, data):
    require(user, {'profissional'})
    ident = data.get('id','')
    comment = text(data.get('comment',''), 'comentário', 10000)
    condition = text(data.get('condition',''), 'quadro do paciente', 10000, False)
    referral = text(data.get('referral',''), 'encaminhamento', 10000, False)
    complete = data.get('complete') == 'yes'
    with connect(write=True) as db:
        appointment = db.execute('SELECT * FROM appointments WHERE id=? AND doctor=?', (ident,user['id'])).fetchone()
        if not appointment:
            raise DomainError('Atendimento não encontrado.', 404)
        if appointment['status'] == 'Cancelado':
            raise DomainError('Não é possível registrar um atendimento cancelado.', 409)
        if complete and datetime.fromisoformat(appointment['date']+'T'+appointment['time']) > datetime.now():
            raise DomainError('A consulta só pode ser marcada como realizada após o horário de início.')
        old = db.execute('SELECT * FROM encounters WHERE appointment_id=?', (ident,)).fetchone()
        version = old['version'] if old else 0
        if str(version) != data.get('version','0'):
            raise DomainError('O registro foi alterado em outra janela. Recarregue antes de editar.', 409)
        if old:
            db.execute('INSERT INTO encounter_revisions(appointment_id,actor,comment,condition,referral,version) VALUES(?,?,?,?,?,?)', (ident,user['id'],old['comment'],old['condition'],old['referral'],version))
        completed_at = old['completed_at'] if old else None
        if complete and not completed_at:
            completed_at = datetime.now().isoformat(timespec='seconds')
        db.execute('''INSERT INTO encounters(appointment_id,comment,condition,referral,completed_at,version)
            VALUES(?,?,?,?,?,?) ON CONFLICT(appointment_id) DO UPDATE SET
            comment=excluded.comment,condition=excluded.condition,referral=excluded.referral,
            completed_at=excluded.completed_at,version=excluded.version,updated_at=CURRENT_TIMESTAMP''',
            (ident,comment,condition,referral,completed_at,version+1))
        audit(db,user['id'],'encounter.complete' if complete else 'encounter.save',ident)
    return ident


def encounter_history(user, query=''):
    require(user, {'profissional'})
    with connect() as db:
        rows = db.execute('''SELECT a.id,a.patient,a.patient_id,a.date,a.time,u.email,e.comment,e.condition,e.referral
            FROM appointments a JOIN encounters e ON e.appointment_id=a.id JOIN users u ON u.id=a.patient_id
            WHERE a.doctor=? AND e.completed_at IS NOT NULL ORDER BY a.date DESC,a.time DESC''', (user['id'],)).fetchall()
    term = query.strip().casefold()
    return [dict(row) for row in rows if term in row['patient'].casefold() or term in row['email'].casefold()]
