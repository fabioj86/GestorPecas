from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, Usuario, Item, Maquina, MovimentacaoEstoque, OrdemServico, AuditLog, ItemImagem
from config import Config
import os

app = Flask(__name__)
app.config.from_object(Config)

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

    # Verifica se já existe algum usuário no banco
    if not Usuario.query.first():
        # Se não existir, cria o usuário administrador padrão
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
# ROTA: LISTAR USUÁRIOS (Tela de Gerenciamento)
# -----------------------------------------------------------------------------
@app.route('/usuarios')
@login_required
def listar_usuarios():
    # BARREIRA DE SEGURANÇA: Verifica se é Administrador
    if current_user.role != 'Administrador':
        flash('Acesso negado: Área restrita para administradores.', 'danger')
        return redirect(url_for('dashboard'))

    # Busca todos os usuários no banco
    usuarios = Usuario.query.order_by(Usuario.id).all()
    return render_template('usuarios.html', usuarios=usuarios)


# -----------------------------------------------------------------------------
# ROTA: CADASTRAR NOVO USUÁRIO
# -----------------------------------------------------------------------------
@app.route('/usuario/novo', methods=['POST'])
@login_required
def novo_usuario():
    # BARREIRA DE SEGURANÇA NA ROTA DE GRAVAÇÃO
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    email = request.form.get('email')
    senha = request.form.get('password')
    role = request.form.get('role')

    # Validação: Verifica se o nome de usuário já existe no banco
    usuario_existente = Usuario.query.filter_by(username=username).first()
    if usuario_existente:
        flash('Erro: Este nome de usuário já está em uso no sistema.', 'danger')
        return redirect(url_for('listar_usuarios'))

    # Criptografa a senha digitada antes de salvar
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
# ROTA: DASHBOARD PRINCIPAL
# -----------------------------------------------------------------------------
@app.route('/')
@login_required
def dashboard():
    # Painel de Alertas: Filtra itens abaixo do nível crítico (Stock Mínimo)
    alertas_criticos = Item.query.filter(Item.estoque_atual <= Item.estoque_minimo).all()
    total_maquinas = Maquina.query.count()
    total_itens = Item.query.count()
    os_pendentes = OrdemServico.query.filter_by(status='Pendente').count()

    return render_template('paineldecontrole.html',
                           alertas=alertas_criticos,
                           total_maquinas=total_maquinas,
                           total_itens=total_itens,
                           os_pendentes=os_pendentes)


# -----------------------------------------------------------------------------
# ROTA: PESQUISA E CONSULTA DE ITENS
# -----------------------------------------------------------------------------
@app.route('/itens', methods=['GET'])
@login_required
def listar_itens():
    termo_busca = request.args.get('search', '')

    # Filtro avançado dinâmico
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


# Rota de API assíncrona (AJAX) para abrir a sub-rotina de detalhes do item
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
# ROTA: CADASTRAR NOVO ITEM
# -----------------------------------------------------------------------------
@app.route('/item/novo', methods=['POST'])
@login_required
def novo_item():
    # Coleta os dados do formulário
    sku = request.form.get('sku')
    descricao = request.form.get('descricao')
    categoria = request.form.get('categoria')
    localizacao = request.form.get('localizacao')
    fornecedor = request.form.get('fornecedor')
    preco = request.form.get('preco_unitario')

    # Tratamento básico para vírgulas no preço
    preco_unitario = preco.replace(',', '.') if preco else 0.0

    estoque_minimo = request.form.get('estoque_minimo', 0)
    estoque_maximo = request.form.get('estoque_maximo', 0)

    # Cria a peça principal no banco
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
    db.session.commit()  # Salvamos primeiro para gerar o ID do item

    # Tratamento das Múltiplas Imagens
    imagens = request.files.getlist('imagens')
    for imagem in imagens:
        if imagem and imagem.filename:
            # Segurança básica de nome de arquivo
            from werkzeug.utils import secure_filename
            filename = secure_filename(imagem.filename)

            # Verifica se a pasta static/uploads existe, se não, cria.
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            # Salva o arquivo fisicamente na pasta
            caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            imagem.save(caminho_completo)

            # Registra o caminho da imagem no banco de dados vinculada à peça
            nova_img = ItemImagem(item_id=novo.id, caminho_imagem=filename)
            db.session.add(nova_img)

    db.session.commit()

    flash('Nova peça cadastrada com sucesso!', 'success')
    return redirect(url_for('listar_itens'))


# -----------------------------------------------------------------------------
# ROTA: CONTROLE DE ESTOQUE (Entradas e Baixas)
# -----------------------------------------------------------------------------
@app.route('/estoque/movimentar', methods=['POST'])
@login_required
def movimentar_estoque():
    item_id = request.form.get('item_id')
    tipo = request.form.get('tipo')
    quantidade = int(request.form.get('quantidade'))
    nota_fiscal = request.form.get('nota_fiscal')
    os_id = request.form.get('os_id')

    # TRATAMENTO CRÍTICO: Se o campo vier vazio do formulário, converte para None
    # para não tentar salvar uma string vazia ("") na chave estrangeira
    if os_id == "":
        os_id = None
    elif os_id:
        # Verifica se a OS realmente existe no banco antes de prosseguir
        from models import OrdemServico  # Certifique-se de importar o modelo
        os_existe = OrdemServico.query.get(os_id)
        if not os_existe:
            flash(f'Erro: A Ordem de Serviço número {os_id} não existe no sistema.', 'danger')
            return redirect(url_for('listar_itens'))

    item = Item.query.get_or_404(item_id)

    # Restante do seu código de movimentação...
    if tipo == 'Entrada':
        item.estoque_atual += quantidade
    elif tipo == 'Baixa':
        if quantidade > item.estoque_atual:
            flash('Erro: Quantidade de baixa maior que o estoque atual!', 'danger')
            return redirect(url_for('listar_itens'))
        item.estoque_atual -= quantidade

    # Criação do registro de movimentação
    nova_movimentacao = MovimentacaoEstoque(
        item_id=item.id,
        usuario_id=current_user.id,
        tipo=tipo,
        quantidade=quantidade,
        nota_fiscal=nota_fiscal,
        os_id=os_id  # Agora ele vai como None ou como um ID válido
    )

    db.session.add(nova_movimentacao)
    db.session.commit()

    flash(f'{tipo} de {quantidade} unidades realizada com sucesso!', 'success')
    return redirect(url_for('listar_itens'))


# Se o ficheiro for executado diretamente, roda o servidor local
if __name__ == '__main__':
    app.run(debug=True)