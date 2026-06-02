# Guia de Login - Sistema 1Crypten

## 🎯 Sistema de Login Disponível

### 1. Login Rápido (Cockpit)
- **URL:** `https://1crypten.space/cockpit`
- **Interface:** Login rápido com senha
- **Credenciais:**
  - Usuário: `admin` (automático)
  - Senha: `admin123`
- **Funcionalidade:** Acesso rápido ao cockpit principal
- **Botão:** "Login Completo →" para acessar sistema completo

### 2. Login Completo (`/auth`)
- **URL:** `https://1crypten.space/auth`
- **Interface:** Sistema único de login e cadastro (com abas)
- **Recursos:**
  - Aba "Login" para autenticação
  - Aba "Cadastro" para novos usuários
  - Validação de senhas
  - Design moderno e responsivo (Tailwind)
  - Material Icons e animações suaves
- **Credenciais:**
  - Login: `admin` / `admin123`
  - Cadastro: Novos usuários com senha mínima 8 caracteres

> **Nota:** A URL `/login` foi unificada com `/auth` e agora redireciona automaticamente. Use `/auth` em links e referências.

## 🔐 Como Usar

### Acesso Rápido (Recomendado para testes)
1. Acesse `https://1crypten.space/cockpit`
2. Digite `admin123` no campo "CHAVE DE ACESSO"
3. Clique em "ENTRAR"
4. Pronto! Você está no cockpit principal

### Acesso Completo (Para cadastro e login normal)
1. Acesse `https://1crypten.space/auth`
2. Use as credenciais `admin` / `admin123` para login rápido
3. Ou clique na aba "Cadastro" para criar nova conta
4. Preencha os campos e crie sua conta

### Acesso Direto (Sem autenticação)
1. Acesse `https://1crypten.space/cockpit`
2. Clique em "Login Completo →"
3. Ou acesse diretamente `https://1crypten.space/auth`

## 📱 URLs Disponíveis

| URL | Descrição | Recomendação |
|-----|-----------|--------------|
| `https://1crypten.space/` | Redireciona para `/auth` | Página principal |
| `https://1crypten.space/auth` | Login + Cadastro (tela única) | Uso geral |
| `https://1crypten.space/login` | [LEGADO] Redireciona para `/auth` | Compatibilidade |
| `https://1crypten.space/cockpit` | Cockpit com login rápido | Testes rápidos |

## 🔑 Credenciais Padrão

### Demo/Testes
- **Usuário:** `admin`
- **Senha:** `admin123`

### Cadastro de Novos Usuários
- **Usuário:** Qualquer nome (mínimo 3 caracteres)
- **Email:** Opcional
- **Senha:** Mínimo 8 caracteres
- **Confirmação:** Mesma senha

## 🚀 Funcionalidades

### Sistema de Login
- ✅ Autenticação via API REST
- ✅ Tokens JWT para sessão
- ✅ Armazenamento local seguro
- ✅ Redirecionamento automático

### Sistema de Cadastro
- ✅ Registro de novos usuários
- ✅ Validação de senhas forte
- ✅ Criptografia de senhas
- ✅ Ativação imediata

### Interface
- ✅ Design moderno e responsivo
- ✅ Tema escuro (dark mode)
- ✅ Animações suaves
- ✅ Feedback visual claro

## 🛠️ Integração Backend

### API Endpoints
```bash
# Login
POST /api/auth/login
{
    "username": "admin",
    "password": "admin123"
}

# Cadastro  
POST /api/auth/register
{
    "username": "novo_usuario",
    "email": "email@exemplo.com",
    "password": "senha123",
    "confirm_password": "senha123"
}

# Perfil
GET /api/auth/me
Authorization: Bearer <token>
```

## 🔄 Como alternar entre sistemas

1. **Do Cockpit:** Clique em "Login Completo →"
2. **Da Tela de Auth:** Acesse diretamente `cockpit.html`
3. **Ambos:** Usam o mesmo backend de autenticação

## 💡 Dicas

- Use o login rápido do cockpit para testes rápidos
- Use a tela `/auth` para cadastro de novos usuários
- Todos os sistemas são integrados ao mesmo backend
- As credenciais `admin` / `admin123` funcionam em todos os fluxos

## 🚨 Problemas Comuns

### Erro 422 (Unprocessable Content)
- Verifique se está enviando `username` e `password`
- Confirme se o backend está rodando

### Senha Incorreta
- Use `admin123` (não `123`)
- Verifique se não há espaços no início/fim

### Página não encontrada
- Aguarde o deploy do Railway completar
- Verifique se a URL está correta