from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, render_template_string
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
import os

# Importação consolidada de todos os modelos do banco de dados
from models import (
    db, Usuario, Item, Maquina, MovimentacaoEstoque,
    OrdemServico, AuditLog, ItemImagem, MaquinaImagem,
    OrdemServicoImagem, OrdemServicoItemPrevisto, ManutencaoProgramada
)
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# ----------------------------------------------------------------------------
# CONFIGURAÇÕES DE PASTAS DE UPLOAD
# ----------------------------------------------------------------------------
PASTA_UPLOAD_MAQUINAS = os.path.join('static', 'uploads', 'maquinas')
app.config['UPLOAD_MAQUINAS'] = PASTA_UPLOAD_MAQUINAS
os.makedirs(PASTA_UPLOAD_MAQUINAS, exist_ok=True)

PASTA_UPLOAD_OS = os.path.join('static', 'uploads', 'os')
app.config['UPLOAD_OS'] = PASTA_UPLOAD_OS
os.makedirs(PASTA_UPLOAD_OS, exist_ok=True)

PASTA_UPLOAD_ITENS = os.path.join('static', 'uploads')
app.config['UPLOAD_ITENS'] = PASTA_UPLOAD_ITENS
os.makedirs(PASTA_UPLOAD_ITENS, exist_ok=True)

# Inicialização do Banco de Dados e Login Manager
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# ----------------------------------------------------------------------------
# ROTAS DE AUTENTICAÇÃO
# ----------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos!', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ----------------------------------------------------------------------------
# PAINEL DE CONTROLE (DASHBOARD)
# ----------------------------------------------------------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    total_itens = Item.query.count()
    total_maquinas = Maquina.query.filter_by(status='Operando').count()
    os_pendentes = OrdemServico.query.filter_by(status='Pendente').count()

    hoje = date.today()
    os_em_atraso = OrdemServico.query.filter(OrdemServico.status == 'Pendente',
                                             OrdemServico.prazo_previsto < hoje).all()

    prazo_critico = hoje + timedelta(days=3)
    os_no_prazo_critico = OrdemServico.query.filter(
        OrdemServico.status == 'Pendente',
        OrdemServico.prazo_previsto >= hoje,
        OrdemServico.prazo_previsto <= prazo_critico
    ).all()

    return render_template('paineldecontrole.html',
                           total_itens=total_itens,
                           total_maquinas=total_maquinas,
                           os_pendentes=os_pendentes,
                           os_em_atraso=os_em_atraso,
                           os_no_prazo_critico=os_no_prazo_critico)


# ----------------------------------------------------------------------------
# GESTÃO DE ESTOQUE e ALMOXARIFADO
# ----------------------------------------------------------------------------
@app.route('/itens')
@login_required
def listar_itens():
    termo_busca = request.args.get('search', '')
    query = Item.query
    if termo_busca:
        query = query.filter(
            (Item.sku.ilike(f"%{termo_busca}%")) |
            (Item.descricao.ilike(f"%{termo_busca}%")) |
            (Item.categoria.ilike(f"%{termo_busca}%")) |
            (Item.localizacao.ilike(f"%{termo_busca}%"))
        )
    itens = query.all()
    return render_template('itens.html', itens=itens, termo_busca=termo_busca)


@app.route('/item/novo', methods=['POST'])
@login_required
def item_novo():
    sku = request.form.get('sku')
    categoria = request.form.get('categoria')
    descricao = request.form.get('descricao')
    fornecedor = request.form.get('fornecedor')
    preco_unitario = request.form.get('preco_unitario', '0')
    localizacao = request.form.get('localizacao')
    estoque_minimo = request.form.get('estoque_minimo', 0)
    estoque_maximo = request.form.get('estoque_maximo', 0)

    try:
        preco_unitario = float(preco_unitario.replace(',', '.'))
    except ValueError:
        preco_unitario = 0.0

    novo_item = Item(
        sku=sku, categoria=categoria, descricao=descricao,
        fornecedor=fornecedor, preco_unitario=preco_unitario,
        localizacao=localizacao, estoque_minimo=int(estoque_minimo or 0),
        estoque_maximo=int(estoque_maximo or 0), estoque_atual=0
    )
    db.session.add(novo_item)
    db.session.commit()

    imagens = request.files.getlist('imagens')
    for img in imagens:
        if img and img.filename:
            nome_seguro = secure_filename(f"{novo_item.id}_{img.filename}")
            img.save(os.path.join(app.config['UPLOAD_ITENS'], nome_seguro))
            nova_img = ItemImagem(item_id=novo_item.id, caminho_arquivo=nome_seguro)
            db.session.add(nova_img)

    db.session.commit()
    flash('Peça cadastrada com sucesso!', 'success')
    return redirect(url_for('listar_itens'))


