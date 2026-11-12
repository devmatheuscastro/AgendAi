"""AgendAí — aplicação web local com persistência PostgreSQL."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from http.cookies import SimpleCookie
from datetime import date, timedelta
from html import escape
from pathlib import Path
from threading import RLock
import secrets
import calendar
import backend
import re
import logging

ROOT = Path(__file__).parent
LOCK = RLock()
SESSIONS = {}
ROLES = {'paciente': 'Paciente', 'profissional': 'Profissional', 'atendente': 'Atendente', 'admin': 'Admin'}
DOCTORS, STAFF, APPOINTMENTS = [], [], []
ROUTINES, DAY_HOURS = {}, {}
SPECIALTIES = ['Alergologia', 'Cardiologia', 'Clínica geral', 'Dermatologia', 'Endocrinologia', 'Fisioterapia', 'Ginecologia', 'Neurologia', 'Nutrição', 'Oftalmologia', 'Ortopedia', 'Otorrinolaringologia', 'Pediatria', 'Psicologia', 'Psiquiatria', 'Urologia']
TIMES = backend.HOURS
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def h(value):
    return escape(str(value), quote=True)


def doctor(ident):
    found = next((d for d in DOCTORS if d['id'] == ident), None)
    if not found:
        raise backend.DomainError('Médico não encontrado.', 404)
    return found


def refresh_data():
    global DOCTORS, STAFF, APPOINTMENTS, ROUTINES, DAY_HOURS
    DOCTORS, STAFF, APPOINTMENTS, ROUTINES, DAY_HOURS = backend.snapshot()
    for s in STAFF:
        s['role'] = ROLES[s['role']]


def active_doctors():
    return [d for d in DOCTORS if any(s['id'] == d['id'] and s['active'] for s in STAFF)]


def occupied(doc, day, hour):
    return hour not in DAY_HOURS.get((doc, day), ROUTINES.get(doc, TIMES)) or any(a['doctor'] == doc and a['date'] == day and a['time'] == hour and a['status'] in ['Confirmado', 'Realizado'] for a in APPOINTMENTS)


def fmt(day):
    return date.fromisoformat(day).strftime('%d/%m/%Y')


def field(label, name, kind='text', value='', required=True):
    return f'<label>{label}<input type="{kind}" name="{name}" value="{h(value)}" {"required" if required else ""}></label>'


def page(title, content, user=None, current='', message=''):
    if user:
        role = user['role']
        menus = {'paciente': [('buscar', '⌕', 'Encontrar profissional'), ('consultas', '▦', 'Meus agendamentos')], 'profissional': [('agenda', '▦', 'Minha agenda'), ('horarios', '◷', 'Disponibilidade')], 'atendente': [('buscar', '⌕', 'Agendar consulta'), ('consultas', '▦', 'Agendamentos')], 'admin': [('equipe', '♧', 'Funcionários')]}
        menus['atendente'].append(('horarios', '◷', 'Horários dos médicos'))
        menus['profissional'].append(('historico', '▤', 'Histórico de consultas'))
        menus[role].append(('senha', '⚙', 'Alterar senha'))
        links = ''.join(f'<a class="nav {"selected" if key == current else ""}" href="/{key}"><span>{icon}</span>{label}</a>' for key, icon, label in menus[role])
        shell = f'<aside><a class="brand" href="/">agend<span>aí</span><i>✳</i></a><div class="workspace">ESPAÇO DO {ROLES[role].upper()}</div><nav>{links}</nav><div class="aside-bottom"><div class="demo-tag">◌ Ambiente de demonstração</div><div class="identity"><b class="mini-avatar">{h(user["name"][:1].upper())}</b><div><strong>{h(user["name"])}</strong><small>{ROLES[role]}</small></div></div><form method="post" action="/sair"><button class="logout">Sair da conta ↗</button></form></div></aside><div class="shell"><header><span>Seu cuidado, bem organizado.</span><span class="header-right">✧ &nbsp; AgendAí <b>MVP</b></span></header><main>{f"<div class=flash role=status>{h(message)}</div>" if message else ""}{content}</main><footer>AgendAí © {date.today().year} <span>Mais tempo para cuidar de você.</span></footer></div>'
    else:
        shell = content
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{h(title)} · AgendAí</title><link rel="stylesheet" href="/static/style.css"></head><body>{shell}</body></html>'


def login(register=False):
    title = 'Crie sua conta' if register else 'Bom ter você por aqui.'
    action = '/cadastrar-paciente' if register else '/entrar'
    name_field = field('Nome completo', 'name') if register else ''
    button = 'Criar conta' if register else 'Entrar na plataforma'
    link = '<a href="/">Já tem conta? Entrar</a>' if register else '<a href="/cadastro">Criar conta de paciente</a>'
    email_field = field('E-mail', 'email', 'email')
    password_field = field('Senha (mínimo 8 caracteres)' if register else 'Senha', 'password', 'password')
    form = f'''<div class="login"><section class="login-story"><a class="brand" href="/">agend<span>aí</span><i>✳</i></a><div><div class="eyebrow">CUIDADO QUE CONECTA</div><h1>Sua saúde merece<br>um lugar na agenda.</h1><p>Encontre quem cuida de você.<br>Agende com facilidade.</p><div class="story-art"><span>✳</span><div class="floating-card">✓ Cuidado marcado.<small>O próximo passo é se sentir bem.</small></div></div></div><small>Uma conexão mais simples entre pessoas e cuidado.</small></section><section class="login-form"><div class="login-box"><div class="eyebrow">BEM-VINDO À AGENDAÍ</div><h2>{title}</h2><p class="muted">Entre com seus dados para continuar.</p><form method="post" action="{action}">{name_field}{email_field}{password_field}<button class="primary wide">{button} →</button></form><p class="center">{link}</p></div></section></div>'''
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
        content += f'<article class="panel doctor-card"><div class="doctor-top"><img class="doctor-photo" src="/static/doctors/{d["photo"]}" alt="Foto de {h(d["name"])}"><span class="available">● Agenda aberta</span></div><h3>{"Dr." if d["id"] == "2" else "Dra."} {h(d["name"])}</h3><p class="specialty">{h(d["specialty"])}</p><div class="doctor-meta">✧ Atendimento presencial<br>⌖ São Paulo, SP</div><div class="doctor-price"><span>Consulta a partir de<strong>R$ {d["price"]},00</strong></span><span class="muted">Particular</span></div><a class="outline wide" href="/agendar?doctor={d["id"]}">Escolher horário <span>→</span></a></article>'
    return content + ('</div>' if docs else '</div><div class="empty">Nenhum profissional encontrado. Tente outra busca.</div>')


def booking(user, query):
    d = doctor(query.get('doctor', ['1'])[0])
    if not d['active']:
        raise backend.DomainError('Profissional indisponível.', 404)
    day = query.get('date', [TOMORROW])[0]
    try:
        if date.fromisoformat(day) < date.today(): day = TOMORROW
    except ValueError:
        day = TOMORROW
    date_field = field('Data da consulta', 'date', 'date', day)
    date_field = date_field.replace('<input ', '<input onchange="this.form.submit()" ', 1)
    full = all(occupied(d['id'], day, t) for t in TIMES)
    content = heading('AGENDAR CONSULTA', 'Um horário para cuidar de você.', 'Escolha a data, o horário e conte o motivo do atendimento.', '<a class="text-link" href="/buscar">← Voltar à busca</a>')
    content += f'<div class="booking-layout"><section class="panel profile"><img class="profile-photo" src="/static/doctors/{d["photo"]}" alt="Foto de {h(d["name"])}"><h2>{h(d["name"])}</h2><p class="specialty">{h(d["specialty"])}</p><hr><p>⌖ Atendimento presencial · São Paulo</p><p>◷ Duração estimada: 50 minutos</p><h3>R$ {d["price"]},00</h3><p class="muted">Consulta particular</p></section><section class="panel"><div class="schedule-head"><div><h2>Escolha um horário</h2><p class="muted">Os horários livres aparecem abaixo.</p></div></div><form method="get" action="/agendar"><input type="hidden" name="doctor" value="{d["id"]}">{date_field}</form><h3 class="{ "unavailable" if full else "" }">{"Indisponível" if full else "Horários disponíveis"} · {fmt(day)}</h3><form method="post" action="/agendar"><input type="hidden" name="doctor" value="{d["id"]}"><input type="hidden" name="date" value="{day}"><div class="slots">'
    for t in TIMES:
        busy = occupied(d['id'], day, t)
        booked = any(a['doctor'] == d['id'] and a['date'] == day and a['time'] == t and a['status'] == 'Confirmado' for a in APPOINTMENTS)
        state = 'reserved' if booked else 'blocked' if busy else 'free'
        caption = 'Agendado' if booked else 'Não atende' if busy else 'Disponível'
        content += f'<label class="slot {state}"><input type="radio" name="time" value="{t}" required {"disabled" if busy else ""}><span>{t}<small>{caption}</small></span></label>'
    content += '</div><p class="slot-legend">🟢 Disponível · 🟡 Médico não atende · 🔴 Já agendado</p>'
    if user['role'] == 'atendente': content += '<h3>Para quem é a consulta?</h3><p class="muted">Informe os dados do paciente. O agendamento ficará vinculado ao e-mail dele.</p>' + field('Nome completo do paciente', 'patient') + field('E-mail do paciente', 'patient_email', 'email')
    if user['role'] == 'atendente': content += field('Senha inicial (apenas para paciente novo, mínimo 8 caracteres)', 'patient_password', 'password', required=False)
    content += field('Motivo da consulta *', 'reason') + '<label>Descrição <span class="muted">(opcional)</span><textarea name="description" rows="3" placeholder="Se desejar, acrescente informações sobre o atendimento."></textarea></label><button class="primary wide" '+('disabled' if full else '')+'>Confirmar agendamento →</button></form></section></div>'
    return content


def appointments(user, agenda=False):
    items = [a for a in APPOINTMENTS if user['role'] == 'atendente' or (a['doctor'] == user.get('doctor', '1') if agenda else a['owner'] == user['email'])]
    confirmed = [a for a in items if a['status'] == 'Confirmado']
    upcoming = [a for a in confirmed if a['date'] >= date.today().isoformat()]
    content = heading('SUA ROTINA, MAIS ORGANIZADA', 'Minha agenda' if agenda else 'Agendamentos', 'Acompanhe os atendimentos e os detalhes de cada consulta.', '<a class="primary" href="/horarios">Configurar horários</a>' if agenda else '<a class="primary" href="/buscar">+ Agendar consulta</a>')
    content += f'<div class="stats"><div class="panel"><span>Consultas confirmadas</span><strong>{len(confirmed):02}</strong></div><div class="panel"><span>Consultas canceladas</span><strong>{sum(a["status"] == "Cancelado" for a in items):02}</strong></div><div class="panel"><span>Próximo atendimento</span><strong class="stat-date">{fmt(min(a["date"] for a in upcoming)) if upcoming else "Sem consultas"}</strong></div></div><section class="panel"><div class="section-title"><h2>{"Atendimentos" if agenda else "Suas consultas"}</h2><span class="muted">Todos os agendamentos</span></div>'
    for a in sorted(items, key=lambda a: (a['date'], a['time'])):
        d = doctor(a['doctor'])
        description = '<p>' + h(a['description']) + '</p>' if a['description'] else ''
        display_name = h(a["patient"]) if agenda or user["role"] == "atendente" else h(d["name"])
        content += f'<article class="appointment"><div class="date-tile"><strong>{a["date"][-2:]}</strong><small>{fmt(a["date"])[3:10]}</small></div><img class="appointment-photo" src="/static/doctors/{d["photo"]}" alt=""><div class="appointment-detail"><h3>{display_name}</h3><p>{h(d["specialty"])} · <b>{a["time"]}</b> · {fmt(a["date"])}</p><p><b>Motivo:</b> {h(a["reason"])}</p>{description}</div><div class="appointment-actions"><span class="status {"cancelled" if a["status"] != "Confirmado" else ""}">{a["status"]}</span>'
        if a['status'] == 'Confirmado':
            content += f'<form method="post" action="/cancelar"><input type="hidden" name="id" value="{a["id"]}"><button class="danger" onclick="return confirm(\'Cancelar esta consulta?\')">Cancelar consulta</button></form>'
        content += '</div></article>'
    return content + ('' if items else '<div class="empty">◷<h3>Sua agenda começa aqui.</h3><p>Os agendamentos aparecerão neste espaço.</p></div>') + '</section>'


def staff_doctors(query, target):
    term = query.get('q', [''])[0].strip()
    docs = [d for d in active_doctors() if term.casefold() in (d['name'] + ' ' + d['specialty']).casefold()]
    title = 'Horários dos médicos' if target == 'horarios' else 'Agendamentos'
    content = heading('ÁREA DO ATENDENTE', title, 'Selecione o médico para continuar.')
    content += f'<section class="panel"><form method="get" action="/{target}"><div class="search-line"><input name="q" aria-label="Nome ou especialidade" value="{h(term)}" placeholder="Pesquisar por nome ou especialidade"><button class="primary">Pesquisar</button></div></form></section><div class="doctor-grid" style="margin-top:24px">'
    for d in docs:
        action = 'Configurar horários' if target == 'horarios' else 'Ver agenda'
        content += f'<a class="panel doctor-card" href="/{target}?doctor={d["id"]}"><img class="doctor-photo" src="/static/doctors/{d["photo"]}" alt="Foto de {h(d["name"])}"><h3>{h(d["name"])}</h3><p class="specialty">{h(d["specialty"])}</p><span class="primary" style="margin-top:24px">{action} →</span></a>'
    return content + '</div>' + ('' if docs else '<p class="empty">Nenhum médico encontrado.</p>')


def staff_view(user, query, target):
    doc = query.get('doctor', [''])[0]
    if doc not in [d['id'] for d in active_doctors()]:
        return staff_doctors(query, target)
    context = dict(user, doctor=doc)
    if target == 'horarios':
        content = availability(context, query)
    else:
        content = professional_calendar(context, query)
        content = content.replace('/agenda?date=', f'/consultas?doctor={doc}&date=')
        content = content.replace('href="/horarios"', f'href="/horarios?doctor={doc}"')
        content = content.replace('action="/cancelar">', f'action="/cancelar"><input type="hidden" name="doctor" value="{doc}">')
    return f'<a class="text-link" href="/{target}">← Voltar aos médicos</a><h2>{h(doctor(doc)["name"])} · {h(doctor(doc)["specialty"])}</h2>' + content


def professional_calendar(user, query):
    try:
        selected = date.fromisoformat(query.get('date', [date.today().isoformat()])[0])
    except ValueError:
        selected = date.today()
    month = selected.replace(day=1)
    previous = month - timedelta(days=1)
    following = (month + timedelta(days=32)).replace(day=1)
    months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    items = [a for a in APPOINTMENTS if a['doctor'] == user['doctor'] and a['status'] in ['Confirmado', 'Realizado']]
    content = heading('SUA ROTINA, MAIS ORGANIZADA', 'Minha agenda', 'Selecione um dia no calendário para acompanhar seus atendimentos.', '<a class="primary" href="/horarios">Configurar horários</a>')
    content += f'<div class="calendar-layout"><section class="panel"><div class="calendar-heading"><a class="outline" aria-label="Mês anterior" href="/agenda?date={previous.isoformat()}">←</a><h2>{months[month.month-1]} {month.year}</h2><a class="outline" aria-label="Próximo mês" href="/agenda?date={following.isoformat()}">→</a></div><div class="calendar-grid">'
    content += ''.join(f'<b class="weekday">{name}</b>' for name in ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'])
    for week in calendar.Calendar().monthdatescalendar(month.year, month.month):
        for day in week:
            count = sum(a['date'] == day.isoformat() for a in items)
            classes = 'calendar-day' + (' outside' if day.month != month.month else '') + (' has-appointments' if count else '') + (' chosen' if day == selected else '') + (' today' if day == date.today() else '')
            marker = f'<small>{count} consulta'+('s' if count != 1 else '')+'</small>' if count else '<small>Sem consultas</small>'
            content += f'<a class="{classes}" href="/agenda?date={day.isoformat()}" aria-label="{fmt(day.isoformat())}, {count} consultas"><strong>{day.day}</strong>{marker}</a>'
    content += '</div><p class="muted">● Dias em verde têm consultas confirmadas ou realizadas. O contorno indica hoje.</p></section>'
    day_items = [a for a in items if a['date'] == selected.isoformat()]
    content += f'<section class="panel day-schedule"><div class="eyebrow">ATENDIMENTOS DO DIA</div><h2>{fmt(selected.isoformat())}</h2><p class="muted">{len(day_items)} atendimento(s)</p>'
    for hour in TIMES:
        appointment = next((a for a in day_items if a['time'] == hour), None)
        if appointment:
            content += f'<article class="agenda-hour reserved"><strong>{hour}</strong><div><h3>{h(appointment["patient"])}</h3><p>{h(appointment["reason"])}</p>'
            if appointment['description']:
                content += f'<p>{h(appointment["description"])}</p>'
            content += f'<p class="status">{appointment["status"]}</p>'
            if user['role'] == 'profissional':
                content += f'<a class="primary" href="/atendimento?id={appointment["id"]}">Registro do atendimento →</a>'
            if appointment['status'] != 'Realizado':
                content += f'<form method="post" action="/cancelar"><input type="hidden" name="id" value="{appointment["id"]}"><button class="danger" onclick="return confirm(\'Cancelar esta consulta?\')">Cancelar consulta</button></form>'
            content += '</div></article>'
        else:
            free = not occupied(user['doctor'], selected.isoformat(), hour)
            content += f'<article class="agenda-hour {"free" if free else "blocked"}"><strong>{hour}</strong><span>{"Disponível" if free else "Não atende"}</span></article>'
    return content + '</section></div>'


def clinical_record(user, query):
    record = backend.encounter(user, query.get('id', [''])[0])
    content = heading('REGISTRO DO ATENDIMENTO', h(record['patient']), f'{fmt(record["date"])} às {record["time"]}', '<a class="text-link" href="/historico">Ver histórico</a>')
    content += f'<section class="panel clinical-record"><p><b>Motivo da consulta:</b> {h(record["reason"])}</p><p class="muted">{h(record["owner"])}</p>'
    if record['status'] == 'Cancelado':
        return content + '<p>Esta consulta foi cancelada.</p></section>'
    content += f'<form method="post" action="/atendimento"><input type="hidden" name="id" value="{record["id"]}"><input type="hidden" name="version" value="{record["version"]}">'
    for label, key, required in [('Comentário / evolução do atendimento', 'comment', True), ('Quadro do paciente / hipótese diagnóstica', 'condition', False), ('Encaminhamento / conduta', 'referral', False)]:
        content += f'<label>{label}<textarea name="{key}" rows="5" maxlength="10000" {"required" if required else ""}>{h(record[key] or "")}</textarea></label>'
    if record['completed_at']:
        content += '<p class="status">Consulta realizada · Registro disponível no histórico</p>'
    else:
        content += '<label class="completion-option"><input type="checkbox" name="complete" value="yes"> Marcar consulta como realizada e incluir no histórico</label>'
    content += '<p class="muted">Sem marcar como realizada, o registro fica salvo na consulta. Apenas o médico responsável pode acessar estas anotações.</p><button class="primary">Salvar registro</button></form></section>'
    if record['updated_at']:
        content += f'<p class="muted">Última atualização: {h(record["updated_at"])} (UTC) · Versão {record["version"]}</p>'
    return content


def clinical_history(user, query):
    term = query.get('q', [''])[0]
    records = backend.encounter_history(user, term)
    content = heading('CONTINUIDADE DO CUIDADO', 'Histórico de consultas', 'Pesquise pelo nome ou e-mail do paciente para consultar atendimentos realizados.')
    content += f'<section class="panel"><form method="get" action="/historico"><div class="search-line"><input name="q" value="{h(term)}" aria-label="Nome ou e-mail do paciente" placeholder="Nome ou e-mail do paciente"><button class="primary">Pesquisar paciente</button><a class="outline" href="/historico">Limpar</a></div></form></section><p class="muted">{len(records)} atendimento(s) realizado(s)</p>'
    for record in records:
        content += f'<article class="panel clinical-history"><div class="section-title"><div><h2>{h(record["patient"])}</h2><p class="muted">{h(record["email"])} · {fmt(record["date"])} às {record["time"]}</p></div><a class="outline" href="/atendimento?id={record["id"]}">Abrir registro →</a></div>'
        for label, key in [('Comentário', 'comment'), ('Quadro do paciente', 'condition'), ('Encaminhamento', 'referral')]:
            content += f'<div class="clinical-text"><strong>{label}</strong><p>{h(record[key]) if record[key] else "Não informado."}</p></div>'
        content += '</article>'
    if not records:
        content += '<section class="panel empty">Nenhuma consulta realizada encontrada. Abra uma consulta na agenda e salve o registro marcando-a como realizada.</section>'
    return content


def availability(user, query):
    day = query.get('date', [TOMORROW])[0]
    try: date.fromisoformat(day)
    except ValueError: day = TOMORROW
    doc = user['doctor']
    if user['role'] == 'atendente':
        doc = query.get('doctor', ['1'])[0]
        if doc not in [d['id'] for d in active_doctors()]:
            doc = active_doctors()[0]['id'] if active_doctors() else ''
    routine = query.get('scope', ['day'])[0] == 'routine'
    scope = 'routine' if routine else 'day'
    selected = ROUTINES.get(doc, TIMES) if routine else DAY_HOURS.get((doc, day), ROUTINES.get(doc, TIMES))
    content = heading('SUA AGENDA, DO SEU JEITO', 'Disponibilidade', 'Selecione os horários que deseja disponibilizar. Consultas existentes são preservadas.')
    content += f'<section class="panel"><h3>{h(doctor(doc)["name"])}</h3><div class="search-line"><a class="outline" href="/horarios?scope=routine&doctor={doc}">Rotina para todos os dias</a><a class="outline" href="/horarios?date={day}&doctor={doc}">Ajustar um dia específico</a></div>'
    if not routine:
        content += f'<form method="get" action="/horarios"><input type="hidden" name="doctor" value="{doc}"><label>Dia<input type="date" name="date" value="{day}" required onchange="this.form.submit()"></label></form>'
    title = 'Carga horária diária' if routine else 'Horários de atendimento'
    explanation = 'Estes horários se repetem todos os dias. Ajustes de datas específicas têm prioridade. Consultas já marcadas são mantidas.' if routine else 'Esta alteração vale apenas para a data escolhida. Nos demais dias, vale a rotina do médico.'
    content += f'<h3>{title}</h3><p class="muted">{explanation}</p><form method="post" action="/horarios"><input type="hidden" name="doctor" value="{doc}"><input type="hidden" name="scope" value="{scope}"><input type="hidden" name="date" value="{day}"><div class="slots">'
    for t in TIMES:
        booked = not routine and any(a['doctor'] == doc and a['date'] == day and a['time'] == t and a['status'] == 'Confirmado' for a in APPOINTMENTS)
        state = 'reserved' if booked else ''
        content += f'<label class="slot availability {state}"><input type="checkbox" name="available" value="{t}" {"checked" if t in selected else ""} {"disabled" if booked else ""}><span>{t}<small>{"Agendado" if booked else ""}</small></span></label>'
    return content + '</div><p class="slot-legend">🟢 Disponível · 🟡 Médico não atende · 🔴 Já agendado</p><p class="muted">Clique nos horários para alternar sua disponibilidade e salve. Consultas agendadas não podem ser alteradas aqui.</p><button class="primary">Salvar disponibilidade</button></form></section>'


class Handler(BaseHTTPRequestHandler):
    def cookie(self, name):
        try:
            c = SimpleCookie(self.headers.get('Cookie', ''))
            return c[name].value if name in c else ''
        except Exception:
            return ''

    def user(self):
        token = self.cookie('session')
        account = backend.session_user(token)
        if account:
            account['message'] = SESSIONS.pop(token, '')
        return account

    def send(self, body, status=200, mime='text/html; charset=utf-8'):
        csrf = self.cookie('csrf')
        if not re.fullmatch(r'[a-f0-9]{64}', csrf):
            csrf = secrets.token_hex(32)
        if isinstance(body, str) and mime.startswith('text/html'):
            body = re.sub(r'(<form\b[^>]*method="post"[^>]*>)', lambda m: m[0] + f'<input type="hidden" name="csrf" value="{csrf}">', body)
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(status)
        self.send_header('Set-Cookie', f'csrf={csrf}; SameSite=Strict; Path=/')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

    def redirect(self, url, cookie=None):
        self.send_response(303)
        self.send_header('Location', url)
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers()

    def do_GET(self):
        with LOCK:
            try:
                refresh_data()
                self.render_get()
            except (backend.DomainError, ValueError) as exc:
                self.error(str(exc), getattr(exc, 'status', 400))
            except Exception:
                logging.exception('Falha ao renderizar página')
                self.error('Não foi possível carregar esta página.', 500)

    def error(self, message, status=400):
        self.send(page('Confira os dados', f'<main><section class="panel"><h1>{h(message)}</h1><a class="outline" href="/">Voltar à plataforma</a></section></main>'), status)

    def render_get(self):
        path = urlparse(self.path).path
        q = parse_qs(urlparse(self.path).query)
        if path.startswith('/static/'):
            asset = (ROOT / path.lstrip('/')).resolve()
            if (ROOT / 'static').resolve() in asset.parents and asset.exists() and asset.is_file():
                mime = 'text/css; charset=utf-8' if asset.suffix == '.css' else 'image/svg+xml' if asset.suffix == '.svg' else 'image/png'
                return self.send(asset.read_bytes(), mime=mime)
            return self.send('Not found', 404)
        user = self.user()
        if not user: return self.send(login(path == '/cadastro'))
        home = {'paciente': 'buscar', 'profissional': 'agenda', 'atendente': 'buscar', 'admin': 'equipe'}[user['role']]
        if path == '/': return self.redirect('/' + home)
        allowed = {'paciente': ['buscar', 'agendar', 'consultas'], 'profissional': ['agenda', 'horarios'], 'atendente': ['buscar', 'agendar', 'consultas'], 'admin': ['equipe']}[user['role']]
        if user['role'] == 'atendente': allowed.append('horarios')
        if user['role'] == 'profissional': allowed.extend(['historico', 'atendimento'])
        allowed.append('senha')
        key = path.strip('/')
        if key not in allowed: return self.redirect('/' + home)
        if key == 'senha':
            content = heading('SUA CONTA', 'Alterar senha', 'Após salvar, entre novamente com a nova senha.') + '<section class="panel"><form method="post" action="/senha">' + field('Senha atual', 'current_password', 'password') + field('Nova senha (mínimo 8 caracteres)', 'new_password', 'password') + '<button class="primary">Salvar nova senha</button></form></section>'
        elif key == 'historico': content = clinical_history(user, q)
        elif key == 'atendimento': content = clinical_record(user, q)
        elif key == 'buscar': content = search(user, q)
        elif key == 'agendar': content = booking(user, q)
        elif key == 'agenda': content = professional_calendar(user, q)
        elif key == 'consultas': content = staff_view(user, q, 'consultas') if user['role'] == 'atendente' else appointments(user)
        elif key == 'horarios': content = staff_view(user, q, 'horarios') if user['role'] == 'atendente' else availability(user, q)
        else:
            content = heading('ADMINISTRAÇÃO', 'Funcionários', 'Cadastre profissionais e atendentes e gerencie sua equipe.')
            content += '<section class="panel"><h2>Cadastrar funcionário</h2><form method="post" action="/funcionarios">'
            content += field('Nome completo', 'name') + field('E-mail', 'email', 'email') + '<p class="muted">Senha inicial: <strong>SenhaPadraoFunc</strong>. O funcionário pode alterá-la em Alterar senha.</p>'
            content += '<label>Perfil<select name="role" onchange="document.getElementById(\'professional-fields\').hidden=this.value!==\'profissional\'"><option value="profissional">Profissional</option><option value="atendente">Atendente</option></select></label><div id="professional-fields">'
            content += field('Especialidade (obrigatória para profissionais)', 'specialty', required=False) + field('Valor da consulta em R$', 'price', 'number', '180', required=False)
            content += '</div><button class="primary">Cadastrar funcionário</button></form></section><section class="panel" style="margin-top:24px"><h2>Equipe cadastrada</h2>'
            for s in STAFF:
                content += f'<article class="appointment"><b class="mini-avatar">{h(s["name"][0])}</b><div class="appointment-detail"><h3>{h(s["name"])}</h3><p>{h(s["role"])} · {h(s.get("email", ""))}</p></div><span class="status {"cancelled" if not s["active"] else ""}">{"Ativo" if s["active"] else "Desligado"}</span>'
                if s['active']: content += f'<form method="post" action="/demitir"><input type="hidden" name="id" value="{s["id"]}"><button class="danger" onclick="return confirm(\'Confirmar o desligamento deste funcionário?\')">Demitir funcionário</button></form>'
                content += '</article>'
            content += '</section>'
        message = user.pop('message', '')
        self.send(page(ROLES[user['role']], content, user, 'buscar' if key == 'agendar' else key, message))

    def do_POST(self):
        with LOCK:
            try: self.post()
            except backend.DomainError as exc: self.error(str(exc), exc.status)
            except (ValueError, KeyError): self.error('Confira os dados informados.')
            except backend.DatabaseError:
                logging.exception('Erro de banco de dados')
                self.error('Não foi possível salvar. Tente novamente.', 503)
            except Exception:
                logging.exception('Erro na requisição')
                self.error('Não foi possível concluir a operação.', 500)

    def post(self):
        length = int(self.headers.get('Content-Length', 0))
        if not 0 < length <= 524288:
            raise backend.DomainError('Formulário inválido ou muito grande.', 413)
        data = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True, max_num_fields=50)
        get = lambda key: data.get(key, [''])[0]
        csrf = self.cookie('csrf')
        if not re.fullmatch(r'[a-f0-9]{64}', csrf) or not secrets.compare_digest(csrf, get('csrf')):
            raise backend.DomainError('A página expirou. Recarregue antes de enviar novamente.', 403)
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            raise backend.DomainError('Origem do formulário inválida.', 403)
        path = urlparse(self.path).path
        values = {key: get(key).strip() for key in data}
        if path in ['/entrar', '/cadastrar-paciente']:
            if path == '/cadastrar-paciente':
                backend.register(get('name'), get('email'), get('password'))
            token = backend.authenticate(get('email'), get('password'), self.client_address[0])
            old_token = self.cookie('session')
            if old_token:
                backend.logout(old_token)
            return self.redirect('/', f'session={token}; HttpOnly; SameSite=Lax; Max-Age=28800; Path=/')
        user = self.user()
        if not user:
            return self.redirect('/')
        target, message = '/', ''
        if path == '/sair':
            backend.logout(self.cookie('session'))
            return self.redirect('/', 'session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/')
        elif path == '/senha':
            backend.change_password(user, get('current_password'), get('new_password'))
            return self.redirect('/', 'session=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/')
        elif path == '/atendimento':
            ident = backend.save_encounter(user, values)
            target, message = f'/atendimento?id={ident}', 'Registro do atendimento salvo.'
        elif path == '/agendar':
            values['patient_password'] = get('patient_password')
            doc = backend.book(user, values)
            target = f'/consultas?doctor={doc}' if user['role']=='atendente' else '/consultas'
            message = 'Consulta agendada com sucesso.'
        elif path == '/cancelar':
            doc = backend.cancel(user, get('id'))
            target = '/agenda' if user['role']=='profissional' else f'/consultas?doctor={doc}' if user['role']=='atendente' else '/consultas'
            message = 'Consulta cancelada.'
        elif path == '/horarios':
            doc = backend.save_hours(user, get('doctor'), get('date'), get('scope'), data.get('available', []))
            target = f'/horarios?doctor={doc}&scope={get("scope")}&date={get("date")}'
            message = 'Disponibilidade salva. Consultas existentes foram preservadas.'
        elif path == '/funcionarios':
            backend.create_employee(user, values)
            target, message = '/equipe', 'Funcionário cadastrado.'
        elif path == '/demitir':
            backend.dismiss(user, get('id'))
            target, message = '/equipe', 'Funcionário desligado. O acesso foi revogado.'
        else:
            raise backend.DomainError('Operação não encontrada.', 404)
        SESSIONS[self.cookie('session')] = message
        return self.redirect(target)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Iniciar AgendAí')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        backend.initialize()
        initial_password = backend.seed_demo()
    except (backend.DatabaseError, ValueError):
        raise SystemExit('Não foi possível conectar ao PostgreSQL. Confira o .env e se o banco está iniciado. Consulte README.md.')
    if initial_password:
        print('Banco criado. Senha inicial de admin e paciente de exemplo:', initial_password, flush=True)
        print('Admin: admin@agendai.com — guarde a senha antes de fechar este terminal.', flush=True)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        raise SystemExit(f'Não foi possível iniciar na porta {args.port}: {exc}. Tente --port 8766')
    print(f'AgendAí disponível em http://127.0.0.1:{args.port} — Ctrl+C para encerrar.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
