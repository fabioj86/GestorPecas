from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


# -----------------------------------------------------------------------------
# MODELO: UTILIZADOR (Gestão de Acessos - RBAC)
# -----------------------------------------------------------------------------
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Níveis: 'Administrador', 'Tecnico', 'Almoxarifado'
    role = db.Column(db.String(255), nullable=False, default='Tecnico')

    # Relações
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='operador', lazy=True)
    auditorias = db.relationship('AuditLog', backref='usuario', lazy=True)


# -----------------------------------------------------------------------------
# MODELO: MÁQUINA DE PRODUÇÃO
# -----------------------------------------------------------------------------

class Maquina(db.Model):
    __tablename__ = 'maquinas'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    linha = db.Column(db.String(50))  # Ex: Linha 01, Linha de Montagem
    status = db.Column(db.String(20), default='Operando')  # 'Operando' ou 'Defeito'

    # Relacionamento opcional com ordens de serviço, se desejar expandir depois
    # movimentacoes = db.relationship('MovimentacaoEstoque', backref='maquina_ref')

# -----------------------------------------------------------------------------
# MODELO: ITEM / PEÇA DE MANUTENÇÃO
# -----------------------------------------------------------------------------
class Item(db.Model):
    __tablename__ = 'itens'

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)  # Código único da peça
    descricao = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(50))
    localizacao = db.Column(db.String(50))  # Ex: Prateleira A-3
    fornecedor = db.Column(db.String(100))
    preco_unitario = db.Column(db.Numeric(10, 2), default=0.00)

    # Controle de Stock
    estoque_atual = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=0)
    estoque_maximo = db.Column(db.Integer, default=0)

    # Relações
    imagens = db.relationship('ItemImagem', backref='item', cascade='all, delete-orphan', lazy=True)
    movimentacoes = db.relationship('MovimentacaoEstoque', backref='item', lazy=True)
    auditorias = db.relationship('AuditLog', backref='item', lazy=True)


# MODELO AUXILIAR: Múltiplas imagens por item
class ItemImagem(db.Model):
    __tablename__ = 'item_imagens'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('itens.id'), nullable=False)
    caminho_imagem = db.Column(db.String(255), nullable=False)


# -----------------------------------------------------------------------------
# MODELO: GESTÃO DE ESTOQUE (Entradas e Baixas)
# -----------------------------------------------------------------------------
class MovimentacaoEstoque(db.Model):
    __tablename__ = 'movimentacoes_estoque'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('itens.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'Entrada' ou 'Baixa'
    quantidade = db.Column(db.Integer, nullable=False)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)

    # Campos de Rastreabilidade
    nota_fiscal = db.Column(db.String(50))  # Obrigatório para Entradas
    os_id = db.Column(db.Integer, db.ForeignKey('ordens_servico.id'), nullable=True)  # Vinculo para Baixas


# -----------------------------------------------------------------------------
# MODELO: MANUTENÇÃO (Ordens de Serviço)
# -----------------------------------------------------------------------------
class OrdemServico(db.Model):
    __tablename__ = 'ordens_servico'

    id = db.Column(db.Integer, primary_key=True)
    maquina_id = db.Column(db.Integer, db.ForeignKey('maquinas.id'), nullable=False)
    descricao_problema = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente, Em Andamento, Concluída
    data_abertura = db.Column(db.DateTime, default=datetime.utcnow)
    data_fechamento = db.Column(db.DateTime, nullable=True)

    # Relações
    pecas_utilizadas = db.relationship('MovimentacaoEstoque', backref='ordem_servico', lazy=True)


# -----------------------------------------------------------------------------
# MODELO: AUDITORIA (Quem alterou o quê?)
# -----------------------------------------------------------------------------
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('itens.id'), nullable=False)
    acao = db.Column(db.String(20), nullable=False)  # 'Criou', 'Editou', 'Excluiu'
    detalhes = db.Column(db.Text)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)