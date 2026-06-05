Documentação do Sistema (GestorPecas)

## Visão Geral do Projeto

O **GestorPecas** é uma aplicação web focada no gerenciamento e controle de estoque de peças e suprimentos de manutenção. O sistema garante o controle de acesso por níveis de usuário, o registro rigoroso das movimentações de entrada e baixa, e o vínculo dessas movimentações com Ordens de Serviço (O.S.).

## Tecnologias Utilizadas (Stack)

* **Linguagem:** Python
* **Framework Web:** Flask
* **Banco de Dados:** PostgreSQL
* **ORM (Mapeamento Objeto-Relacional):** SQLAlchemy / Flask-SQLAlchemy
* **Autenticação e Segurança:** Flask-Login, Werkzeug Security (scrypt)
* **Interface (Frontend):** HTML5, Bootstrap 5 (para estilização responsiva e componentes como Modais)

## Estrutura de Banco de Dados (Modelos Principais)

| Tabela | Função Principal | Campos Chave |
| --- | --- | --- |
| **`usuarios`** | Gerenciar o acesso e permissões. | `id`, `username`, `email`, `password_hash` (255 char), `role` (Administrador, Tecnico, Almoxarifado). |
| **`itens`** | Catálogo central de peças. | `sku`, `descricao`, `categoria`, `fornecedor`, `preco_unitario`, `estoque_atual`, `estoque_minimo`, `estoque_maximo`. |
| **`item_imagens`** | Armazenar o caminho das fotos de cada peça. | `id`, `item_id` (Chave Estrangeira), `caminho_imagem`. |
| **`movimentacoes_estoque`** | Histórico/Auditoria de tudo que entra e sai. | `tipo` (Entrada/Baixa), `quantidade`, `nota_fiscal`, `os_id`, `usuario_id`, `data_hora`. |
| **`ordens_servico`** | Cadastro de O.S. para vínculo com as baixas. | `id` (Vinculado às movimentações). |

## Mapa de Funcionalidades (Rotas)

### 1. Autenticação e Segurança

* `GET/POST /login`: Valida credenciais (usuário e senha criptografada). Redireciona usuários não logados.
* `GET /logout`: Encerra a sessão do usuário.

### 2. Painel Principal (Dashboard)

* `GET /dashboard`: Exibe a visão geral do sistema e alertas críticos (ex: peças onde o `estoque_atual` é menor ou igual ao `estoque_minimo`).

### 3. Gestão de Peças e Estoque

* `GET /itens`: Lista todas as peças cadastradas.
* `POST /item/novo`: Recebe dados do formulário Modal, cria o registro do item e processa o upload de múltiplas imagens na pasta física, salvando os caminhos no banco.
* `POST /estoque/movimentar`: Registra entradas e saídas. Atualiza a coluna `estoque_atual` do item. Possui validação para impedir baixa maior que o estoque e tratamento para campos vazios de O.S.

### 4. Gestão de Usuários (Acesso Restrito)

* `GET /usuarios`: Lista usuários ativos (Exclusivo para Administradores).
* `POST /usuario/novo`: Cadastra um novo acesso, gerando automaticamente o hash da senha (Exclusivo para Administradores).
