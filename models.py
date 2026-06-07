from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


# -----------------------------------------------------------------------------
# MODELO: USUÁRIO
# -----------------------------------------------------------------------------
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Tecnico')  # Ex: Administrador, Tecnico

    # Relacionamentos
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='usuario', lazy=True)


# -----------------------------------------------------------------------------
# MODELO: ITEM (PEÇAS DO ESTOQUE)
# -----------------------------------------------------------------------------
class Item(db.Model):
    __tablename__ = 'itens'

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(100))
    localizacao = db.Column(db.String(100))
    fornecedor = db.Column(db.String(100))
    preco_unitario = db.Column(db.Numeric(10, 2), default=0.0)

    # Coluna corrigida para refletir exatamente a estrutura física do banco
    estoque_atual = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=0)
    estoque_maximo = db.Column(db.Integer, default=0)

    # Relacionamentos
    imagens = db.relationship('ItemImagem', backref='item', lazy=True)
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='item', lazy=True)


class ItemImagem(db.Model):
    __tablename__ = 'item_imagens'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('itens.id'), nullable=False)
    caminho_imagem = db.Column(db.String(255), nullable=False)


# -----------------------------------------------------------------------------
# MODELO: MÁQUINA
# -----------------------------------------------------------------------------
class Maquina(db.Model):
    __tablename__ = 'maquinas'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    linha = db.Column(db.String(100))
    status = db.Column(db.String(50), default='Operando')  # Ex: Operando, Defeito, Manutencao

    # Relacionamentos
    imagens = db.relationship('MaquinaImagem', backref='maquina', lazy=True)
    ordens_servico = db.relationship('OrdemServico', backref='maquina', lazy=True)


class MaquinaImagem(db.Model):
    __tablename__ = 'maquina_imagens'

    id = db.Column(db.Integer, primary_key=True)
    maquina_id = db.Column(db.Integer, db.ForeignKey('maquinas.id'), nullable=False)
    caminho_arquivo = db.Column(db.String(255), nullable=False)


# -----------------------------------------------------------------------------
# MODELO: ORDEM DE SERVIÇO (MÓDULO DE MANUTENÇÃO)
# -----------------------------------------------------------------------------
class OrdemServico(db.Model):
    __tablename__ = 'ordens_servico'

    id = db.Column(db.Integer, primary_key=True)
    maquina_id = db.Column(db.Integer, db.ForeignKey('maquinas.id'), nullable=False)
    descricao_defeito = db.Column(db.Text, nullable=False)  # Alinhado com a correção do banco
    data_abertura = db.Column(db.DateTime, default=datetime.utcnow)
    prazo_previsto = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Andamento, Concluída

    # Relacionamentos
    imagens = db.relationship('OrdemServicoImagem', backref='ordem', lazy=True)
    itens_previstos = db.relationship('OrdemServicoItemPrevisto', backref='ordem', lazy=True)
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='ordem_servico', lazy=True)


class OrdemServicoImagem(db.Model):
    __tablename__ = 'os_imagens'

    id = db.Column(db.Integer, primary_key=True)
    os_id = db.Column(db.Integer, db.ForeignKey('ordens_servico.id', ondelete='CASCADE'), nullable=False)
    caminho_arquivo = db.Column(db.String(255), nullable=False)


class OrdemServicoItemPrevisto(db.Model):
    __tablename__ = 'os_itens_previstos'

    id = db.Column(db.Integer, primary_key=True)
    os_id = db.Column(db.Integer, db.ForeignKey('ordens_servico.id', ondelete='CASCADE'), nullable=False)
    item_sku = db.Column(db.String(50), db.ForeignKey('itens.sku'), nullable=False)
    quantidade_prevista = db.Column(db.Integer, nullable=False, default=1)

    # Relacionamento que vincula o SKU cadastrado na O.S ao cadastro global do Item
    item = db.relationship('Item', primaryjoin="OrdemServicoItemPrevisto.item_sku==Item.sku", backref='os_links', lazy=True)


# -----------------------------------------------------------------------------
# MODELO: MOVIMENTAÇÃO DE ESTOQUE (LOGS OPERACIONAIS)
# -----------------------------------------------------------------------------
class MovimentacaoEstoque(db.Model):
    __tablename__ = 'movimentacoes_estoque'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('itens.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Entrada ou Baixa
    quantidade = db.Column(db.Integer, nullable=False)
    data_movimentacao = db.Column(db.DateTime, default=datetime.utcnow)
    nota_fiscal = db.Column(db.String(50), nullable=True)
    os_id = db.Column(db.Integer, db.ForeignKey('ordens_servico.id'), nullable=True)


# -----------------------------------------------------------------------------
# MODELO: LOG DE AUDITORIA DO SISTEMA
# -----------------------------------------------------------------------------
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    acao = db.Column(db.String(255), nullable=False)
    detalhes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# -----------------------------------------------------------------------------
# MODELO: MANUTENÇÃO PROGRAMADA (PREVENTIVAS / AGENDAMENTOS)
# -----------------------------------------------------------------------------
class ManutencaoProgramada(db.Model):
    __tablename__ = 'manutencoes_programadas'

    id = db.Column(db.Integer, primary_key=True)
    maquina_id = db.Column(db.Integer, db.ForeignKey('maquinas.id'), nullable=False)
    descricao_atividades = db.Column(db.Text, nullable=False)
    data_programada = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Atraso, Concluida

    # Guarda o ID da OS se o usuário optar por gerar uma automaticamente
    os_gerada_id = db.Column(db.Integer, db.ForeignKey('ordens_servico.id'), nullable=True)

    # Relacionamentos
    maquina = db.relationship('Maquina', backref='programacoes', lazy=True)
    os_gerada = db.relationship('OrdemServico', backref='origem_programacao', lazy=True)