from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
import os

# Importação consolidada de todos os modelos do banco de dados
from models import (
    db, Usuario, Item, Maquina, MovimentacaoEstoque,
    OrdemServico, AuditLog, ItemImagem, MaquinaImagem,
    OrdemServicoImagem, OrdemServicoItemPrevisto
)
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# -----------------------------------------------------------------------------
# CONFIGURAÇÕES DE PASTAS DE UPLOAD
# -----------------------------------------------------------------------------
PASTA_UPLOAD_MAQUINAS = os.path.join('static', 'uploads', 'maquinas')
app.config['UPLOAD_MAQUINAS'] = PASTA_UPLOAD_MAQUINAS
os.makedirs(PASTA_UPLOAD_MAQUINAS, exist_ok=True)

PASTA_UPLOAD_OS = os.path.join('static', 'uploads', 'os')
app.config['UPLOAD_OS'] = PASTA_UPLOAD_OS
os.makedirs(PASTA_UPLOAD_OS, exist_ok=True)

# Inicialização do Banco de Dados e Login Manager
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# Criação das tabelas e do Usuário Padrão
with app.app_context():
    db.create_all()

    if not Usuario.query.first():
        senha_criptografada = generate_password_hash('admin123')
        usuario_admin = Usuario(
            username='admin',
            email='admin@industria.com',
            password_hash=senha_criptografada,
            role='Administrador'
        )
        db.session.add(usuario_admin)
        db.session.commit()
        print("Usuário padrão 'admin' criado com sucesso!")


# -----------------------------------------------------------------------------
# ROTAS DE AUTENTICAÇÃO
# -----------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Utilizador ou senha incorretos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# -----------------------------------------------------------------------------
# ROTA: LISTAR USUÁRIOS
# -----------------------------------------------------------------------------
@app.route('/usuarios')
@login_required
def listar_usuarios():
    if current_user.role != 'Administrador':
        flash('Acesso negado: Área restrita para administradores.', 'danger')
        return redirect(url_for('dashboard'))

    usuarios = Usuario.query.order_by(Usuario.id).all()
    return render_template('usuarios.html', usuarios=usuarios)


