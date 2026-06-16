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
# INJETOR DE CONTEXTO GLOBAL (Para Modais e Dados Compartilhados)
# ----------------------------------------------------------------------------
@app.context_processor
def inject_dados_globais_modais():
    """
    Garante que as listagens completas de peças e máquinas estejam disponíveis
    em qualquer página que utilize os modais globais da barra de navegação/base.
    """
    if current_user.is_authenticated:
        todas_pecas = Item.query.order_by(Item.descricao).all()
        todas_maquinas = Maquina.query.filter_by(ativo=True).order_by(Maquina.codigo).all()
        return dict(pecas=todas_pecas, maquinas_globais=todas_maquinas)
    return dict(pecas=[], maquinas_globais=[])


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

    alertas = Item.query.filter(Item.estoque_atual <= Item.estoque_minimo).all()

    return render_template('paineldecontrole.html',
                           total_itens=total_itens,
                           total_maquinas=total_maquinas,
                           os_pendentes=os_pendentes,
                           os_em_atraso=os_em_atraso,
                           os_atrasadas=os_em_atraso,
                           os_no_prazo_critico=os_no_prazo_critico,
                           alertas=alertas)


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

    if Item.query.filter_by(sku=sku).first():
        flash(f'Erro: O código (SKU) "{sku}" já está cadastrado no sistema!', 'danger')
        return redirect(url_for('listar_itens'))

    try:
        preco_unitario = float(preco_unitario.replace(',', '.'))
    except ValueError:
        preco_unitario = 0.0

    try:
        novo_item = Item(
            sku=sku, categoria=categoria, descricao=descricao,
            fornecedor=fornecedor, preco_unitario=preco_unitario,
            localizacao=localizacao, estoque_minimo=int(estoque_minimo or 0),
            estoque_maximo=int(estoque_maximo or 0), estoque_atual=0
        )
        db.session.add(novo_item)
        db.session.flush()

        imagens = request.files.getlist('imagens')
        for img in imagens:
            if img and img.filename:
                nome_seguro = secure_filename(f"{novo_item.id}_{img.filename}")
                caminho_arquivo = os.path.join(app.config['UPLOAD_ITENS'], nome_seguro)
                img.save(caminho_arquivo)

                nova_img = ItemImagem(item_id=novo_item.id, caminho_imagem=nome_seguro)
                db.session.add(nova_img)

        db.session.commit()
        flash('Peça cadastrada com sucesso!', 'success')
        return redirect(url_for('listar_itens'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao cadastrar a peça: {str(e)}', 'danger')
        return redirect(url_for('listar_itens'))


@app.route('/api/item/<int:item_id>')
@login_required
def api_item(item_id):
    item = Item.query.get_or_404(item_id)
    imagens = [f"uploads/{img.caminho_imagem}" for img in item.imagens]
    preco = float(item.preco_unitario) if item.preco_unitario else 0.0

    return jsonify({
        'sku': item.sku,
        'descricao': item.descricao,
        'categoria': item.categoria or '',
        'localizacao': item.localizacao or '',
        'preco': preco,
        'estoque_atual': item.estoque_atual,
        'estoque_minimo': item.estoque_minimo,
        'estoque_maximo': item.estoque_maximo,
        'imagens': imagens,
        'fornecedor': item.fornecedor or ''
    })


@app.route('/item/editar', methods=['POST'])
@login_required
def item_editar():
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('listar_itens'))

    item_id = request.form.get('item_id')
    item = Item.query.get_or_404(item_id)

    try:
        item.descricao = request.form.get('descricao')
        item.categoria = request.form.get('categoria')
        item.fornecedor = request.form.get('fornecedor')
        item.localizacao = request.form.get('localizacao')

        try:
            preco = float(request.form.get('preco_unitario', '0').replace(',', '.'))
            item.preco_unitario = preco
        except ValueError:
            item.preco_unitario = 0.0

        item.estoque_minimo = int(request.form.get('estoque_minimo', 0))
        item.estoque_maximo = int(request.form.get('estoque_maximo', 0))

        imagens = request.files.getlist('imagens')
        if imagens and imagens[0].filename:
            for img in imagens:
                if img and img.filename:
                    nome_seguro = secure_filename(f"{item.id}_{img.filename}")
                    img.save(os.path.join(app.config['UPLOAD_ITENS'], nome_seguro))
                    nova_img = ItemImagem(item_id=item.id, caminho_imagem=nome_seguro)
                    db.session.add(nova_img)

        db.session.commit()
        flash('Peça updated com sucesso!', 'success')
        return redirect(url_for('listar_itens'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar a peça: {str(e)}', 'danger')
        return redirect(url_for('listar_itens'))


@app.route('/item/excluir/<int:item_id>', methods=['POST'])
@login_required
def item_excluir(item_id):
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('listar_itens'))

    item = Item.query.get_or_404(item_id)

    try:
        for img in item.imagens:
            caminho_arquivo = os.path.join('static', img.caminho_imagem)
            try:
                if os.path.exists(caminho_arquivo):
                    os.remove(caminho_arquivo)
            except:
                pass
            db.session.delete(img)

        MovimentacaoEstoque.query.filter_by(item_id=item_id).delete()
        db.session.delete(item)
        db.session.commit()

        flash('Peça excluída com sucesso!', 'success')
        return redirect(url_for('listar_itens'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir a peça: {str(e)}', 'danger')
        return redirect(url_for('listar_itens'))


@app.route('/estoque/movimentar', methods=['POST'])
@login_required
def estoque_movimentar():
    item_id = request.form.get('item_id')
    tipo = request.form.get('tipo')
    quantidade = int(request.form.get('quantidade', 0))
    nota_fiscal = request.form.get('nota_fiscal')
    os_id = request.form.get('os_id')
    item = Item.query.get_or_404(item_id)

    if not os_id or os_id.strip() == '':
        os_id = None

    if os_id is not None:
        os_existe = OrdemServico.query.get(os_id)
        if not os_existe:
            flash("OS inválida", "danger")
            return redirect(request.referrer or url_for('listar_itens'))

    try:
        nova_movimentacao = MovimentacaoEstoque(
            item_id=item.id,
            usuario_id=current_user.id,
            tipo=tipo,
            quantidade=quantidade,
            os_id=os_id,
        )

        if tipo == 'Entrada':
            item.estoque_atual += quantidade
        elif tipo == 'Baixa':
            item.estoque_atual -= quantidade

        db.session.add(nova_movimentacao)
        db.session.commit()

        flash("Movimentação de estoque registrada com sucesso!", "success")
        return redirect(url_for('listar_itens'))

    except Exception as e:
        db.session.rollback()
        flash("Erro interno ao salvar os dados.", "danger")
        return redirect(request.referrer or url_for('listar_itens'))


@app.route('/itens/relatorio')
@login_required
def imprimir_relatorio_itens():
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


@app.route('/ordens/relatorio')
@login_required
def relatorio_ordens():
    # Busca todas as ordens de serviço cadastradas para o relatório
    ordens = OrdemServico.query.order_by(OrdemServico.id.desc()).all()

    html_template = """
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>Relatório de Ordens de Serviço</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            @media print { .no-print { display: none; } }
        </style>
    </head>
    <body class="container mt-4">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h2>Relatório de Ordens de Serviço (Manutenção)</h2>
            <button onclick="window.print()" class="btn btn-success no-print">Imprimir / Salvar PDF</button>
        </div>
        <table class="table table-bordered table-striped">
            <thead class="table-dark">
                <tr>
                    <th>Nº O.S.</th>
                    <th>Equipamento</th>
                    <th>Defeito Relatado</th>
                    <th>Prazo Previsto</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for os in ordens %}
                <tr>
                    <td>#{{ os.id }}</td>
                    <td>{{ os.maquina.codigo }} - {{ os.maquina.descricao }}</td>
                    <td>{{ os.descricao_defeito }}</td>
                    <td>{{ os.prazo_previsto.strftime('%d/%m/%Y') }}</td>
                    <td>{{ os.status }}</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="5" class="text-center">Nenhuma ordem encontrada.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """
    return render_template_string(html_template, ordens=ordens)

# ----------------------------------------------------------------------------
# GESTÃO DE EQUIPAMENTOS (MÁQUINAS)
# ----------------------------------------------------------------------------
@app.route('/maquinas')
@login_required
def listar_maquinas():
    codigo = request.args.get('codigo', '')
    descricao = request.args.get('descricao', '')
    linha = request.args.get('linha', '')
    incluir_inativos = request.args.get('incluir_inativos') == 'true'

    query = Maquina.query

    if not incluir_inativos:
        query = query.filter(Maquina.ativo == True)

    if codigo:
        query = query.filter(Maquina.codigo.ilike(f"%{codigo}%"))
    if descricao:
        query = query.filter(Maquina.descricao.ilike(f"%{descricao}%"))
    if linha:
        query = query.filter(Maquina.linha.ilike(f"%{linha}%"))

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(Maquina.id.desc()).paginate(page=page, per_page=10, error_out=False)
    maquinas = pagination.items

    return render_template('maquinas.html', maquinas=maquinas, pagination=pagination)

@app.route('/relatorio/maquinas')
@login_required
def relatorio_maquinas():
    # 1. Captura os parâmetros enviados pela URL
    codigo = request.args.get('codigo', '')
    descricao = request.args.get('descricao', '')
    linha = request.args.get('linha', '')
    incluir_inativos = request.args.get('incluir_inativos', 'false')
    agora = datetime.now()

    # 2. Inicia a Query base do SQLAlchemy
    query = Maquina.query

    # 3. Aplica os filtros de busca textuais (preservando o que já funcionava)
    if codigo:
        query = query.filter(Maquina.codigo.ilike(f'%{codigo}%'))
    if descricao:
        query = query.filter(Maquina.descricao.ilike(f'%{descricao}%'))
    if linha:
        # Adapte para 'linha_producao' se o seu modelo usar esse nome
        if hasattr(Maquina, 'linha'):
            query = query.filter(Maquina.linha.ilike(f'%{linha}%'))
        elif hasattr(Maquina, 'linha_producao'):
            query = query.filter(Maquina.linha_producao.ilike(f'%{linha}%'))

    # 4. APLICANDO O FILTRO DO SWITCH (CORREÇÃO SOLICITADA):
    # Se 'incluir_inativos' não for true, filtra para trazer APENAS quem está ativo
    if incluir_inativos != 'true':
        # Adapte 'Operando' ou 'Ativa' de acordo com o padrão do seu banco de dados
        query = query.filter(Maquina.status == 'Operando')

    # 5. Executa a busca final ordenada
    maquinas_filtradas = query.order_by(Maquina.codigo).all()

    # 6. Renderiza o seu template de relatório padrão passando a lista filtrada
    # (Mantenha o nome do seu template de relatório atual, ex: 'relatorio_maquinas.html')
    return render_template('relatorio_manutencao.html',
                           maquinas=maquinas_filtradas,
                           data_atual=agora)

@app.route('/api/maquinas/<int:maquina_id>')
@login_required
def api_detalhes_maquina(maquina_id):
    maquina = Maquina.query.get_or_404(maquina_id)

    # Descobre dinamicamente qual nome de atributo armazena a linha/setor
    linha_val = 'Não informada'
    if hasattr(maquina, 'linha'):
        linha_val = maquina.linha
    elif hasattr(maquina, 'linha_producao'):
        linha_val = maquina.linha_producao

    # Descobre dinamicamente qual nome de atributo armazena o histórico de O.S.
    historico_os = []
    atributos_busca = ['ordens_servico', 'ordens', 'manutencoes', 'os']
    relacionamento_encontrado = None

    for attr in atributos_busca:
        if hasattr(maquina, attr):
            relacionamento_encontrado = getattr(maquina, attr)
            break

    # Se encontrou o histórico, processa com segurança
    if relacionamento_encontrado:
        try:
            for os in relacionamento_encontrado:
                # Evita quebra caso prazos ou descrições estejam nulos
                dt_prazo = os.prazo_previsto.strftime('%d/%m/%Y') if hasattr(os,
                                                                             'prazo_previsto') and os.prazo_previsto else 'N/A'
                desc = os.descricao_defeito if hasattr(os, 'descricao_defeito') else (
                    os.descricao if hasattr(os, 'descricao') else 'Sem descrição')

                historico_os.append({
                    'id': os.id,
                    'descricao': desc,
                    'data': dt_prazo,
                    'status': os.status if hasattr(os, 'status') else 'Pendente'
                })
        except Exception:
            pass  # Garante que mesmo com erro em alguma O.S., a tela abra

    # Formata a resposta JSON final
    return jsonify({
        'id': maquina.id,
        'codigo': maquina.codigo,
        'descricao': maquina.descricao,
        'linha_producao': linha_val if linha_val else 'Não informada',
        'status': maquina.status if hasattr(maquina, 'status') and maquina.status else 'Operando',
        'historico': historico_os
    })


@app.route('/manutencoes/nova', methods=['POST'])
@login_required
def nova_manutencao():
    # 1. Coletar os dados enviados pelo formulário HTML
    maquina_id = request.form.get('maquina_id')
    descricao = request.form.get('descricao_atividades')
    data_str = request.form.get('data_programada')

    # Validação simples
    if not maquina_id or not descricao or not data_str:
        flash('Todos os campos são obrigatórios!', 'danger')
        return redirect(url_for('cronograma'))  # ou para a página anterior

    # Converter a string de data vinda do HTML (YYYY-MM-DD) para um objeto date do Python
    data_formatada = datetime.strptime(data_str, '%Y-%m-%d').date()

    try:
        # 2. Instanciar o modelo conforme definido no seu models.txt
        nova_programacao = ManutencaoProgramada(
            maquina_id=int(maquina_id),
            descricao_atividades=descricao,
            data_programada=data_formatada,
            status='Pendente'  # Valor padrão seguro
        )

        # 3. Adicionar à sessão e PERSISTIR no banco (CRÍTICO!)
        db.session.add(nova_programacao)
        db.session.commit()  # <--- Se faltar isso, não aparece no cronograma!

        flash('Manutenção programada com sucesso!', 'success')

    except Exception as e:
        db.session.rollback()  # Desfaz em caso de erro catastrófico
        flash(f'Erro ao salvar no banco de dados: {str(e)}', 'danger')
        # Dica de ouro: use print(e) para ver o erro exato no terminal onde o Flask está rodando
        print(f"Erro detectado: {e}")

    return redirect(url_for('calendario'))  # Redireciona para atualizar a tela


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
    mq.ativo = False
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
    return render_template('ordens.html', ordens=ordens, maquinas=maquinas)


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
                    ordem_id=nova_os.id,
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


@app.route('/api/ordem/<int:os_id>')
@login_required
def api_ordem(os_id):
    ordem = OrdemServico.query.get_or_404(os_id)
    return jsonify({
        'id': ordem.id,
        'maquina_id': ordem.maquina_id,
        'descricao_defeito': ordem.descricao_defeito,
        'prazo_previsto': ordem.prazo_previsto.strftime('%Y-%m-%d'),
        'status': ordem.status,
        'data_abertura': ordem.data_abertura.isoformat() if ordem.data_abertura else None
    })


@app.route('/ordem/editar', methods=['POST'])
@login_required
def ordem_editar():
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('listar_ordens'))

    os_id = request.form.get('os_id')
    ordem = OrdemServico.query.get_or_404(os_id)

    try:
        ordem.maquina_id = request.form.get('maquina_id')
        prazo_str = request.form.get('prazo_previsto')
        ordem.prazo_previsto = datetime.strptime(prazo_str, '%Y-%m-%d').date()
        ordem.descricao_defeito = request.form.get('descricao_defeito')
        ordem.status = request.form.get('status', 'Pendente')

        imagens = request.files.getlist('imagens')
        if imagens and imagens[0].filename:
            for img in imagens:
                if img and img.filename:
                    nome_seguro = secure_filename(f"os_{ordem.id}_{img.filename}")
                    img.save(os.path.join(app.config['UPLOAD_OS'], nome_seguro))
                    nova_img = OrdemServicoImagem(ordem_servico_id=ordem.id,
                                                  caminho_arquivo=f"uploads/os/{nome_seguro}")
                    db.session.add(nova_img)

        db.session.commit()
        flash('Ordem de Serviço atualizada com sucesso!', 'success')
        return redirect(url_for('listar_ordens'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar a O.S.: {str(e)}', 'danger')
        return redirect(url_for('listar_ordens'))


@app.route('/ordem/excluir/<int:os_id>', methods=['POST'])
@login_required
def ordem_excluir(os_id):
    if current_user.role != 'Administrador':
        flash('Acesso negado!', 'danger')
        return redirect(url_for('listar_ordens'))

    ordem = OrdemServico.query.get_or_404(os_id)

    try:
        for img in ordem.imagens:
            caminho_arquivo = os.path.join('static', img.caminho_arquivo)
            try:
                if os.path.exists(caminho_arquivo):
                    os.remove(caminho_arquivo)
            except:
                pass
            db.session.delete(img)

        for item_previsto in ordem.itens_previstos:
            db.session.delete(item_previsto)

        MovimentacaoEstoque.query.filter_by(os_id=os_id).delete()

        maquina = Maquina.query.get(ordem.maquina_id)
        if maquina:
            maquina.status = 'Operando'

        db.session.delete(ordem)
        db.session.commit()

        flash('Ordem de Serviço excluída com sucesso!', 'success')
        return redirect(url_for('listar_ordens'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir a O.S.: {str(e)}', 'danger')
        return redirect(url_for('listar_ordens'))


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


@app.route('/api/manutencao/<int:manutencao_id>')
@login_required
def api_manutencao(manutencao_id):
    manutencao = ManutencaoProgramada.query.get_or_404(manutencao_id)
    return jsonify({
        'id': manutencao.id,
        'maquina_id': manutencao.maquina_id,
        'descricao_atividades': manutencao.descricao_atividades,
        'data_programada': manutencao.data_programada.strftime('%Y-%m-%d'),
        'status': manutencao.status
    })


@app.route('/manutencao/editar', methods=['POST'])
@login_required
def manutencao_editar():
    if current_user.role not in ['Administrador', 'Tecnico']:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('calendario'))

    manutencao_id = request.form.get('manutencao_id')
    manutencao = ManutencaoProgramada.query.get_or_404(manutencao_id)

    try:
        manutencao.maquina_id = request.form.get('maquina_id')
        data_str = request.form.get('data_programada')
        manutencao.data_programada = datetime.strptime(data_str, '%Y-%m-%d').date()
        manutencao.descricao_atividades = request.form.get('descricao_atividades')
        manutencao.status = request.form.get('status', 'Pendente')

        db.session.commit()
        flash('Manutenção atualizada com sucesso!', 'success')
        return redirect(url_for('calendario'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar a manutenção: {str(e)}', 'danger')
        return redirect(url_for('calendario'))


@app.route('/manutencao/excluir/<int:manutencao_id>', methods=['POST'])
@login_required
def manutencao_excluir(manutencao_id):
    if current_user.role not in ['Administrador', 'Tecnico']:
        flash('Acesso negado!', 'danger')
        return redirect(url_for('calendario'))

    manutencao = ManutencaoProgramada.query.get_or_404(manutencao_id)

    try:
        if manutencao.os_gerada_id:
            os = OrdemServico.query.get(manutencao.os_gerada_id)
            if os:
                for img in os.images:
                    caminho_arquivo = os.path.join('static', img.caminho_arquivo)
                    try:
                        if os.path.exists(caminho_arquivo):
                            os.remove(caminho_arquivo)
                    except:
                        pass
                    db.session.delete(img)

                for item_previsto in os.itens_previstos:
                    db.session.delete(item_previsto)

                MovimentacaoEstoque.query.filter_by(os_id=os.id).delete()

                maquina = Maquina.query.get(os.maquina_id)
                if maquina:
                    maquina.status = 'Operando'

                db.session.delete(os)

        db.session.delete(manutencao)
        db.session.commit()

        flash('Manutenção programada excluída com sucesso!', 'success')
        return redirect(url_for('calendario'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir a manutenção: {str(e)}', 'danger')
        return redirect(url_for('calendario'))


@app.route('/api/ordens/<int:os_id>')
@login_required
def api_detalhes_ordem(os_id):
    os_reg = OrdemServico.query.get_or_404(os_id)

    # Mapeia as peças/insumos previstos para esta OS
    insumos = []
    for p in os_reg.itens_previstos:
        insumos.append({
            'descricao': p.item.descricao,
            'quantidade': p.quantidade_prevista
        })

    # Mapeia as imagens associadas
    imagens = [img.caminho_arquivo for img in os_reg.imagens]

    return jsonify({
        'id': os_reg.id,
        'maquina_codigo': os_reg.maquina.codigo,
        'maquina_descricao': os_reg.maquina.descricao,
        'descricao_defeito': os_reg.descricao_defeito,
        'prazo_previsto': os_reg.prazo_previsto.strftime('%d/%m/%Y'),
        'status': os_reg.status,
        'insumos': insumos,
        'imagens': imagens
    })


if __name__ == '__main__':
    app.run(debug=True)