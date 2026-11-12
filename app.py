"""AgendAí — MVP local, feito com a biblioteca padrão do Python."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from http.cookies import SimpleCookie
from datetime import date, timedelta
from html import escape
from pathlib import Path
from threading import RLock
import secrets
import calendar

ROOT = Path(__file__).parent
LOCK = RLock()
SESSIONS = {}
ROLES = {'paciente': 'Paciente', 'profissional': 'Profissional', 'atendente': 'Atendente', 'admin': 'Admin'}
DOCTORS = [
    {'id': '1', 'name': 'Marina Costa', 'specialty': 'Cardiologia', 'initials': 'MC', 'color': 'rose', 'photo': 'marina.png', 'price': '280'},
    {'id': '2', 'name': 'Rafael Mendes', 'specialty': 'Clínica geral', 'initials': 'RM', 'color': 'blue', 'photo': 'rafael.png', 'price': '180'},
    {'id': '3', 'name': 'Beatriz Almeida', 'specialty': 'Dermatologia', 'initials': 'BA', 'color': 'sand', 'photo': 'beatriz.png', 'price': '250'},
]
SPECIALTIES = ['Alergologia', 'Cardiologia', 'Clínica geral', 'Dermatologia', 'Endocrinologia', 'Fisioterapia', 'Ginecologia', 'Neurologia', 'Nutrição', 'Oftalmologia', 'Ortopedia', 'Otorrinolaringologia', 'Pediatria', 'Psicologia', 'Psiquiatria', 'Urologia']
TIMES = [f'{hour:02d}:00' for hour in range(8, 19)]
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
APPOINTMENTS = [{'id': 'demo', 'doctor': '1', 'patient': 'Ana Silva', 'owner': 'ana@email.com', 'date': TOMORROW, 'time': '09:00', 'reason': 'Consulta de rotina', 'description': '', 'status': 'Confirmado'}]
NOTICES = []
STAFF = [{'id': '1', 'name': 'Marina Costa', 'role': 'Profissional', 'active': True}, {'id': '2', 'name': 'Rafael Mendes', 'role': 'Profissional', 'active': True}, {'id': '3', 'name': 'Beatriz Almeida', 'role': 'Profissional', 'active': True}, {'id': '4', 'name': 'Lucas Oliveira', 'role': 'Atendente', 'active': True}]
BLOCKED = set()
ROUTINES = {}
DAY_HOURS = {}


def h(value):
    return escape(str(value), quote=True)


def doctor(ident):
    return next((d for d in DOCTORS if d['id'] == ident), DOCTORS[0])


def active_doctors():
    return [d for d in DOCTORS if any(s['id'] == d['id'] and s['active'] for s in STAFF)]


def occupied(doc, day, hour):
    return hour not in DAY_HOURS.get((doc, day), ROUTINES.get(doc, TIMES)) or any(a['doctor'] == doc and a['date'] == day and a['time'] == hour and a['status'] == 'Confirmado' for a in APPOINTMENTS)


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
    specialty_options = ''.join(f'<option value="{h(s)}">' for s in SPECIALTIES)
    specialty_text = ' · '.join(SPECIALTIES)
    content = heading('SEU PRÓXIMO CUIDADO', f'Olá, {h(user["name"].split()[0])} <span class="wave">✳</span>', 'Encontre o profissional certo e reserve um tempo para você.')
    content += '<section class="hero"><div><span class="pill">CUIDAR COMEÇA COM UM ENCONTRO</span><h2>O cuidado que você precisa,<br>no horário que funciona.</h2><p>Profissionais de saúde e uma agenda mais simples.<br>Seu próximo atendimento começa aqui.</p></div><div class="hero-art">✳<span class="art-badge">♡ &nbsp; Sua saúde em primeiro lugar</span></div></section>'
    content += f'<section class="panel search-panel"><form method="get" action="/buscar"><div class="search-top"><h3>Encontre seu profissional</h3><div class="toggle"><label><input type="radio" name="mode" value="specialty" {"checked" if mode != "name" else ""}> Especialidade</label><label><input type="radio" name="mode" value="name" {"checked" if mode == "name" else ""}> Nome do médico</label></div></div><div class="search-line"><input list="specialties" aria-label="Buscar profissional" name="q" value="{h(term)}" placeholder="⌕  Busque por especialidade ou nome..."><datalist id="specialties">{specialty_options}</datalist><button class="primary">Buscar profissional →</button></div><div class="specialty-list"><span>Especialidades:</span> {specialty_text}</div></form></section><div class="section-title"><h2>Profissionais disponíveis</h2><span class="muted">{len(docs)} profissionais encontrados</span></div><div class="doctor-grid">'
    for d in docs:
        content += f'<article class="panel doctor-card"><div class="doctor-top"><img class="doctor-photo" src="/static/doctors/{d["photo"]}" alt="Foto de {h(d["name"])}"><span class="available">● Agenda aberta</span></div><h3>{"Dr." if d["id"] == "2" else "Dra."} {d["name"]}</h3><p class="specialty">{d["specialty"]}</p><div class="doctor-meta">✧ Atendimento presencial<br>⌖ São Paulo, SP</div><div class="doctor-price"><span>Consulta a partir de<strong>R$ {d["price"]},00</strong></span><span class="muted">Particular</span></div><a class="outline wide" href="/agendar?doctor={d["id"]}">Escolher horário <span>→</span></a></article>'
    return content + ('</div>' if docs else '</div><div class="empty">Nenhum profissional encontrado. Tente outra busca.</div>')


def booking(user, query):
    d = doctor(query.get('doctor', ['1'])[0])
    day = query.get('date', [TOMORROW])[0]
    try:
        if date.fromisoformat(day) < date.today(): day = TOMORROW
    except ValueError:
        day = TOMORROW
    date_field = field('Data da consulta', 'date', 'date', day)
    date_field = date_field.replace('>', ' onchange="this.form.submit()">', 1)
    full = all(occupied(d['id'], day, t) for t in TIMES)
    content = heading('AGENDAR CONSULTA', 'Um horário para cuidar de você.', 'Escolha a data, o horário e conte o motivo do atendimento.', '<a class="text-link" href="/buscar">← Voltar à busca</a>')
    content += f'<div class="booking-layout"><section class="panel profile"><img class="profile-photo" src="/static/doctors/{d["photo"]}" alt="Foto de {h(d["name"])}"><h2>{d["name"]}</h2><p class="specialty">{d["specialty"]}</p><hr><p>⌖ Atendimento presencial · São Paulo</p><p>◷ Duração estimada: 50 minutos</p><h3>R$ {d["price"]},00</h3><p class="muted">Consulta particular</p></section><section class="panel"><div class="schedule-head"><div><h2>Escolha um horário</h2><p class="muted">Os horários livres aparecem abaixo.</p></div></div><form method="get" action="/agendar"><input type="hidden" name="doctor" value="{d["id"]}">{date_field}</form><h3 class="{ "unavailable" if full else "" }">{"Indisponível" if full else "Horários disponíveis"} · {fmt(day)}</h3><form method="post" action="/agendar"><input type="hidden" name="doctor" value="{d["id"]}"><input type="hidden" name="date" value="{day}"><div class="slots">'
    for t in TIMES:
        busy = occupied(d['id'], day, t)
        booked = any(a['doctor'] == d['id'] and a['date'] == day and a['time'] == t and a['status'] == 'Confirmado' for a in APPOINTMENTS)
        state = 'reserved' if booked else 'blocked' if busy else 'free'
        caption = 'Agendado' if booked else 'Não atende' if busy else 'Disponível'
        content += f'<label class="slot {state}"><input type="radio" name="time" value="{t}" required {"disabled" if busy else ""}><span>{t}<small>{caption}</small></span></label>'
    content += '</div><p class="slot-legend">🟢 Disponível · 🟡 Médico não atende · 🔴 Já agendado</p>'
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
        display_name = h(a["patient"]) if agenda or user["role"] == "atendente" else d["name"]
        content += f'<article class="appointment"><div class="date-tile"><strong>{a["date"][-2:]}</strong><small>{fmt(a["date"])[3:10]}</small></div><img class="appointment-photo" src="/static/doctors/{d["photo"]}" alt=""><div class="appointment-detail"><h3>{display_name}</h3><p>{d["specialty"]} · <b>{a["time"]}</b> · {fmt(a["date"])}</p><p><b>Motivo:</b> {h(a["reason"])}</p>{description}</div><div class="appointment-actions"><span class="status {"cancelled" if a["status"] != "Confirmado" else ""}">{a["status"]}</span>'
        if a['status'] == 'Confirmado':
            content += f'<form method="post" action="/cancelar"><input type="hidden" name="id" value="{a["id"]}"><button class="danger" onclick="return confirm(\'Cancelar esta consulta? O paciente receberá um aviso.\')">Cancelar consulta</button></form>'
        content += '</div></article>'
    return content + ('' if items else '<div class="empty">◷<h3>Sua agenda começa aqui.</h3><p>Os agendamentos aparecerão neste espaço.</p></div>') + '</section>'


def professional_calendar(user, query):
    try:
        selected = date.fromisoformat(query.get('date', [date.today().isoformat()])[0])
    except ValueError:
        selected = date.today()
    month = selected.replace(day=1)
    previous = month - timedelta(days=1)
    following = (month + timedelta(days=32)).replace(day=1)
    months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    items = [a for a in APPOINTMENTS if a['doctor'] == user['doctor'] and a['status'] == 'Confirmado']
    content = heading('SUA ROTINA, MAIS ORGANIZADA', 'Minha agenda', 'Selecione um dia no calendário para acompanhar seus atendimentos.', '<a class="primary" href="/horarios">Configurar horários</a>')
    content += f'<div class="calendar-layout"><section class="panel"><div class="calendar-heading"><a class="outline" aria-label="Mês anterior" href="/agenda?date={previous.isoformat()}">←</a><h2>{months[month.month-1]} {month.year}</h2><a class="outline" aria-label="Próximo mês" href="/agenda?date={following.isoformat()}">→</a></div><div class="calendar-grid">'
    content += ''.join(f'<b class="weekday">{name}</b>' for name in ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'])
    for week in calendar.Calendar().monthdatescalendar(month.year, month.month):
        for day in week:
            count = sum(a['date'] == day.isoformat() for a in items)
            classes = 'calendar-day' + (' outside' if day.month != month.month else '') + (' has-appointments' if count else '') + (' chosen' if day == selected else '') + (' today' if day == date.today() else '')
            marker = f'<small>{count} consulta'+('s' if count != 1 else '')+'</small>' if count else '<small>Sem consultas</small>'
            content += f'<a class="{classes}" href="/agenda?date={day.isoformat()}" aria-label="{fmt(day.isoformat())}, {count} consultas"><strong>{day.day}</strong>{marker}</a>'
    content += '</div><p class="muted">● Dias em verde têm consultas confirmadas. O contorno indica hoje.</p></section>'
    day_items = [a for a in items if a['date'] == selected.isoformat()]
    content += f'<section class="panel day-schedule"><div class="eyebrow">ATENDIMENTOS DO DIA</div><h2>{fmt(selected.isoformat())}</h2><p class="muted">{len(day_items)} consulta(s) confirmada(s)</p>'
    for hour in TIMES:
        appointment = next((a for a in day_items if a['time'] == hour), None)
        if appointment:
            content += f'<article class="agenda-hour reserved"><strong>{hour}</strong><div><h3>{h(appointment["patient"])}</h3><p>{h(appointment["reason"])}</p>'
            if appointment['description']:
                content += f'<p>{h(appointment["description"])}</p>'
            content += f'<form method="post" action="/cancelar"><input type="hidden" name="id" value="{appointment["id"]}"><button class="danger" onclick="return confirm(\'Cancelar esta consulta?\')">Cancelar consulta</button></form></div></article>'
        else:
            free = not occupied(user['doctor'], selected.isoformat(), hour)
            content += f'<article class="agenda-hour {"free" if free else "blocked"}"><strong>{hour}</strong><span>{"Disponível" if free else "Não atende"}</span></article>'
    return content + '</section></div>'


def availability(user, query):
    day = query.get('date', [TOMORROW])[0]
    try: date.fromisoformat(day)
    except ValueError: day = TOMORROW
    doc = user['doctor']
    routine = query.get('scope', ['day'])[0] == 'routine'
    scope = 'routine' if routine else 'day'
    selected = ROUTINES.get(doc, TIMES) if routine else DAY_HOURS.get((doc, day), ROUTINES.get(doc, TIMES))
    content = heading('SUA AGENDA, DO SEU JEITO', 'Disponibilidade', 'Selecione os horários que deseja disponibilizar. Consultas existentes são preservadas.')
    content += f'<section class="panel"><div class="search-line"><a class="outline" href="/horarios?scope=routine">Rotina para todos os dias</a><a class="outline" href="/horarios?date={day}">Ajustar um dia específico</a></div>'
    if not routine:
        content += f'<form method="get" action="/horarios"><label>Dia<input type="date" name="date" value="{day}" required onchange="this.form.submit()"></label></form>'
    title = 'Carga horária diária' if routine else 'Horários de atendimento'
    explanation = 'Estes horários se repetem todos os dias. Ajustes de datas específicas têm prioridade. Consultas já marcadas são mantidas.' if routine else 'Esta alteração vale apenas para a data escolhida. Nos demais dias, vale a rotina do médico.'
    content += f'<h3>{title}</h3><p class="muted">{explanation}</p><form method="post" action="/horarios"><input type="hidden" name="scope" value="{scope}"><input type="hidden" name="date" value="{day}"><div class="slots">'
    for t in TIMES:
        booked = not routine and any(a['doctor'] == doc and a['date'] == day and a['time'] == t and a['status'] == 'Confirmado' for a in APPOINTMENTS)
        state = 'reserved' if booked else ''
        content += f'<label class="slot availability {state}"><input type="checkbox" name="available" value="{t}" {"checked" if t in selected else ""} {"disabled" if booked else ""}><span>{t}<small>{"Agendado" if booked else ""}</small></span></label>'
    return content + '</div><p class="slot-legend">🟢 Disponível · 🟡 Médico não atende · 🔴 Já agendado</p><p class="muted">Clique nos horários para alternar sua disponibilidade e salve. Consultas agendadas não podem ser alteradas aqui.</p><button class="primary">Salvar disponibilidade</button></form></section>'


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
        if path.startswith('/static/'):
            asset = ROOT / path.lstrip('/')
            if asset.exists() and asset.is_file():
                mime = 'text/css; charset=utf-8' if asset.suffix == '.css' else 'image/png'
                return self.send(asset.read_bytes(), mime=mime)
            return self.send('Not found', 404)
        user = self.user()
        if not user: return self.send(login(path == '/cadastro'))
        home = {'paciente': 'buscar', 'profissional': 'agenda', 'atendente': 'buscar', 'admin': 'equipe'}[user['role']]
        if path == '/': return self.redirect('/' + home)
        allowed = {'paciente': ['buscar', 'agendar', 'consultas', 'avisos'], 'profissional': ['agenda', 'horarios'], 'atendente': ['buscar', 'agendar', 'consultas'], 'admin': ['equipe']}[user['role']]
        key = path.strip('/')
        if key not in allowed: return self.redirect('/' + home)
        if key == 'buscar': content = search(user, q)
        elif key == 'agendar': content = booking(user, q)
        elif key == 'agenda': content = professional_calendar(user, q)
        elif key == 'consultas': content = appointments(user)
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
            selected = set(data.get('available', [])) & set(TIMES)
            if get('scope') == 'routine':
                ROUTINES[user['doctor']] = selected
                user['message'] = 'Carga horária salva para todos os dias. Exceções de datas específicas e consultas existentes foram mantidas.'
                return self.redirect('/horarios?scope=routine')
            selected.update(a['time'] for a in APPOINTMENTS if a['doctor'] == user['doctor'] and a['date'] == day and a['status'] == 'Confirmado')
            DAY_HOURS[(user['doctor'], day)] = selected
            user['message'] = 'Disponibilidade atualizada para este dia.'
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