# -----------------------------------------------------------------------------
# ROTA: CADASTRAR NOVO USUÁRIO
# -----------------------------------------------------------------------------
@app.route('/usuario/novo', methods=['POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    email = request.form.get('email')
    senha = request.form.get('password')
    role = request.form.get('role')

    usuario_existente = Usuario.query.filter_by(username=username).first()
    if usuario_existente:
        flash('Erro: Este nome de usuário já está em uso no sistema.', 'danger')
        return redirect(url_for('listar_usuarios'))

    senha_criptografada = generate_password_hash(senha)

    novo_user = Usuario(
        username=username,
        email=email,
        password_hash=senha_criptografada,
        role=role
    )

    db.session.add(novo_user)
    db.session.commit()

    flash(f'Usuário {username} cadastrado com sucesso!', 'success')
    return redirect(url_for('listar_usuarios'))



# -----------------------------------------------------------------------------
# ROTA: DASHBOARD PRINCIPAL (PAINEL DE CONTROLE)
# -----------------------------------------------------------------------------
@app.route('/')
@app.route('/paineldecontrole')
@app.route('/dashboard')
@login_required
def dashboard():
    hoje = date.today()
    limite_alerta = hoje + timedelta(days=2)

    # 1. Consultas para Peças e Máquinas
    total_pecas = Item.query.count()
    maquinas_operando = Maquina.query.filter_by(status='Operando').count()

    # 2. Consultas para Ordens de Serviço Pendentes
    os_pendentes_list = OrdemServico.query.filter(OrdemServico.status != 'Concluída').all()
    total_pendentes = len(os_pendentes_list)

    # Filtragem auxiliar por prazos críticos
    os_atrasadas = [os for os in os_pendentes_list if os.prazo_previsto < hoje]
    os_no_prazo_critico = [os for os in os_pendentes_list if hoje <= os.prazo_previsto <= limite_alerta]

    # 3. Consulta para Alertas de Estoque Mínimo
    itens_alerta_list = Item.query.filter(Item.estoque_atual <= Item.estoque_minimo).all()

    # Retorno unificado com todas as variáveis e apelidos necessários
    return render_template('paineldecontrole.html',
                           # Peças e Estoque Geral
                           total_pecas=total_pecas,
                           total_itens=total_pecas,
                           pecas_cadastradas=total_pecas,

                           # Máquinas Operando
                           maquinas_operando=maquinas_operando,
                           total_maquinas=maquinas_operando,
                           maquinas_ativas=maquinas_operando,

                           # Ordens de Serviço (Múltiplas variações para segurança do Card)
                           total_pendentes=total_pendentes,
                           total_os=total_pendentes,
                           qtd_os=total_pendentes,
                           os_pendentes=total_pendentes,

                           # Alertas de Estoque (Mapeamento completo incluindo a variável "alertas")
                           alertas=itens_alerta_list,  # <--- CORREÇÃO AQUI
                           itens_alerta=itens_alerta_list,
                           alertas_estoque=itens_alerta_list,
                           itens_estoque_minimo=itens_alerta_list,
                           produtos_alerta=itens_alerta_list,

                           # Listas para prazos de O.S.
                           os_atrasadas=os_atrasadas,
                           os_no_prazo_critico=os_no_prazo_critico)

# -----------------------------------------------------------------------------
# ROTA: PESQUISA E CONSULTA DE ITENS
# -----------------------------------------------------------------------------
@app.route('/itens', methods=['GET'])
@login_required
def listar_itens():
    termo_busca = request.args.get('search', '')

    query = Item.query
    if termo_busca:
        query = query.filter(
            (Item.sku.ilike(f'%{termo_busca}%')) |
            (Item.descricao.ilike(f'%{termo_busca}%')) |
            (Item.categoria.ilike(f'%{termo_busca}%')) |
            (Item.localizacao.ilike(f'%{termo_busca}%'))
        )
    itens = query.all()
    return render_template('itens.html', itens=itens, termo_busca=termo_busca)


# -----------------------------------------------------------------------------
# ROTA: CONTROLE OPERACIONAL DE ORDENS DE SERVIÇO
# -----------------------------------------------------------------------------
@app.route('/ordens')
@login_required
def listar_ordens():
    ordens = OrdemServico.query.order_by(OrdemServico.data_abertura.desc()).all()
    todas_maquinas = Maquina.query.all()
    pecas_disponiveis = Item.query.all()
    return render_template('ordens.html', ordens=ordens, maquinas=todas_maquinas, pecas=pecas_disponiveis)


@app.route('/ordem/nova', methods=['POST'])
@login_required
def nova_os():
    maquina_id = request.form.get('maquina_id')
    descricao_defeito = request.form.get('descricao_defeito')
    prazo_previsto_str = request.form.get('prazo_previsto')

    prazo_previsto = datetime.strptime(prazo_previsto_str, '%Y-%m-%d').date()

    nova_os = OrdemServico(maquina_id=maquina_id, descricao_defeito=descricao_defeito, prazo_previsto=prazo_previsto)
    db.session.add(nova_os)
    db.session.flush()

    skus_selecionados = request.form.getlist('pecas_sku[]')
    quantidades = request.form.getlist('pecas_qtd[]')

    for sku, qtd in zip(skus_selecionados, quantidades):
        if sku and qtd:
            previsao = OrdemServicoItemPrevisto(os_id=nova_os.id, item_sku=sku, quantidade_prevista=int(qtd))
            db.session.add(previsao)

    if 'imagens' in request.files:
        arquivos = request.files.getlist('imagens')
        for arquivo in arquivos:
            if arquivo and arquivo.filename != '':
                nome_seguro = secure_filename(f"os_{nova_os.id}_{arquivo.filename}")
                arquivo.save(os.path.join(app.config['UPLOAD_OS'], nome_seguro))

                nova_foto = OrdemServicoImagem(os_id=nova_os.id, caminho_arquivo=f"uploads/os/{nome_seguro}")
                db.session.add(nova_foto)

    maquina = Maquina.query.get(maquina_id)
    if maquina:
        maquina.status = 'Defeito'

    db.session.commit()
    flash(f'O.S. Nº {nova_os.id} aberta e máquina alterada para status Em Defeito!', 'success')
    return redirect(url_for('listar_ordens'))


@app.route('/api/item/<int:item_id>', methods=['GET'])
@login_required
def obter_detalhes_item(item_id):
    item = Item.query.get_or_404(item_id)
    imagens = [img.caminho_imagem for img in item.imagens]

    return jsonify({
        'sku': item.sku,
        'descricao': item.descricao,
        'categoria': item.categoria,
        'localizacao': item.localizacao,
        'estoque_atual': item.estoque_atual,
        'estoque_minimo': item.estoque_minimo,
        'estoque_maximo': item.estoque_maximo,
        'preco': float(item.preco_unitario),
        'imagens': imagens
    })


# -----------------------------------------------------------------------------
# ROTA API: OBTER DETALHES COMPLETOS DA MÁQUINA (MODAL VIA FETCH)
# -----------------------------------------------------------------------------
@app.route('/api/maquina/<int:maquina_id>', methods=['GET'])
@login_required
def obter_detalhes_maquina(maquina_id):
    maquina = Maquina.query.get_or_404(maquina_id)
    imagens = [img.caminho_arquivo for img in maquina.imagens]

    # Coleta todas as Ordens de Serviço associadas
    ordens = maquina.ordens_servico

    tempo_parada_str = "0 horas (Equipamento Operando)"
    previsao_manutencao = "Nenhuma manutenção pendente"
    ordens_data = []

    # Filtra ordens ativas para cálculo de parada e previsão
    ordens_ativas = [os for os in ordens if os.status in ['Pendente', 'Em Andamento']]

    # 1. Cálculo do Tempo de Parada Atual
    if maquina.status != 'Operando' and ordens_ativas:
        # Pega a ordem ativa mais antiga (quando o equipamento parou)
        os_inicial = min(ordens_ativas, key=lambda x: x.data_abertura)
        diferenca = datetime.utcnow() - os_inicial.data_abertura

        horas = int(diferenca.total_seconds() // 3600)
        minutos = int((diferenca.total_seconds() % 3600) // 60)
        tempo_parada_str = f"{horas}h {minutos}min"

    # 2. Cálculo da Previsão de Manutenção (Prazo Limite Próximo)
    if ordens_ativas:
        os_proxima = min(ordens_ativas, key=lambda x: x.prazo_previsto)
        previsao_manutencao = os_proxima.prazo_previsto.strftime('%d/%m/%Y')

    # 3. Formatação do Histórico / Programação de OS (Ordenado por data mais recente)
    ordens_ordenadas = sorted(ordens, key=lambda x: x.data_abertura, reverse=True)
    for os in ordens_ordenadas:
        ordens_data.append({
            'id': os.id,
            'descricao_defeito': os.descricao_defeito,
            'data_abertura': os.data_abertura.strftime('%d/%m/%Y %H:%M'),
            'prazo_previsto': os.prazo_previsto.strftime('%d/%m/%Y'),
            'status': os.status
        })

    return jsonify({
        'id': maquina.id,
        'codigo': maquina.codigo,
        'descricao': maquina.descricao,
        'linha': maquina.linha,
        'status': maquina.status,
        'imagens': imagens,
        'tempo_parada': tempo_parada_str,
        'previsao_manutencao': previsao_manutencao,
        'programacao_os': ordens_data[:5]  # Retorna as 5 mais recentes
    })


# -----------------------------------------------------------------------------
# ROTA: LISTAR MÁQUINAS (COM SUPORTE PARA CRIAÇÃO DE O.S.)
# -----------------------------------------------------------------------------
@app.route('/maquinas')
@login_required
def listar_maquinas():
    if current_user.role not in ['Administrador', 'Tecnico']:
        flash('Acesso restrito à equipe técnica.', 'danger')
        return redirect(url_for('dashboard'))

    q_codigo = request.args.get('codigo', '')
    q_descricao = request.args.get('descricao', '')
    q_linha = request.args.get('linha', '')

    query = Maquina.query
    if q_codigo:
        query = query.filter(Maquina.codigo.ilike(f'%{q_codigo}%'))
    if q_descricao:
        query = query.filter(Maquina.descricao.ilike(f'%{q_descricao}%'))
    if q_linha:
        query = query.filter(Maquina.linha.ilike(f'%{q_linha}%'))

    maquinas = query.order_by(Maquina.codigo).all()

    # --- NOVAS CONSULTAS: Alimenta os seletores do modal de Nova O.S. ---
    pecas_disponiveis = Item.query.order_by(Item.descricao).all()
    todas_maquinas = Maquina.query.order_by(Maquina.codigo).all()

    return render_template('maquinas.html',
                           maquinas=maquinas,
                           todas_maquinas=todas_maquinas,
                           pecas=pecas_disponiveis)
# -----------------------------------------------------------------------------
# ROTA: CADASTRAR NOVA MÁQUINA
# -----------------------------------------------------------------------------
@app.route('/maquina/nova', methods=['POST'])
@login_required
def nova_maquina():
    if current_user.role not in ['Administrador', 'Tecnico']:
        return "Acesso Negado", 403

    codigo = request.form.get('codigo')
    descricao = request.form.get('descricao')
    linha = request.form.get('linha')
    status = request.form.get('status', 'Operando')

    if Maquina.query.filter_by(codigo=codigo).first():
        flash(f'Erro: O código {codigo} já está cadastrado!', 'danger')
        return redirect(url_for('listar_maquinas'))

    nova = Maquina(codigo=codigo, descricao=descricao, linha=linha, status=status)
    db.session.add(nova)
    db.session.flush()

    if 'imagens' in request.files:
        arquivos = request.files.getlist('imagens')
        for arquivo in arquivos:
            if arquivo and arquivo.filename != '':
                nome_seguro = secure_filename(f"{nova.id}_{arquivo.filename}")
                arquivo.save(os.path.join(app.config['UPLOAD_MAQUINAS'], nome_seguro))

                nova_foto = MaquinaImagem(maquina_id=nova.id, caminho_arquivo=f"uploads/maquinas/{nome_seguro}")
                db.session.add(nova_foto)

    db.session.commit()
    flash(f'Máquina {codigo} cadastrada com sucesso!', 'success')
    return redirect(url_for('listar_maquinas'))


# -----------------------------------------------------------------------------
# ROTA: CADASTRAR NOVO ITEM
# -----------------------------------------------------------------------------
@app.route('/item/novo', methods=['POST'])
@login_required
def novo_item():
    sku = request.form.get('sku')
    descricao = request.form.get('descricao')
    categoria = request.form.get('categoria')
    localizacao = request.form.get('localizacao')
    fornecedor = request.form.get('fornecedor')
    preco = request.form.get('preco_unitario')

    preco_unitario = preco.replace(',', '.') if preco else 0.0
    estoque_minimo = request.form.get('estoque_minimo', 0)
    estoque_maximo = request.form.get('estoque_maximo', 0)

    novo = Item(
        sku=sku,
        descricao=descricao,
        categoria=categoria,
        localizacao=localizacao,
        fornecedor=fornecedor,
        preco_unitario=preco_unitario,
        estoque_minimo=int(estoque_minimo),
        estoque_maximo=int(estoque_maximo)
    )
    db.session.add(novo)
    db.session.commit()

    return redirect(url_for('listar_itens'))


# -----------------------------------------------------------------------------
# ROTA: CONTROLE DE ESTOQUE
# -----------------------------------------------------------------------------
@app.route('/estoque/movimentar', methods=['POST'])
@login_required
def movimentar_estoque():
    item_id = request.form.get('item_id')
    tipo = request.form.get('tipo')
    quantidade = int(request.form.get('quantidade'))
    nota_fiscal = request.form.get('nota_fiscal')
    os_id = request.form.get('os_id')

    if os_id == "":
        os_id = None

    item = Item.query.get_or_404(item_id)

    if tipo == 'Entrada':
        item.estoque_atual += quantidade
    elif tipo == 'Baixa':
        if quantidade > item.estoque_atual:
            flash('Erro: Quantidade de baixa maior que o estoque atual!', 'danger')
            return redirect(url_for('listar_itens'))
        item.estoque_atual -= quantidade

    nova_movimentacao = MovimentacaoEstoque(
        item_id=item.id,
        usuario_id=current_user.id,
        tipo=tipo,
        quantidade=quantidade,
        nota_fiscal=nota_fiscal,
        os_id=os_id
    )

    db.session.add(nova_movimentacao)
    db.session.commit()

    flash(f'{tipo} de {quantidade} unidades realizada com sucesso!', 'success')
    return redirect(url_for('listar_itens'))


if __name__ == '__main__':
    app.run(debug=True)