@app.route('/api/item/<int:item_id>')
@login_required
def api_item(item_id):
    item = Item.query.get_or_404(item_id)
    imagens = [img.caminho_arquivo for img in item.imagens]
    return jsonify({
        'sku': item.sku,
        'descricao': item.descricao,
        'categoria': item.categoria,
        'localizacao': item.localizacao,
        'preco': item.preco_unitario or 0.0,
        'estoque_atual': item.estoque_atual,
        'estoque_minimo': item.estoque_minimo,
        'estoque_maximo': item.estoque_maximo,
        'imagens': imagens
    })


@app.route('/estoque/movimentar', methods=['POST'])
@login_required
def estoque_movimentar():
    item_id = request.form.get('item_id')
    tipo = request.form.get('tipo')
    quantidade = int(request.form.get('quantidade', 0))
    nota_fiscal = request.form.get('nota_fiscal')
    os_id = request.form.get('os_id')

    item = Item.query.get_or_404(item_id)
    if tipo == 'Entrada':
        item.estoque_atual += quantidade
    elif tipo == 'Baixa':
        if item.estoque_atual < quantidade:
            flash('Quantidade insuficiente em estoque para realizar a baixa!', 'danger')
            return redirect(url_for('listar_itens'))
        item.estoque_atual -= quantidade

    mov = MovimentacaoEstoque(
        item_id=item_id,
        usuario_id=current_user.id,
        tipo=tipo,
        quantidade=quantidade,
        nota_fiscal=nota_fiscal,
        ordem_servico_id=int(os_id) if os_id else None,
        data_movimentacao=datetime.utcnow()
    )
    db.session.add(mov)
    db.session.commit()
    flash(f'Movimentação de {tipo} registrada com sucesso!', 'success')
    return redirect(url_for('listar_itens'))


@app.route('/itens/relatorio')
@login_required
def imprimir_relatorio_itens():
    # Captura o termo de busca caso o estoque esteja filtrado na tela
    termo_busca = request.args.get('search', '')

    query = Item.query
    if termo_busca:
        query = query.filter(
            (Item.sku.ilike(f'%{termo_busca}%')) |
            (Item.descricao.ilike(f'%{termo_busca}%')) |
            (Item.categoria.ilike(f'%{termo_busca}%')) |
            (Item.localizacao.ilike(f'%{termo_busca}%'))
        )

    itens = query.order_by(Item.descricao).all()
    data_emissao = datetime.now().strftime('%d/%m/%Y %H:%M')

    return render_template('relatorio_itens.html', itens=itens, data_emissao=data_emissao, termo_busca=termo_busca)

# ----------------------------------------------------------------------------
# GESTÃO DE EQUIPAMENTOS (MÁQUINAS)
# ----------------------------------------------------------------------------
@app.route('/maquinas')
@login_required
def listar_maquinas():
    codigo = request.args.get('codigo', '')
    descricao = request.args.get('descricao', '')
    linha = request.args.get('linha', '')

    query = Maquina.query
    if codigo:
        query = query.filter(Maquina.codigo.ilike(f"%{codigo}%"))
    if descricao:
        query = query.filter(Maquina.descricao.ilike(f"%{descricao}%"))
    if linha:
        query = query.filter(Maquina.linha.ilike(f"%{linha}%"))

    maquinas = query.all()
    todas_maquinas = Maquina.query.all()
    pecas = Item.query.all()
    return render_template('maquinas.html', maquinas=maquinas, todas_maquinas=todas_maquinas, pecas=pecas)


