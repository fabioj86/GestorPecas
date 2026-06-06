Visão Geral do Sistema

O Gestor de Manutenção Industrial é uma aplicação web desenvolvida para otimizar o controle de ativos fabris, gerenciamento de estoque de peças de reposição e emissão/acompanhamento de Ordens de Serviço (O.S.). O sistema integra de forma inteligente a indisponibilidade de máquinas com o mapeamento prévio de insumos do almoxarifado.

Arquitetura e Tecnologias

Backend: Python 3.x com framework Flask.

Banco de Dados: PostgreSQL (gerenciado via Flask-SQLAlchemy).

Frontend: HTML5, CSS3, Bootstrap 5 (Ícones via Bootstrap Icons) e JavaScript Nativo (Vanilla JS).

Autenticação: Flask-Login com criptografia de senhas via Werkzeug.

3. Arquitetura do Banco de Dados (Modelos)
3.1. Usuário (usuarios)
Gerencia o controle de acesso por níveis.

id (Integer, PK)

username (String, Único)

email (String, Único)

password_hash (String)

role (String) - Níveis: Administrador, Tecnico, Almoxarifado.

3.2. Item / Peça (itens)
Catálogo de componentes do almoxarifado.

id (Integer, PK)

sku (String, Único) - Código identificador único da peça.

descricao (String)

categoria (String)

estoque_atual (Integer)

estoque_minimo (Integer)

localizacao (String)

3.3. Máquina (maquinas)
Ativos monitorados pelo time de manutenção.

id (Integer, PK)

codigo (String, Único) - TAG de identificação física.

descricao (String)

linha (String) - Linha de produção ou setor.

status (String) - Operando ou Defeito.

3.4. Ordem de Serviço (ordens_servico)
Registros de intervenções técnicas.

id (Integer, PK)

maquina_id (Integer, FK -> maquinas.id)

descricao_defeito (Text)

data_abertura (DateTime, Padrão: Atual)

prazo_previsto (Date)

status (String) - Pendente, Em Andamento, Concluída.

3.5. Itens Previstos para O.S. (os_itens_previstos)
Tabela relacional de pré-mapeamento de peças necessárias para a execução da manutenção.

id (Integer, PK)

os_id (Integer, FK -> ordens_servico.id)

item_sku (String, FK -> itens.sku)

quantidade_prevista (Integer)

Relacionamento Direto: Mapeado explicitamente para o modelo Item via condição de junção por SKU string.

4. Módulos e Fluxos Funcionais
4.1. Painel de Controle (Dashboard)
Centraliza os indicadores críticos da planta industrial em tempo real:

Métricas Gerais: Total de peças em estoque, máquinas operando e O.S. pendentes.

Alertas de Estoque Mínimo: Tabela vermelha dinâmica que exibe peças cujos saldos atuais estão iguais ou abaixo do limite de segurança.

Alertas de O.S. em Atraso: Nova tabela crítica que isola e exibe ordens pendentes cuja data limite (prazo_previsto) é menor que a data atual.

Prazos Críticos: Monitoramento visual de ordens de serviço com vencimento iminente.

4.2. Controle de Ativos (Máquinas)
Apresenta listagem com filtros avançados de busca por código, descrição e setor.

Abertura de O.S. Centralizada: Inclusão de um botão de ação rápida amarelo (+ Nova O.S.) posicionado estrategicamente à esquerda de + Nova Máquina.

Ao acionar o botão, um modal completo permite associar a falha a um ativo, detalhar os sintomas técnicos, delimitar o prazo de conclusão (bloqueando datas retroativas via JavaScript) e pré-reservar insumos de forma dinâmica.

4.3. Controle de Estoque e Almoxarifado
Permite dar entradas (via Nota Fiscal) e baixas operacionais.

Vincula saídas de insumos a Ordens de Serviço abertas para cálculo de custos de manutenção e rastreabilidade total.
