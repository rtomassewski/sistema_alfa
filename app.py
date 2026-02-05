from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_secreta'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'escola.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

class Atendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno = db.Column(db.String(100), nullable=False)
    professor_destino = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='aguardando')

with app.app_context():
    db.create_all()

# --- ROTAS ---
@app.route('/')
def index():
    return render_template('aluno.html') # Agora chama o arquivo separado

@app.route('/agendar', methods=['POST'])
def agendar():
    novo = Atendimento(aluno=request.form['nome'], professor_destino=request.form['professor'])
    db.session.add(novo)
    db.session.commit()
    return render_template('aluno.html', mensagem="Senha gerada com sucesso!")

@app.route('/professor')
def professor():
    if 'prof_nome' not in session: return render_template('professor.html', guiche=None)
    lista = Atendimento.query.filter_by(status='aguardando').all()
    return render_template('professor.html', guiche=session['prof_guiche'], nome=session['prof_nome'], atendimentos=lista)

@app.route('/login_prof', methods=['POST'])
def login_prof():
    session['prof_nome'] = request.form['nome']
    session['prof_guiche'] = request.form['guiche']
    return redirect(url_for('professor'))

@app.route('/chamar', methods=['POST'])
def chamar():
    atendimento = Atendimento.query.get(request.form['id'])
    if atendimento:
        atendimento.status = 'chamado'
        db.session.commit()
        socketio.emit('chamar_aluno', {'aluno': atendimento.aluno, 'guiche': session['prof_guiche'], 'professor': session['prof_nome']})
    return redirect(url_for('professor'))

@app.route('/tv')
def tv():
    return render_template('tv.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('professor'))

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')