@app.route('/maquina/nova', methods=['POST'])
@login_required
def maquina_nova():
    codigo = request.form.get('codigo')
    descricao = request.form.get('descricao')
    linha = request.form.get('linha')
    status = request.form.get('status', 'Operando')

    nova_mq = Maquina(codigo=codigo, descricao=descricao, linha=linha, status=status)
    db.session.add(nova_mq)
    db.session.commit()

    imagens = request.files.getlist('imagens')
    for img in imagens:
        if img and img.filename:
            nome_seguro = secure_filename(f"{nova_mq.id}_{img.filename}")
            img.save(os.path.join(app.config['UPLOAD_MAQUINAS'], nome_seguro))
            nova_img = MaquinaImagem(maquina_id=nova_mq.id, caminho_arquivo=f"uploads/maquinas/{nome_seguro}")
            db.session.add(nova_img)

    db.session.commit()
    flash('Máquina cadastrada com sucesso!', 'success')
    return redirect(url_for('listar_maquinas'))


@app.route('/maquina/editar/<int:id>', methods=['POST'])
@login_required
def maquina_editar(id):
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('listar_maquinas'))
    mq = Maquina.query.get_or_404(id)
    mq.codigo = request.form.get('codigo')
    mq.descricao = request.form.get('descricao')
    mq.linha = request.form.get('linha')
    mq.status = request.form.get('status')
    db.session.commit()
    flash('Máquina atualizada com sucesso!', 'success')
    return redirect(url_for('listar_maquinas'))


@app.route('/maquina/excluir/<int:id>', methods=['POST'])
@login_required
def maquina_excluir(id):
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('listar_maquinas'))
    mq = Maquina.query.get_or_404(id)
    for img in mq.imagens:
        try:
            os.remove(os.path.join('static', img.caminho_arquivo))
        except:
            pass
        db.session.delete(img)
    db.session.delete(mq)
    db.session.commit()
    flash('Equipamento excluído com sucesso!', 'success')
    return redirect(url_for('listar_maquinas'))


@app.route('/maquinas/finalizar-manutencao', methods=['POST'])
@login_required
def finalizar_manutencao():
    maquina_id = request.form.get('maquina_id')
    detalhes = request.form.get('detalhes')

    maquina = Maquina.query.get_or_404(maquina_id)
    maquina.status = 'Operando'

    os_aberta = OrdemServico.query.filter_by(maquina_id=maquina_id, status='Pendente').first()
    if os_aberta:
        os_aberta.status = 'Concluída'
        os_aberta.data_conclusao = datetime.utcnow()

    log = AuditLog(usuario_id=current_user.id, acao="Finalizar Manutenção",
                   detalhes=f"Máquina {maquina.codigo}: {detalhes}")
    db.session.add(log)
    db.session.commit()
    flash('Manutenção finalizada com sucesso!', 'success')
    return redirect(url_for('listar_maquinas'))


@app.route('/maquinas/prorrogagar-manutencao', methods=['POST'])
@login_required
def prorrogagar_manutencao():
    maquina_id = request.form.get('maquina_id')
    detalhes = request.form.get('detalhes')
    novo_prazo_str = request.form.get('novo_prazo')

    os_aberta = OrdemServico.query.filter_by(maquina_id=maquina_id, status='Pendente').first()
    if os_aberta and novo_prazo_str:
        os_aberta.prazo_previsto = datetime.strptime(novo_prazo_str, '%Y-%m-%d').date()

    log = AuditLog(usuario_id=current_user.id, acao="Prorrogar Manutenção",
                   detalhes=f"Máquina ID {maquina_id}: {detalhes}. Novo prazo: {novo_prazo_str}")
    db.session.add(log)
    db.session.commit()
    flash('Prazo de manutenção prorrogado com sucesso!', 'success')
    return redirect(url_for('listar_maquinas'))


# ----------------------------------------------------------------------------
# ORDENS DE SERVIÇO
# ----------------------------------------------------------------------------
@app.route('/ordens')
@login_required
def listar_ordens():
    ordens = OrdemServico.query.all()
    maquinas = Maquina.query.all()
    pecas = Item.query.all()
    return render_template('ordens.html', ordens=ordens, maquinas=maquinas, pecas=pecas)


