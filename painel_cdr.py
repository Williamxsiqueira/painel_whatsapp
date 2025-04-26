import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
from functools import wraps

# Configuração de logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'altere_para_um_segredo_forte')
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# Conexão com Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credenciais.json", scope)
client = gspread.authorize(creds)

wb = client.open("whatsapp_contatos")
contatos_sheet = wb.worksheet("Página1")
config_sheet = wb.worksheet("configuracoes")
usuarios_sheet = wb.worksheet("usuarios")

# Planilha separada de promoções (arquivo inteiro)
try:
    promocoes_wb = client.open("promocoes")
    promocoes_sheet = promocoes_wb.sheet1
except SpreadsheetNotFound:
    promocoes_wb = client.create("promocoes")
    promocoes_sheet = promocoes_wb.sheet1
    promocoes_sheet.append_row(["vendedor", "promocao", "timestamp"])

COLS = {
    'nome_cliente': 1,
    'numero_whatsapp': 2,
    'vendedor': 3,
    'recebeu_msg1': 4,
    'respondeu_msg1': 5,
    'data_ultimo_envio': 6,
    'tipo_cliente': 7,
    'mensagem_gerada': 8,
    'disparar_msg1': 9
}


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped


def load_users():
    try:
        recs = usuarios_sheet.get_all_records()
    except Exception as e:
        logging.error(f"Erro ao ler usuários: {e}")
        return {}
    users = {}
    for row in recs:
        u = row.get('username', '').strip().lower()
        users[u] = {'password': str(
            row.get('password', '')), 'role': row.get('role', 'vendor')}
    return users


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        u = request.form['username'].strip().lower()
        p = request.form['password']
        users = load_users()
        if u in users and users[u]['password'] == p:
            session.permanent = True
            session['username'] = u
            session['role'] = users[u]['role']
            return redirect(url_for('index'))
        error = "Usuário ou senha inválidos."
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def carregar_lista(coluna):
    try:
        vals = config_sheet.col_values(coluna)
        return [v for v in vals if v.strip() and v.lower() != 'header']
    except Exception as e:
        logging.error(f"Erro carregando configurações coluna {coluna}: {e}")
        flash("Não foi possível carregar configurações.")
        return []


@app.route('/')
@login_required
def index():
    sel_vendedor = request.args.get('vendedor', '').strip()
    sel_tipo = request.args.get('tipo_cliente', '').strip()
    sel_busca = request.args.get('busca_nome', '').strip().lower()
    sel_tempo = request.args.get('tempo_envio', '').strip()
    try:
        rows = contatos_sheet.get_all_values()[1:]
    except Exception as e:
        logging.error(f"Erro lendo contatos: {e}")
        flash("Falha ao carregar contatos.")
        rows = []
    if session['role'] == 'vendor':
        rows = [r for r in rows if r[COLS['vendedor']-1].strip().lower()
                == session['username']]
    if sel_vendedor:
        rows = [r for r in rows if r[COLS['vendedor']-1] == sel_vendedor]
    if sel_tipo:
        rows = [r for r in rows if r[COLS['tipo_cliente']-1] == sel_tipo]
    if sel_busca:
        rows = [r for r in rows if sel_busca in r[COLS['nome_cliente']-1].lower()]
    if sel_tempo:
        try:
            d = int(sel_tempo)
            cutoff = datetime.now() - timedelta(days=d)
            rows = [r for r in rows if datetime.fromisoformat(
                r[COLS['data_ultimo_envio']-1]) >= cutoff]
        except:
            pass
    for r in rows:
        if r[COLS['disparar_msg1']-1].strip().lower() == 'sim':
            r[COLS['mensagem_gerada']-1] = ''
    for r in rows:
        ds = r[COLS['data_ultimo_envio']-1]
        try:
            r[COLS['data_ultimo_envio'] -
                1] = datetime.fromisoformat(ds).strftime("%d/%m/%Y")
        except:
            pass
    vendedores = carregar_lista(1)
    tipos = carregar_lista(2)
    return render_template('painel.html', dados=rows, vendedores=vendedores, tipos=tipos,
                           sel_vendedor=sel_vendedor, sel_tipo=sel_tipo, sel_busca=sel_busca, sel_tempo=sel_tempo)


