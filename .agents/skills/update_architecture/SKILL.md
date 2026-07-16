---
name: update_architecture_diagram
description: Updates the system architecture Mermaid diagram when code files, routes, or routing parameters are modified.
---

# Skill: update_architecture_diagram

Esta skill orienta o agente de IA a manter e atualizar o diagrama de arquitetura do sistema sempre que ocorrerem mudanças estruturais no código-fonte.

## Instruções de Operação

### 1. Quando disparar esta Skill
* Ao criar, renomear ou deletar roteadores FastAPI (`backend/routes/*`).
* Ao adicionar novos serviços ou motores táticos (`backend/services/*`).
* Ao alterar a persistência ou a sincronização de dados (PostgreSQL, Firebase Firestore, Firebase RTDB, SQLite).
* Ao modificar os fluxos de dependência e consenso (como CaptainAgent, OracleAgent, etc.).

### 2. Passos para Atualização
1. Abra o arquivo de imagem/texto do diagrama em [`master_architecture_diagram.md`](file:///C:/Users/spcom/.gemini/antigravity/brain/17f4ca78-4bd5-4768-9e93-a882ad663d2a/master_architecture_diagram.md).
2. Localize os blocos de subgrafos correspondentes no código Mermaid:
   * `subgraph Frontend`: Telas de frontend.
   * `subgraph API_Routers`: Rotas e endpoints.
   * `subgraph Decision_Engines`: Agentes e motores de lógica principal.
   * `subgraph Sandbox_Labs`: Laboratórios simulados.
   * `subgraph Data_Layer`: Bancos de dados de persistência.
3. Edite as relações de fluxo (`-->` ou `==>`) para refletir como os dados trafegam.
4. Salve o arquivo e adicione ao commit com o prefixo `docs(arch): update mermaid architecture diagram`.