@app.route('/ordem/nova', methods=['POST'])
@login_required
def ordem_nova():
    maquina_id = request.form.get('maquina_id')
    prazo_str = request.form.get('prazo_previsto')
    descricao_defeito = request.form.get('descricao_defeito')

    prazo_previsto = datetime.strptime(prazo_str, '%Y-%m-%d').date()

    nova_os = OrdemServico(
        maquina_id=maquina_id,
        descricao_defeito=descricao_defeito,
        prazo_previsto=prazo_previsto,
        status='Pendente',
        data_abertura=datetime.utcnow()
    )
    db.session.add(nova_os)
    db.session.flush()

    maquina = Maquina.query.get(maquina_id)
    if maquina:
        maquina.status = 'Defeito'

    pecas_sku = request.form.getlist('pecas_sku[]')
    pecas_qtd = request.form.getlist('pecas_qtd[]')

    for sku, qtd in zip(pecas_sku, pecas_qtd):
        if sku and qtd:
            item = Item.query.filter_by(sku=sku).first()
            if item:
                previsto = OrdemServicoItemPrevisto(
                    ordem_servico_id=nova_os.id,
                    item_id=item.id,
                    quantidade_prevista=int(qtd)
                )
                db.session.add(previsto)

    imagens = request.files.getlist('imagens')
    for img in imagens:
        if img and img.filename:
            nome_seguro = secure_filename(f"os_{nova_os.id}_{img.filename}")
            img.save(os.path.join(app.config['UPLOAD_OS'], nome_seguro))
            nova_img = OrdemServicoImagem(ordem_servico_id=nova_os.id, caminho_arquivo=f"uploads/os/{nome_seguro}")
            db.session.add(nova_img)

    db.session.commit()
    flash('Ordem de Serviço aberta com sucesso!', 'success')
    return redirect(request.referrer or url_for('listar_ordens'))


# ----------------------------------------------------------------------------
# GESTÃO DE USUÁRIOS
# ----------------------------------------------------------------------------
@app.route('/usuarios')
@login_required
def listar_usuarios():
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('dashboard'))
    usuarios = Usuario.query.all()
    return render_template('usuarios.html', usuarios=usuarios)


@app.route('/usuario/novo', methods=['POST'])
@login_required
def usuario_novo():
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('dashboard'))
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')

    hash_senha = generate_password_hash(password)
    novo_usuario = Usuario(username=username, email=email, password_hash=hash_senha, role=role)
    db.session.add(novo_usuario)
    db.session.commit()
    flash('Usuário criado com sucesso!', 'success')
    return redirect(url_for('listar_usuarios'))


# ----------------------------------------------------------------------------
# CALENDÁRIO / CRONOGRAMA DE MANUTENÇÃO
# ----------------------------------------------------------------------------
@app.route('/manutencao/calendario')
@login_required
def calendario():
    maquinas = Maquina.query.all()
    return render_template('calendario.html', maquinas=maquinas)


@app.route('/api/manutencoes/eventos')
@login_required
def api_eventos():
    status_filtro = request.args.get('status', '')
    query = ManutencaoProgramada.query
    if status_filtro:
        query = query.filter_by(status=status_filtro)
    programacoes = query.all()

    eventos = []
    for p in programacoes:
        eventos.append({
            'id': p.id,
            'title': f"[{p.status}] {p.maquina.codigo}",
            'start': p.data_programada.isoformat(),
            'extendedProps': {
                'maquina': p.maquina.descricao,
                'linha': p.maquina.linha or 'N/A',
                'descricao': p.descricao_atividades,
                'status': p.status,
                'os_id': p.os_gerada_id or 'Não gerada'
            }
        })
    return jsonify(eventos)


@app.route('/manutencoes/programar', methods=['POST'])
@login_required
def programar_manutencao():
    if current_user.role not in ['Administrador', 'Tecnico']:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('dashboard'))

    maquina_id = request.form.get('maquina_id')
    descricao = request.form.get('descricao_atividades')
    data_str = request.form.get('data_programada')
    gerar_os = request.form.get('gerar_os')

    data_programada = datetime.strptime(data_str, '%Y-%m-%d').date()

    nova_programacao = ManutencaoProgramada(
        maquina_id=maquina_id,
        descricao_atividades=descricao,
        data_programada=data_programada,
        status='Pendente'
    )
    db.session.add(nova_programacao)
    db.session.flush()

    if gerar_os == 'sim':
        nova_os = OrdemServico(
            maquina_id=maquina_id,
            descricao_defeito=f"[PREVENTIVA PROGRAMADA] {descricao}",
            prazo_previsto=data_programada,
            status='Pendente',
            data_abertura=datetime.utcnow()
        )
        db.session.add(nova_os)
        db.session.flush()
        nova_programacao.os_gerada_id = nova_os.id

        maquina = Maquina.query.get(maquina_id)
        if maquina:
            maquina.status = 'Defeito'

    db.session.commit()
    flash('Manutenção programada com sucesso!', 'success')
    return redirect(url_for('calendario'))


