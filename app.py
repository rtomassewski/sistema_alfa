from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_ultra_secreta_escola'

# Configuração Banco de Dados
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'escola.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

# --- MODELOS (TABELAS DO BANCO) ---

class Professor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    materia = db.Column(db.String(100), nullable=False)
    # Relacionamento: Um professor tem vários atendimentos
    atendimentos = db.relationship('Atendimento', backref='professor', lazy=True)

class Atendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno_nome = db.Column(db.String(100), nullable=False)
    data_solicitacao = db.Column(db.Date, default=date.today) # Para controlar "1 por dia"
    status = db.Column(db.String(20), default='aguardando') # aguardando, chamado, finalizado
    hora_chamada = db.Column(db.DateTime, nullable=True) # Para ordenar o histórico da TV
    
    # Chave Estrangeira (Liga o atendimento a um professor específico)
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'), nullable=False)

# Cria o banco e popula com professores iniciais se estiver vazio
with app.app_context():
    db.create_all()
    if not Professor.query.first():
        print("Criando professores padrão...")
        db.session.add(Professor(nome="Prof. Carlos", materia="Matemática"))
        db.session.add(Professor(nome="Prof. Ana", materia="História"))
        db.session.add(Professor(nome="Coord. Roberto", materia="Coordenação"))
        db.session.add(Professor(nome="Secretaria", materia="Geral"))
        db.session.commit()

# --- ROTAS ---

@app.route('/')
def index():
    # Busca todos os professores para preencher o <select>
    professores = Professor.query.all()
    return render_template('aluno.html', professores=professores)

@app.route('/agendar', methods=['POST'])
def agendar():
    nome_aluno = request.form['nome'].strip()
    prof_id = int(request.form['professor_id'])
    
    # 1. VERIFICAÇÃO: Aluno já agendou hoje?
    ja_agendou = Atendimento.query.filter_by(
        aluno_nome=nome_aluno, 
        data_solicitacao=date.today()
    ).first()

    if ja_agendou:
        professores = Professor.query.all()
        return render_template('aluno.html', professores=professores, erro="Você já pegou uma senha hoje!")

    # 2. CRIAÇÃO
    novo = Atendimento(aluno_nome=nome_aluno, professor_id=prof_id)
    db.session.add(novo)
    db.session.commit()
    
    professores = Professor.query.all()
    return render_template('aluno.html', professores=professores, mensagem="Senha gerada! Aguarde.")

# --- AREA DO PROFESSOR ---

@app.route('/login_prof', methods=['POST'])
def login_prof():
    # Login simplificado: O professor escolhe seu nome numa lista (em produção usaria senha)
    prof_id = request.form.get('professor_id')
    guiche = request.form.get('guiche')
    
    if prof_id:
        prof = Professor.query.get(prof_id)
        session['prof_id'] = prof.id
        session['prof_nome'] = prof.nome
        session['prof_materia'] = prof.materia
        session['guiche'] = guiche
        return redirect(url_for('professor_painel'))
    
    return redirect(url_for('professor_login'))

@app.route('/professor')
def professor_painel():
    if 'prof_id' not in session:
        return render_template('professor_login.html', professores=Professor.query.all())
    
    # FILTRO: Só mostra alunos deste professor específico
    lista = Atendimento.query.filter_by(
        professor_id=session['prof_id'], 
        status='aguardando'
    ).all()
    
    return render_template('professor_painel.html', 
                           guiche=session['guiche'], 
                           nome=session['prof_nome'], 
                           atendimentos=lista)

@app.route('/chamar', methods=['POST'])
def chamar():
    atendimento = Atendimento.query.get(request.form['id'])
    if atendimento:
        atendimento.status = 'chamado'
        atendimento.hora_chamada = datetime.now()
        db.session.commit()
        
        # Pega os últimos 5 chamados para o histórico da TV
        historico = Atendimento.query.filter_by(status='chamado')\
            .order_by(Atendimento.hora_chamada.desc()).limit(5).all()
        
        # Prepara dados para enviar via socket
        lista_historico = []
        for h in historico:
            lista_historico.append({
                'aluno': h.aluno_nome,
                'prof': h.professor.nome, # Pega nome via relacionamento
                'guiche': session['guiche'] if h.id == atendimento.id else "..." # Simplificação
            })

        socketio.emit('atualizar_tv', {
            'atual': {
                'aluno': atendimento.aluno_nome,
                'guiche': session['guiche'],
                'professor': session['prof_nome']
            },
            'historico': lista_historico
        })
        
    return redirect(url_for('professor_painel'))

@app.route('/sair')
def sair():
    session.clear()
    return redirect(url_for('professor_painel'))

# Rota extra para você cadastrar mais professores facilmente
@app.route('/admin/novo_prof', methods=['POST'])
def novo_prof():
    nome = request.form['nome']
    materia = request.form['materia']
    db.session.add(Professor(nome=nome, materia=materia))
    db.session.commit()
    return "Professor cadastrado!"

@app.route('/tv')
def tv():
    return render_template('tv.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)