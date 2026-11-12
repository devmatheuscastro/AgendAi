"""AgendAí — MVP local, feito com a biblioteca padrão do Python."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from http.cookies import SimpleCookie
from datetime import date, timedelta
from html import escape
from pathlib import Path
from threading import RLock
import secrets

ROOT = Path(__file__).parent
LOCK = RLock()
SESSIONS = {}
ROLES = {'paciente': 'Paciente', 'profissional': 'Profissional', 'atendente': 'Atendente', 'admin': 'Admin'}
DOCTORS = [
    {'id': '1', 'name': 'Marina Costa', 'specialty': 'Cardiologia', 'initials': 'MC', 'color': 'rose', 'price': '280'},
    {'id': '2', 'name': 'Rafael Mendes', 'specialty': 'Clínica geral', 'initials': 'RM', 'color': 'blue', 'price': '180'},
    {'id': '3', 'name': 'Beatriz Almeida', 'specialty': 'Dermatologia', 'initials': 'BA', 'color': 'sand', 'price': '250'},
]
TIMES = ['08:00', '09:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00']
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
APPOINTMENTS = [{'id': 'demo', 'doctor': '1', 'patient': 'Ana Silva', 'owner': 'ana@email.com', 'date': TOMORROW, 'time': '09:00', 'reason': 'Consulta de rotina', 'description': '', 'status': 'Confirmado'}]
NOTICES = []
STAFF = [{'id': '1', 'name': 'Marina Costa', 'role': 'Profissional', 'active': True}, {'id': '2', 'name': 'Rafael Mendes', 'role': 'Profissional', 'active': True}, {'id': '3', 'name': 'Beatriz Almeida', 'role': 'Profissional', 'active': True}, {'id': '4', 'name': 'Lucas Oliveira', 'role': 'Atendente', 'active': True}]
BLOCKED = set()


def h(value):
    return escape(str(value), quote=True)


def doctor(ident):
    return next((d for d in DOCTORS if d['id'] == ident), DOCTORS[0])


def active_doctors():
    return [d for d in DOCTORS if any(s['id'] == d['id'] and s['active'] for s in STAFF)]


def occupied(doc, day, hour):
    return (doc, day, hour) in BLOCKED or any(a['doctor'] == doc and a['date'] == day and a['time'] == hour and a['status'] == 'Confirmado' for a in APPOINTMENTS)


def fmt(day):
    return date.fromisoformat(day).strftime('%d/%m/%Y')


def field(label, name, kind='text', value='', required=True):
    return f'<label>{label}<input type="{kind}" name="{name}" value="{h(value)}" {"required" if required else ""}></label>'


def page(title, content, user=None, current='', message=''):
    if user:
        role = user['role']
        menus = {'paciente': [('buscar', '⌕', 'Encontrar profissional'), ('consultas', '▦', 'Meus agendamentos'), ('avisos', '◉', 'Avisos')], 'profissional': [('agenda', '▦', 'Minha agenda'), ('horarios', '◷', 'Disponibilidade')], 'atendente': [('buscar', '⌕', 'Agendar consulta'), ('consultas', '▦', 'Agendamentos')], 'admin': [('equipe', '♧', 'Funcionários')]}
        links = ''.join(f'<a class="nav {"selected" if key == current else ""}" href="/{key}"><span>{icon}</span>{label}</a>' for key, icon, label in menus[role])
        shell = f'<aside><a class="brand" href="/">agend<span>aí</span><i>✳</i></a><div class="workspace">ESPAÇO DO {ROLES[role].upper()}</div><nav>{links}</nav><div class="aside-bottom"><div class="demo-tag">◌ Ambiente de demonstração</div><div class="identity"><b class="mini-avatar">{h(user["name"][:1].upper())}</b><div><strong>{h(user["name"])}</strong><small>{ROLES[role]}</small></div></div><form method="post" action="/sair"><button class="logout">Sair da conta ↗</button></form></div></aside><div class="shell"><header><span>Seu cuidado, bem organizado.</span><span class="header-right">✧ &nbsp; AgendAí <b>MVP</b></span></header><main>{f"<div class=flash role=status>{h(message)}</div>" if message else ""}{content}</main><footer>AgendAí © {date.today().year} <span>Mais tempo para cuidar de você.</span></footer></div>'
    else:
        shell = content
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{h(title)} · AgendAí</title><link rel="stylesheet" href="/static/style.css"></head><body>{shell}</body></html>'


def login(register=False):
    title = 'Crie sua conta' if register else 'Bom ter você por aqui.'
    form = f'''<div class="login"><section class="login-story"><a class="brand" href="/">agend<span>aí</span><i>✳</i></a><div><div class="eyebrow">CUIDADO QUE CONECTA</div><h1>Sua saúde merece<br>um lugar na agenda.</h1><p>Encontre quem cuida de você.<br>Agende com facilidade. Viva com tranquilidade.</p><div class="story-art"><span>✳</span><div class="floating-card">✓ &nbsp; Cuidado marcado.<small>O próximo passo é se sentir bem.</small></div></div></div><small>Uma conexão mais simples entre pessoas e cuidado.</small></section><section class="login-form"><div class="login-box"><div class="eyebrow">BEM-VINDO À AGENDAÍ</div><h2>{title}</h2><p class="muted">Escolha seu perfil para conhecer a plataforma.</p><form method="post" action="/entrar">{field('Como podemos chamar você?', 'name', value='Ana Silva')}{field('E-mail', 'email', 'email', 'ana@email.com')}{field('Senha demonstrativa', 'password', 'password')}<label>Quero acessar como<select name="role">{''.join(f'<option value="{k}">{v}</option>' for k,v in ROLES.items())}</select></label><button class="primary wide">{'Criar conta e continuar' if register else 'Entrar na plataforma'} <span>→</span></button></form><p class="muted center">{'Já tem uma conta?' if register else 'Primeira vez por aqui?'} <a href="{'/' if register else '/cadastro'}">{'Entrar' if register else 'Criar conta'}</a></p><div class="demo-note">ⓘ Protótipo: a senha não é validada nem armazenada.<br>Os dados são fictícios e reiniciam ao encerrar o servidor.</div></div></section></div>'''
    return page(title, form)


def heading(eyebrow, title, subtitle, extra=''):
    return f'<div class="heading"><div><div class="eyebrow">{eyebrow}</div><h1>{title}</h1><p class="muted">{subtitle}</p></div>{extra}</div>'


def search(user, query):
    term = query.get('q', [''])[0]
    mode = query.get('mode', ['specialty'])[0]
    docs = [d for d in active_doctors() if term.casefold() in d['name' if mode == 'name' else 'specialty'].casefold()]
    content = heading('SEU PRÓXIMO CUIDADO', f'Olá, {h(user["name"].split()[0])} <span class="wave">✳</span>', 'Encontre o profissional certo e reserve um tempo para você.')
    content += '<section class="hero"><div><span class="pill">CUIDAR COMEÇA COM UM ENCONTRO</span><h2>O cuidado que você precisa,<br>no horário que funciona.</h2><p>Profissionais de saúde e uma agenda mais simples.<br>Seu próximo atendimento começa aqui.</p></div><div class="hero-art">✳<span class="art-badge">♡ &nbsp; Sua saúde em primeiro lugar</span></div></section>'
    content += f'<section class="panel search-panel"><form method="get" action="/buscar"><div class="search-top"><h3>Encontre seu profissional</h3><div class="toggle"><label><input type="radio" name="mode" value="specialty" {"checked" if mode != "name" else ""}> Especialidade</label><label><input type="radio" name="mode" value="name" {"checked" if mode == "name" else ""}> Nome do médico</label></div></div><div class="search-line"><input aria-label="Buscar profissional" name="q" value="{h(term)}" placeholder="⌕  Busque por especialidade ou nome..."><button class="primary">Buscar profissional →</button></div></form></section><div class="section-title"><h2>Profissionais disponíveis</h2><span class="muted">{len(docs)} profissionais encontrados</span></div><div class="doctor-grid">'
    for d in docs:
        content += f'<article class="panel doctor-card"><div class="doctor-top"><div class="avatar {d["color"]}">{d["initials"]}</div><span class="available">● Agenda aberta</span></div><h3>{"Dr." if d["id"] == "2" else "Dra."} {d["name"]}</h3><p class="specialty">{d["specialty"]}</p><div class="doctor-meta">✧ Atendimento presencial<br>⌖ São Paulo, SP</div><div class="doctor-price"><span>Consulta a partir de<strong>R$ {d["price"]},00</strong></span><span class="muted">Particular</span></div><a class="outline wide" href="/agendar?doctor={d["id"]}">Ver horários disponíveis <span>↗</span></a></article>'
    return content + ('</div>' if docs else '</div><div class="empty">Nenhum profissional encontrado. Tente outra busca.</div>')


def booking(user, query):
    d = doctor(query.get('doctor', ['1'])[0])
    day = query.get('date', [TOMORROW])[0]
    try:
        if date.fromisoformat(day) < date.today(): day = TOMORROW
    except ValueError:
        day = TOMORROW
    date_field = field('Data da consulta', 'date', 'date', day)
    full = all(occupied(d['id'], day, t) for t in TIMES)
    content = heading('AGENDAR CONSULTA', 'Um horário para cuidar de você.', 'Escolha a data, o horário e conte o motivo do atendimento.', '<a class="text-link" href="/buscar">← Voltar à busca</a>')
    content += f'<div class="booking-layout"><section class="panel profile"><div class="avatar large {d["color"]}">{d["initials"]}</div><h2>{d["name"]}</h2><p class="specialty">{d["specialty"]}</p><hr><p>⌖ Atendimento presencial · São Paulo</p><p>◷ Duração estimada: 50 minutos</p><h3>R$ {d["price"]},00</h3><p class="muted">Consulta particular</p></section><section class="panel"><h2>Escolha seu horário</h2><form method="get" action="/agendar"><input type="hidden" name="doctor" value="{d["id"]}">{date_field}<button class="outline">Consultar disponibilidade</button></form><h3 class="{ "unavailable" if full else "" }">{"Indisponível" if full else "Horários disponíveis"} · {fmt(day)}</h3><form method="post" action="/agendar"><input type="hidden" name="doctor" value="{d["id"]}"><input type="hidden" name="date" value="{day}"><div class="slots">'
    for t in TIMES:
        busy = occupied(d['id'], day, t)
        content += f'<label class="slot {"busy" if busy else ""}"><input type="radio" name="time" value="{t}" required {"disabled" if busy else ""}><span>{t}</span></label>'
    content += '</div>'
    if user['role'] == 'atendente': content += field('Nome do paciente', 'patient') + field('E-mail do paciente', 'patient_email', 'email')
    content += field('Motivo da consulta *', 'reason') + '<label>Descrição <span class="muted">(opcional)</span><textarea name="description" rows="3" placeholder="Se desejar, acrescente informações sobre o atendimento."></textarea></label><button class="primary wide" '+('disabled' if full else '')+'>Confirmar agendamento →</button></form></section></div>'
    return content


def appointments(user, agenda=False):
    items = [a for a in APPOINTMENTS if user['role'] == 'atendente' or (a['doctor'] == user.get('doctor', '1') if agenda else a['owner'] == user['email'])]
    confirmed = [a for a in items if a['status'] == 'Confirmado']
    content = heading('SUA ROTINA, MAIS ORGANIZADA', 'Minha agenda' if agenda else 'Agendamentos', 'Acompanhe os atendimentos e os detalhes de cada consulta.', '<a class="primary" href="/horarios">Configurar horários</a>' if agenda else '<a class="primary" href="/buscar">+ Agendar consulta</a>')
    content += f'<div class="stats"><div class="panel"><span>Consultas confirmadas</span><strong>{len(confirmed):02}</strong></div><div class="panel"><span>Consultas canceladas</span><strong>{len(items)-len(confirmed):02}</strong></div><div class="panel"><span>Próximo atendimento</span><strong class="stat-date">{fmt(min(a["date"] for a in confirmed)) if confirmed else "Sem consultas"}</strong></div></div><section class="panel"><div class="section-title"><h2>{"Atendimentos" if agenda else "Suas consultas"}</h2><span class="muted">Todos os agendamentos</span></div>'
    for a in sorted(items, key=lambda a: (a['date'], a['time'])):
        d = doctor(a['doctor'])
        description = '<p>' + h(a['description']) + '</p>' if a['description'] else ''
        content += f'<article class="appointment"><div class="date-tile"><strong>{a["date"][-2:]}</strong><small>{fmt(a["date"])[3:10]}</small></div><div class="appointment-detail"><h3>{h(a["patient"]) if agenda or user["role"] == "atendente" else d["name"]}</h3><p>{d["specialty"]} · {a["time"]} · {fmt(a["date"])}</p><p><b>Motivo:</b> {h(a["reason"])}</p>{description}</div><div class="appointment-actions"><span class="status {"cancelled" if a["status"] != "Confirmado" else ""}">{a["status"]}</span>'
        if a['status'] == 'Confirmado':
            content += f'<form method="post" action="/cancelar"><input type="hidden" name="id" value="{a["id"]}"><button class="danger" onclick="return confirm(\'Cancelar esta consulta? O paciente receberá um aviso.\')">Cancelar consulta</button></form>'
        content += '</div></article>'
    return content + ('' if items else '<div class="empty">◷<h3>Sua agenda começa aqui.</h3><p>Os agendamentos aparecerão neste espaço.</p></div>') + '</section>'


def availability(user, query):
    day = query.get('date', [TOMORROW])[0]
    try: date.fromisoformat(day)
    except ValueError: day = TOMORROW
    doc = user['doctor']
    content = heading('SUA AGENDA, DO SEU JEITO', 'Disponibilidade', 'Selecione os horários que deseja disponibilizar. Consultas existentes são preservadas.')
    content += f'<section class="panel"><form method="get" action="/horarios">{field("Dia", "date", "date", day)}<button class="outline">Visualizar dia</button></form><h3>{fmt(day)}</h3><form method="post" action="/horarios"><input type="hidden" name="date" value="{day}"><div class="slots">'
    for t in TIMES:
        booked = any(a['doctor'] == doc and a['date'] == day and a['time'] == t and a['status'] == 'Confirmado' for a in APPOINTMENTS)
        content += f'<label class="slot availability"><input type="checkbox" name="available" value="{t}" {"checked" if (doc, day, t) not in BLOCKED else ""} {"disabled" if booked else ""}><span>{t}{" · Agendado" if booked else ""}</span></label>'
    return content + '</div><p class="muted">Marcado = disponível · Desmarcado = bloqueado</p><button class="primary">Salvar disponibilidade</button></form></section>'


class Handler(BaseHTTPRequestHandler):
    def user(self):
        c = SimpleCookie(self.headers.get('Cookie', ''))
        return SESSIONS.get(c['session'].value) if 'session' in c else None

    def send(self, body, status=200, mime='text/html; charset=utf-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

    def redirect(self, url, cookie=None):
        self.send_response(303)
        self.send_header('Location', url)
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        q = parse_qs(urlparse(self.path).query)
        if path == '/static/style.css': return self.send((ROOT / 'static/style.css').read_bytes(), mime='text/css; charset=utf-8')
        user = self.user()
        if not user: return self.send(login(path == '/cadastro'))
        home = {'paciente': 'buscar', 'profissional': 'agenda', 'atendente': 'buscar', 'admin': 'equipe'}[user['role']]
        if path == '/': return self.redirect('/' + home)
        allowed = {'paciente': ['buscar', 'agendar', 'consultas', 'avisos'], 'profissional': ['agenda', 'horarios'], 'atendente': ['buscar', 'agendar', 'consultas'], 'admin': ['equipe']}[user['role']]
        key = path.strip('/')
        if key not in allowed: return self.redirect('/' + home)
        if key == 'buscar': content = search(user, q)
        elif key == 'agendar': content = booking(user, q)
        elif key in ['agenda', 'consultas']: content = appointments(user, key == 'agenda')
        elif key == 'horarios': content = availability(user, q)
        elif key == 'avisos':
            notices = [n for n in NOTICES if n['owner'] == user['email']]
            content = heading('FIQUE POR DENTRO', 'Seus avisos', 'As atualizações dos seus agendamentos ficam aqui.') + '<section class="panel">' + (''.join(f'<article class="notice"><span>◉</span><div><h3>Consulta cancelada</h3><p>{h(n["text"])}</p></div></article>' for n in reversed(notices)) or '<div class="empty">Tudo em dia.<p>Você ainda não tem avisos de cancelamento.</p></div>') + '</section>'
        else:
            content = heading('ADMINISTRAÇÃO', 'Funcionários', 'Consulte a equipe e encerre vínculos de funcionários.') + '<section class="panel">'
            for s in STAFF:
                content += f'<article class="appointment"><b class="mini-avatar">{s["name"][0]}</b><div class="appointment-detail"><h3>{s["name"]}</h3><p>{s["role"]}</p></div><span class="status {"cancelled" if not s["active"] else ""}">{"Ativo" if s["active"] else "Desligado"}</span>'
                if s['active']: content += f'<form method="post" action="/demitir"><input type="hidden" name="id" value="{s["id"]}"><button class="danger" onclick="return confirm(\'Confirmar o desligamento deste funcionário?\')">Demitir funcionário</button></form>'
                content += '</article>'
            content += '</section>'
        message = user.pop('message', '')
        self.send(page(ROLES[user['role']], content, user, 'buscar' if key == 'agendar' else key, message))

    def do_POST(self):
        with LOCK:
            try: self.post()
            except (ValueError, KeyError): self.send(page('Dados inválidos', '<main><h1>Confira os dados informados.</h1><a href="/">Voltar à plataforma</a></main>'), 400)

    def post(self):
        path = urlparse(self.path).path
        data = parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode(), keep_blank_values=True)
        get = lambda k: data.get(k, [''])[0].strip()
        if path == '/entrar':
            if get('role') not in ROLES or not get('name') or not get('email'): raise ValueError()
            token = secrets.token_urlsafe(24)
            SESSIONS[token] = {'name': get('name'), 'email': get('email').lower(), 'role': get('role'), 'doctor': '1'}
            return self.redirect('/', f'session={token}; HttpOnly; SameSite=Lax; Path=/')
        user = self.user()
        if not user: return self.redirect('/')
        if path == '/sair':
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            if 'session' in cookie: SESSIONS.pop(cookie['session'].value, None)
            return self.redirect('/', 'session=; Max-Age=0; Path=/')
        if path == '/agendar' and user['role'] in ['paciente', 'atendente']:
            doc, day, hour = get('doctor'), get('date'), get('time')
            if doc not in [d['id'] for d in active_doctors()] or hour not in TIMES or date.fromisoformat(day) < date.today() or not get('reason'): raise ValueError()
            if occupied(doc, day, hour):
                user['message'] = 'Este horário acabou de ficar indisponível. Escolha outro horário.'
                return self.redirect(f'/agendar?doctor={doc}&date={day}')
            patient = get('patient') if user['role'] == 'atendente' else user['name']
            owner = get('patient_email').lower() if user['role'] == 'atendente' else user['email']
            if not patient or not owner: raise ValueError()
            APPOINTMENTS.append({'id': secrets.token_hex(8), 'doctor': doc, 'patient': patient, 'owner': owner, 'date': day, 'time': hour, 'reason': get('reason'), 'description': get('description'), 'status': 'Confirmado'})
            user['message'] = 'Tudo certo! Sua consulta foi agendada.'
            return self.redirect('/consultas')
        if path == '/cancelar' and user['role'] != 'admin':
            a = next((a for a in APPOINTMENTS if a['id'] == get('id')), None)
            if not a or not (user['role'] == 'atendente' or user['role'] == 'profissional' and a['doctor'] == user['doctor'] or user['role'] == 'paciente' and a['owner'] == user['email']): return self.send('Acesso não permitido', 403)
            if a['status'] == 'Confirmado':
                a['status'] = 'Cancelado'
                NOTICES.append({'owner': a['owner'], 'text': f'Sua consulta com {doctor(a["doctor"])["name"]}, em {fmt(a["date"])} às {a["time"]}, foi cancelada. Você pode escolher um novo horário.'})
            user['message'] = 'Consulta cancelada. Um aviso foi enviado à área do paciente.'
            return self.redirect('/agenda' if user['role'] == 'profissional' else '/consultas')
        if path == '/horarios' and user['role'] == 'profissional':
            day = get('date'); date.fromisoformat(day)
            for t in TIMES:
                key = (user['doctor'], day, t)
                booked = any(a['doctor'] == user['doctor'] and a['date'] == day and a['time'] == t and a['status'] == 'Confirmado' for a in APPOINTMENTS)
                if t in data.get('available', []) or booked: BLOCKED.discard(key)
                else: BLOCKED.add(key)
            user['message'] = 'Disponibilidade atualizada.'
            return self.redirect(f'/horarios?date={day}')
        if path == '/demitir' and user['role'] == 'admin':
            s = next(s for s in STAFF if s['id'] == get('id'))
            s['active'] = False
            user['message'] = f'{s["name"]}: desligamento registrado na demonstração.'
            return self.redirect('/equipe')
        self.send('Acesso não permitido', 403)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Iniciar o MVP AgendAí')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        raise SystemExit(f'Não foi possível iniciar na porta {args.port}: {exc}. Tente python app.py --port 8766')
    print(f'AgendAí disponível em http://127.0.0.1:{args.port} — Ctrl+C para encerrar.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
