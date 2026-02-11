from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_ultra_secreta_escola'

# --- CONFIGURAÇÃO BANCO DE DADOS ---
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
    atendimentos = db.relationship('Atendimento', backref='professor', lazy=True)

class Atendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno_nome = db.Column(db.String(100), nullable=False)
    data_solicitacao = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(20), default='aguardando') # aguardando, chamado
    hora_chamada = db.Column(db.DateTime, nullable=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'), nullable=False)

# Cria o banco de dados
with app.app_context():
    db.create_all()

# --- ROTAS DE NAVEGAÇÃO ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/aluno')
def aluno_page():
    professores = Professor.query.all()
    return render_template('aluno.html', professores=professores)

@app.route('/tv')
def tv():
    return render_template('tv.html')

# --- LÓGICA DO ALUNO ---

@app.route('/agendar', methods=['POST'])
def agendar():
    nome_aluno = request.form['nome'].strip()
    prof_id = request.form.get('professor_id')
    
    if not prof_id:
        return redirect(url_for('aluno_page'))

    ja_agendou = Atendimento.query.filter_by(
        aluno_nome=nome_aluno, 
        data_solicitacao=date.today()
    ).first()

    if ja_agendou:
        professores = Professor.query.all()
        return render_template('aluno.html', professores=professores, erro="Você já pegou uma senha hoje!")

    novo = Atendimento(aluno_nome=nome_aluno, professor_id=int(prof_id))
    db.session.add(novo)
    db.session.commit()
    
    professores = Professor.query.all()
    return render_template('aluno.html', professores=professores, mensagem="Senha gerada! Aguarde na TV.")

# --- AREA DO PROFESSOR ---

@app.route('/professor')
def professor_painel():
    if 'prof_id' not in session:
        return render_template('professor_login.html', professores=Professor.query.all())
    
    lista = Atendimento.query.filter_by(
        professor_id=session['prof_id'], 
        status='aguardando'
    ).all()
    
    return render_template('professor_painel.html', 
                           guiche=session['guiche'], 
                           nome=session['prof_nome'], 
                           atendimentos=lista)

@app.route('/login_prof', methods=['POST'])
def login_prof():
    prof_id = request.form.get('professor_id')
    guiche = request.form.get('guiche')
    
    if prof_id:
        prof = Professor.query.get(prof_id)
        session['prof_id'] = prof.id
        session['prof_nome'] = prof.nome
        session['guiche'] = guiche
    return redirect(url_for('professor_painel'))

@app.route('/chamar', methods=['POST'])
def chamar():
    atendimento = Atendimento.query.get(request.form['id'])
    if atendimento:
        atendimento.status = 'chamado'
        atendimento.hora_chamada = datetime.now()
        db.session.commit()
        
        historico = Atendimento.query.filter_by(status='chamado')\
            .order_by(Atendimento.hora_chamada.desc()).limit(5).all()
        
        lista_h = [{'aluno': h.aluno_nome, 'prof': h.professor.nome} for h in historico]

        socketio.emit('atualizar_tv', {
            'atual': {
                'aluno': atendimento.aluno_nome,
                'guiche': session.get('guiche', '?'),
                'professor': session.get('prof_nome', 'Professor')
            },
            'historico': lista_h
        })
    return redirect(url_for('professor_painel'))

@app.route('/sair')
def sair():
    session.clear()
    return redirect(url_for('index'))

# --- AREA ADMINISTRATIVA (COM PROTEÇÃO) ---

ADMIN_PASSWORD = "thomassoft" 

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        senha_digitada = request.form.get('senha')
        if senha_digitada == ADMIN_PASSWORD:
            session['admin_logado'] = True
            return redirect(url_for('admin_page'))
        else:
            return render_template('admin_login.html', erro="Senha incorreta!")
    return render_template('admin_login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_page():
    # Se não tiver a marcação na sessão, bloqueia
    if not session.get('admin_logado'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        nome = request.form['nome']
        materia = request.form['materia']
        db.session.add(Professor(nome=nome, materia=materia))
        db.session.commit()
        return redirect(url_for('admin_page'))
    
    professores = Professor.query.all()
    return render_template('admin.html', professores=professores)

@app.route('/admin/delete/<int:id>')
def delete_prof(id):
    if not session.get('admin_logado'):
        return redirect(url_for('admin_login'))
        
    prof = Professor.query.get(id)
    if prof:
        Atendimento.query.filter_by(professor_id=id).delete()
        db.session.delete(prof)
        db.session.commit()
    return redirect(url_for('admin_page'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logado', None)
    return redirect(url_for('index'))

# --- INICIALIZAÇÃO ---

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)