# ----------------------------------------------------------------------------
# BACKEND: NOVAS ROTAS DEDICADAS PARA IMPRESSÃO DE RELATÓRIOS ISOLADOS
# ----------------------------------------------------------------------------
@app.route('/relatorio/itens')
@login_required
def relatorio_itens():
    search = request.args.get('search', '')
    query = Item.query
    if search:
        query = query.filter(
            (Item.sku.ilike(f"%{search}%")) |
            (Item.descricao.ilike(f"%{search}%")) |
            (Item.categoria.ilike(f"%{search}%")) |
            (Item.localizacao.ilike(f"%{search}%"))
        )
    itens = query.all()

    html_template = """
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>Relatório de Estoque - GestorPecas</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding: 30px; font-family: sans-serif; background-color: #fff; }
            .report-header { border-bottom: 2px solid #333; margin-bottom: 20px; padding-bottom: 10px; }
            @media print { .no-print { display: none; } }
        </style>
    </head>
    <body>
        <div class="d-flex justify-content-between align-items-center report-header">
            <div>
                <h2>GestorPecas - Relatório de Estoque Atual</h2>
                <p class="text-muted mb-0">Filtro aplicado: {% if search %}"{{ search }}"{% else %}Nenhum (Todos os itens){% endif %}</p>
            </div>
            <div class="text-end">
                <button onclick="window.print()" class="btn btn-primary btn-sm no-print">Imprimir / Salvar PDF</button>
                <p class="small text-muted mt-1 mb-0">Gerado em: {{ data_hora }}</p>
            </div>
        </div>
        <table class="table table-bordered table-striped">
            <thead class="table-dark">
                <tr>
                    <th>Código (SKU)</th>
                    <th>Descrição</th>
                    <th>Categoria</th>
                    <th>Localização</th>
                    <th>Estoque Mínimo</th>
                    <th>Estoque Atual</th>
                </tr>
            </thead>
            <tbody>
                {% for item in itens %}
                <tr>
                    <td><strong>{{ item.sku }}</strong></td>
                    <td>{{ item.descricao }}</td>
                    <td>{{ item.categoria or 'N/A' }}</td>
                    <td>{{ item.localizacao or 'N/A' }}</td>
                    <td>{{ item.estoque_minimo }}</td>
                    <td>
                        {% if item.estoque_atual <= item.estoque_minimo %}
                            <span class="text-danger fw-bold">{{ item.estoque_atual }} (Crítico)</span>
                        {% else %}
                            <span class="text-success fw-bold">{{ item.estoque_atual }}</span>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="6" class="text-center text-muted">Nenhum item localizado com o filtro aplicado.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <script>window.onload = function() { window.print(); }</script>
    </body>
    </html>
    """
    return render_template_string(html_template, itens=itens, search=search,
                                  data_hora=datetime.now().strftime('%d/%m/%Y às %H:%M:%S'))


