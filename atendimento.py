from flask import Blueprint, render_template, request, session, redirect, url_for
import sqlite3
from datetime import datetime

# Blueprint para o Painel de Atendimento
bp_atendimento = Blueprint(
    'atendimento',
    __name__,
    template_folder='templates',
    url_prefix='/atendimento'
)

DB_PATH = 'mensagens.db'

# Função para inicializar o banco de dados (mensagens.db)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT,
            nome_cliente TEXT,
            vendedor_atribuido TEXT,
            mensagem TEXT,
            data_hora TEXT,
            respondido TEXT DEFAULT 'não'
        )
    """)
    conn.commit()
    conn.close()

# Inicializa o banco de dados antes da primeira requisição


@bp_atendimento.before_app_first_request
def before_first_request():
    init_db()

# Rota principal do painel de atendimento: lista de conversas


@bp_atendimento.route('/')
def index():
    vendedor = session.get('vendedor')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if vendedor and vendedor.lower() != 'admin':
        cursor.execute(
            "SELECT * FROM conversas WHERE vendedor_atribuido = ? ORDER BY data_hora DESC",
            (vendedor,)
        )
    else:
        cursor.execute(
            "SELECT * FROM conversas ORDER BY data_hora DESC"
        )

    conversas = cursor.fetchall()
    conn.close()
    return render_template('painel_atendimento.html', conversas=conversas)

# Rota de detalhe da conversa e resposta (placeholder)


@bp_atendimento.route('/conversa/<int:conversa_id>', methods=['GET', 'POST'])
def conversa(conversa_id):
    # TODO: implementar visualização da conversa específica e envio de resposta
    return redirect(url_for('atendimento.index'))