@app.route('/salvar_edicoes', methods=['POST'])
@login_required
def salvar_edicoes():
    try:
        rows = contatos_sheet.get_all_values()[1:]
    except Exception as e:
        logging.error(f"Erro lendo para salvar: {e}")
        flash("Falha ao salvar edições.")
        return redirect(url_for('index'))
    for idx, r in enumerate(rows):
        nome = request.form.get(f'nome_{idx}')
        numero = request.form.get(f'numero_{idx}')
        vend = request.form.get(f'vendedor_{idx}')
        tipo = request.form.get(f'tipo_cliente_{idx}')
        if not (nome and numero and vend and tipo):
            continue
        if len(numero) == 13:
            numero = numero[:4] + numero[5:]
        if len(numero) != 12 or any(numero == x[COLS['numero_whatsapp']-1] and i != idx for i, x in enumerate(rows)):
            continue
        rn = idx+2
        try:
            contatos_sheet.update_cell(rn, COLS['nome_cliente'], nome)
            contatos_sheet.update_cell(rn, COLS['numero_whatsapp'], numero)
            contatos_sheet.update_cell(rn, COLS['vendedor'], vend)
            contatos_sheet.update_cell(rn, COLS['tipo_cliente'], tipo)
        except Exception as e:
            logging.error(f"Erro salvando linha {rn}: {e}")
            flash("Algumas alterações não foram salvas.")
    return redirect(url_for('index'))


@app.route('/adicionar', methods=['POST'])
@login_required
def adicionar():
    nome = request.form.get('nome')
    numero = request.form.get('numero')
    vend = request.form.get('vendedor')
    tipo = request.form.get('tipo_cliente')
    if not (nome and numero and vend and tipo):
        flash("Preencha todos os campos.")
        return redirect(url_for('index'))
    try:
        if len(numero) == 13:
            numero = numero[:4] + numero[5:]
        nums = contatos_sheet.col_values(COLS['numero_whatsapp'])
        if len(numero) != 12 or numero in nums:
            flash("Número inválido ou duplicado.")
            return redirect(url_for('index'))
        contatos_sheet.append_row(
            [nome, numero, vend, '', '', '', tipo, '', ''])
    except Exception as e:
        logging.error(f"Erro adicionando cliente: {e}")
        flash("Falha ao adicionar cliente.")
    return redirect(url_for('index'))


@app.route('/enviar_tudo', methods=['POST'])
@login_required
def enviar_tudo():
    try:
        rows = contatos_sheet.get_all_values()[1:]
    except Exception as e:
        logging.error(f"Erro lendo para envio: {e}")
        flash("Falha ao disparar.")
        return redirect(url_for('index'))
    contexto = request.form.get('contexto2', '').strip()
    agora = datetime.now().isoformat(sep=' ', timespec='seconds')
    for idx, r in enumerate(rows):
        if request.form.get(f'selecao_{idx}'):
            msg1 = request.form.get(f'mensagem_{idx}', '').strip()
            vendedor = r[COLS['vendedor']-1]
            if msg1:
                rn = idx+2
                contatos_sheet.update_cell(rn, COLS['mensagem_gerada'], msg1)
                contatos_sheet.update_cell(rn, COLS['disparar_msg1'], 'sim')
                contatos_sheet.update_cell(
                    rn, COLS['data_ultimo_envio'], agora)
            try:
                cell = promocoes_sheet.find(vendedor)
                promocoes_sheet.update_cell(cell.row, 2, contexto)
                promocoes_sheet.update_cell(cell.row, 3, agora)
            except Exception:
                promocoes_sheet.append_row([vendedor, contexto, agora])
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