@app.route('/relatorio/maquinas')
@login_required
def relatorio_maquinas():
    codigo = request.args.get('codigo', '')
    descricao = request.args.get('descricao', '')
    linha = request.args.get('linha', '')

    query = Maquina.query
    if codigo:
        query = query.filter(Maquina.codigo.ilike(f"%{codigo}%"))
    if descricao:
        query = query.filter(Maquina.descricao.ilike(f"%{descricao}%"))
    if linha:
        query = query.filter(Maquina.linha.ilike(f"%{linha}%"))

    maquinas = query.all()

    html_template = """
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>Relatório do Parque de Máquinas - GestorPecas</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding: 30px; font-family: sans-serif; background-color: #fff; }
            .report-header { border-bottom: 2px solid #333; margin-bottom: 20px; padding-bottom: 10px; }
            @media print { .no-print { display: none; } }
        </style>
    </head>
    <body>
        <div class="d-flex justify-content-between align-items-center report-header">
            <div>
                <h2>GestorPecas - Status do Parque de Máquinas</h2>
                <p class="text-muted mb-0">Filtros ativos — Código: "{{ codigo }}", Descrição: "{{ descricao }}", Linha: "{{ linha }}"</p>
            </div>
            <div class="text-end">
                <button onclick="window.print()" class="btn btn-primary btn-sm no-print">Imprimir / Salvar PDF</button>
                <p class="small text-muted mt-1 mb-0">Gerado em: {{ data_hora }}</p>
            </div>
        </div>
        <table class="table table-bordered table-striped text-center">
            <thead class="table-dark">
                <tr>
                    <th>Código</th>
                    <th class="text-start">Descrição / Equipamento</th>
                    <th>Linha / Setor</th>
                    <th>Status Operacional</th>
                </tr>
            </thead>
            <tbody>
                {% for m in maquinas %}
                <tr>
                    <td class="fw-bold">{{ m.codigo }}</td>
                    <td class="text-start">{{ m.descricao }}</td>
                    <td>{{ m.linha or 'N/A' }}</td>
                    <td>
                        {% if m.status == 'Operando' %}
                            <span class="text-success fw-bold">✔ Operando</span>
                        {% else %}
                            <span class="text-danger fw-bold">✘ Defeito / Parada</span>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="4" class="text-center text-muted">Nenhum equipamento localizado.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <script>window.onload = function() { window.print(); }</script>
    </body>
    </html>
    """
    return render_template_string(html_template, maquinas=maquinas, codigo=codigo, descricao=descricao, linha=linha,
                                  data_hora=datetime.now().strftime('%d/%m/%Y às %H:%M:%S'))


@app.route('/relatorio/ordens')
@login_required
def relatorio_ordens():
    ordens = OrdemServico.query.all()

    html_template = """
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>Histórico de O.S. - GestorPecas</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding: 30px; font-family: sans-serif; background-color: #fff; }
            .report-header { border-bottom: 2px solid #333; margin-bottom: 20px; padding-bottom: 10px; }
            @media print { .no-print { display: none; } }
        </style>
    </head>
    <body>
        <div class="d-flex justify-content-between align-items-center report-header">
            <div>
                <h2>GestorPecas - Histórico Geral de Ordens de Serviço</h2>
                <p class="text-muted mb-0">Controle integrado e histórico de manutenções executadas</p>
            </div>
            <div class="text-end">
                <button onclick="window.print()" class="btn btn-primary btn-sm no-print">Imprimir / Salvar PDF</button>
                <p class="small text-muted mt-1 mb-0">Gerado em: {{ data_hora }}</p>
            </div>
        </div>
        <table class="table table-bordered table-striped">
            <thead class="table-dark text-center">
                <tr>
                    <th>Nº O.S.</th>
                    <th>Máquina / Equipamento</th>
                    <th>Defeito / Escopo Relatado</th>
                    <th>Prazo Limite</th>
                    <th>Status</th>
                    <th>Insumos Mapeados</th>
                </tr>
            </thead>
            <tbody>
                {% for os in ordens %}
                <tr>
                    <td class="text-center fw-bold">#{{ os.id }}</td>
                    <td><strong>{{ os.maquina.codigo }}</strong> - {{ os.maquina.descricao }}</td>
                    <td>{{ os.descricao_defeito }}</td>
                    <td class="text-center">{{ os.prazo_previsto.strftime('%d/%m/%Y') }}</td>
                    <td class="text-center">
                        {% if os.status == 'Pendente' %}
                            <span class="text-warning fw-bold">Pendente</span>
                        {% else %}
                            <span class="text-success fw-bold">Concluída</span>
                        {% endif %}
                    </td>
                    <td>
                        {% for p in os.itens_previstos %}
                            <small>• {{ p.item.descricao }} (Qtd: {{ p.quantidade_prevista }})</small><br>
                        {% else %}
                            <small class="text-muted">Nenhum</small>
                        {% endfor %}
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="6" class="text-center text-muted">Nenhuma ordem de serviço registrada no histórico.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <script>window.onload = function() { window.print(); }</script>
    </body>
    </html>
    """
    return render_template_string(html_template, ordens=ordens,
                                  data_hora=datetime.now().strftime('%d/%m/%Y às %H:%M:%S'))


if __name__ == '__main__':
    app.run(debug=True)