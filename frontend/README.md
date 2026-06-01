# Sistema de Autenticação 1Crypten

## Páginas Disponíveis

### 1. Página Principal de Login (`login.html`)
- **URL:** `https://seu-dominio/login.html`
- **Funcionalidade:** Página principal de login e cadastro
- **Acesso:** Redireciona automaticamente ao acessar o domínio principal

### 2. Cockpit Principal (`cockpit.html`)
- **URL:** `https://seu-dominio/cockpit.html`
- **Funcionalidade:** Interface principal do sistema
- **Acesso:** Requer autenticação (tem opção de acesso direto)

### 3. Sistema de Login Integrado
- **URL:** `https://seu-dominio/` (redireciona para login.html)
- **Funcionalidade:** Sistema de login integrado na interface principal

## Credenciais de Acesso

### Acesso Rápido (Demo)
- **Usuário:** `admin`
- **Senha:** `admin123`
- **Nota:** Acesso direto ao cockpit sem necessidade de login

### Cadastro de Novos Usuários
1. Acesse a página `login.html`
2. Clique em "Cadastre-se"
3. Preencha os campos:
   - Usuário (obrigatório)
   - Email (opcional)
   - Senha (mínimo 8 caracteres)
   - Confirmação de senha
4. Clique em "Criar Conta"

## Features

### Sistema de Login
- Autenticação via API REST
- Tokens JWT para sessão
- Manutenção de estado do usuário
- Redirecionamento automático após login

### Sistema de Cadastro
- Registro de novos usuários
- Validação de senhas
- Criptografia de senhas
- Ativação imediata da conta

### Interface
- Design moderno e responsivo
- Tema escuro (dark mode)
- Animações suaves
- Mensagens de feedback claras

## Endpoints da API

### Login
```
POST /api/auth/login
Content-Type: application/json

{
    "username": "admin",
    "password": "admin123"
}
```

### Cadastro
```
POST /api/auth/register
Content-Type: application/json

{
    "username": "novo_usuario",
    "email": "email@exemplo.com",
    "password": "senha123",
    "confirm_password": "senha123"
}
```

### Perfil do Usuário
```
GET /api/auth/me
Authorization: Bearer <token>
```

## Configuração

### Backend
- Serviço de autenticação em `/backend/`
- Banco de dados PostgreSQL
- Criptografia de senhas com bcrypt
- Tokens JWT para segurança

### Frontend
- Interface web responsiva
- Integração com APIs REST
- Armazenamento local de tokens
- Autenticação persistente

## Como Usar

1. **Acesso Principal:**
   - Acesse a URL do seu domínio
   - Será redirecionado para a página de login

2. **Login:**
   - Digite suas credenciais
   - Clique em "Entrar"
   - Será redirecionado para o cockpit

3. **Cadastro:**
   - Clique em "Cadastre-se"
   - Preencha o formulário
   - Confirme o cadastro
   - Faça login com suas novas credenciais

4. **Acesso Direto:**
   - Use o botão "Acesso Direto" para acessar o cockpit sem autenticação
   - Útil para desenvolvimento e testes

## Estrutura de Arquivos

```
frontend/
├── login.html          # Página principal de login e cadastro
├── auth.html           # Página avançada de autenticação
├── cockpit.html        # Interface principal do sistema
├── index.html          # Página inicial (redireciona para login)
├── README.md           # Documentação do sistema
└── ...                 # Outros arquivos do sistema
```

## Segurança

- Senhas criptografadas com bcrypt
- Tokens JWT com expiração
- Validação de entrada de dados
- Proteção contra ataques comuns
- HTTPS recomendado para produção

## Desenvolvimento

### Iniciar Servidor Local
```bash
cd frontend
python -m http.server 8000
```

Acessar em: http://localhost:8000