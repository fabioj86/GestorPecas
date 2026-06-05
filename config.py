import os


class Config:
    # Chave secreta para criptografia de sessões e cookies
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'uma_chave_secreta_muito_segura_12345'

    # Configuração do PostgreSQL (substitua com as suas credenciais)
    # Formato: postgresql://usuario:senha@localhost:5432/nome_do_banco
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'postgresql://postgres:fjpl666848@localhost:5432/gestor_manutencao'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Caminho para upload de imagens
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # Limite de 16MB por upload