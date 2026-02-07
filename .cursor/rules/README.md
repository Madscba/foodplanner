# Cursor Rules for Foodplanner

This directory contains Cursor IDE rules that provide context-aware assistance when working on this project.

## How Rules Work

Rules are `.mdc` files (Markdown with YAML frontmatter) that Cursor loads based on:

1. **`alwaysApply: true`** - Rule is always active
2. **`globs` pattern** - Rule activates when matching files are referenced
3. **`@rule-name`** - Manual activation via chat or Cmd-K

## Available Rules

| Rule | Scope | Description |
|------|-------|-------------|
| `workspace.mdc` | Always on | Core project context, tech stack, essential commands |
| `python-style.mdc` | `**/*.py` | Python conventions, type hints, error handling |
| `fastapi.mdc` | `**/routers/*.py` | API endpoint patterns, schemas, responses |
| `database.mdc` | `**/models.py, **/graph/*.py` | SQLAlchemy and Neo4j patterns |
| `testing.mdc` | `tests/**/*.py` | Pytest conventions, fixtures, markers |
| `celery-tasks.mdc` | `**/tasks/*.py` | Background task patterns, scheduling |
| `scrapers.mdc` | `**/scrapers/*.py` | Web scraping and API connector patterns |
| `docker.mdc` | `**/Dockerfile, **/docker-compose.yml` | Container configuration |

## Usage

### Automatic (Recommended)
Rules load automatically when you reference matching files:
- Open a file in `tests/` → `testing.mdc` loads
- Ask about `routers/recipes.py` → `fastapi.mdc` loads

### Manual Reference
Reference rules explicitly in chat:
```
@workspace.mdc how do I add a new scraper?
```

### Checking Active Rules
In Cursor settings, you can enable "Show active rules" to see which rules are currently loaded.

## Updating Rules

When you encounter repeated issues or new patterns:

1. **Add examples** - Show correct AND incorrect patterns
2. **Be specific** - Avoid vague instructions
3. **Include rationale** - Explain why, not just what
4. **Keep it focused** - Split large rules into multiple files

## Best Practices

- Rules should stay under 500 lines
- Include code examples with both DO and DON'T patterns
- Update rules when project conventions change
- Test rule activation by checking which rules load for different file types

## Memory

Cursor's native Memories feature (Settings → Rules → Memories) can store facts across sessions. Use it for:
- Important decisions that aren't in code
- Personal preferences
- Things you don't want to explain repeatedly

Example: "Remember: always use `uv run` prefix for commands in this project"
