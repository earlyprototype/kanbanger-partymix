# Kanbanger Setup & Usage - Simple User Flow

## Getting Started

```mermaid
graph LR
    A[Install kanbanger] --> B[Run setup wizard]
    B --> C[Create _kanban.md]
    C --> D[Work with AI or CLI]
    D --> E[Tasks sync to GitHub]
    
    style A fill:#4CAF50
    style B fill:#2196F3
    style C fill:#FF9800
    style D fill:#9C27B0
    style E fill:#4CAF50
```

## Setup Wizard Flow

```mermaid
graph TD
    Start([Run: kanban-sync-setup]) --> Q1{Have GitHub token?}
    Q1 -->|No| GetToken[Get token from GitHub]
    Q1 -->|Yes| Step1[Enter GitHub token]
    GetToken --> Step1
    
    Step1 --> Step2[Enter repository name]
    Step2 --> Step3[Select GitHub Project]
    Step3 --> Step4{Want MCP integration?}
    
    Step4 -->|Yes| SetupMCP[Setup MCP server]
    Step4 -->|No| Done
    
    SetupMCP --> Restart[Restart your IDE]
    Restart --> Done([Done! Start using kanbanger])
    
    style Start fill:#4CAF50
    style Done fill:#4CAF50
    style SetupMCP fill:#2196F3
```

## Daily Usage

```mermaid
graph TD
    Open[Open project in IDE] --> AI{Using AI assistant?}
    
    AI -->|Yes| MCP[AI uses MCP tools<br/>add_task, move_task, etc.]
    AI -->|No| Manual[Manually edit _kanban.md]
    
    MCP --> Tasks[Tasks updated in _kanban.md]
    Manual --> Tasks
    
    Tasks --> Sync[Sync to GitHub]
    Sync --> Team[Team sees updates on<br/>GitHub Project board]
    
    style Open fill:#4CAF50
    style MCP fill:#2196F3
    style Team fill:#4CAF50
```

## Commands Cheat Sheet

| Step | Command | What it does |
|------|---------|-------------|
| **Setup** | `kanban-sync-setup` | Interactive wizard - do this first |
| **Preview** | `kanban-sync _kanban.md --dry-run` | See what would change (safe) |
| **Sync** | `kanban-sync _kanban.md` | Push changes to GitHub |
| **MCP** | AI: "Add task to TODO" | AI assistant does it for you |

That's it! 🎉
