# Contributing Guide

This project uses three separate repositories:

- `ecommerce-backend` for Django, DRF, Celery, and backend tests.
- `ecommerce-frontend` for Vue, Tailwind, and frontend tests.
- `ecommerce-infra` for Docker Compose and shared infrastructure files.

Follow this workflow for every task so changes stay reviewable and easy to merge.

## Branching Strategy

Do not work directly on `main`. Every GitHub Project task should have its own branch and pull request.

Branch format:

```bash
feature/<your-name>/<short-task-description>
```

Examples:

```bash
feature/amat/celery-setup
feature/amat/swagger-schema-examples
feature/amat/contributing-guide
```

Before starting a new task, update `main` and create a fresh branch:

```bash
git checkout main
git pull origin main
git checkout -b feature/amat/contributing-guide
```

If your branch falls behind `main`, update it before opening or merging the pull request:

```bash
git checkout main
git pull origin main
git checkout feature/amat/contributing-guide
git merge main
```

Resolve conflicts manually, run checks again, then commit the merge resolution.

## Commit Messages

Use short, descriptive commit messages with one of these prefixes:

- `feat:` for new features.
- `fix:` for bug fixes.
- `docs:` for documentation changes.
- `test:` for tests.
- `refactor:` for code restructuring without behavior changes.
- `chore:` for maintenance and configuration work.

Include the GitHub task number when the commit maps to a task.

Examples:

```bash
git commit -m "feat: add product image upload endpoint (#189)"
git commit -m "test: add Celery queue routing tests (#327)"
git commit -m "docs: add contributing guide and PR checklist (#409)"
```

Keep commits focused. Stage only the files that belong to the current task instead of using `git add .`.

## Pre-commit Hooks

Install the development tooling and Git hook before committing backend changes:

```bash
python -m pip install -r requirements-dev.txt
pre-commit install
```

The configured hooks run before each commit and check:

- Basic file hygiene such as trailing whitespace, YAML syntax, final newlines, and large accidental files.
- Python formatting with `black --check --diff`.
- Python linting with `flake8`.

To run the same checks manually:

```bash
pre-commit run --all-files
```

## Local Development

Run Docker commands from the infrastructure repository:

```bash
cd ../ecommerce-infra
docker compose up -d
```

Useful commands:

```bash
docker compose ps
docker compose logs -f web
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose down
docker compose up --build -d
```

Local URLs:

- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/api/docs/`
- Django Admin: `http://localhost:8000/admin/`
- Frontend: `http://localhost:5173`

## Pull Request Process

Push your task branch:

```bash
git push -u origin feature/amat/contributing-guide
```

Open a pull request on GitHub:

- Base branch: `main`
- Compare branch: your task branch
- Add a clear title.
- Fill in the pull request description.
- Request at least one reviewer.
- Wait for CI checks to pass.
- Merge only after approval and passing checks.

After the pull request is merged, update your local `main`:

```bash
git checkout main
git pull origin main
```

Then create the next task branch from the updated `main`.

## Pull Request Template

Use this structure when opening a pull request:

```markdown
## What This Does
- 

## Related Task
- #

## Related Epic / Story
- 

## How To Test
1. 

## Checklist
- [ ] I used a task-specific branch.
- [ ] I staged only files related to this task.
- [ ] I ran the relevant checks or documented why they were not run.
- [ ] I verified Docker still starts when infrastructure or dependencies changed.
- [ ] I requested a reviewer.
```

## Code Review Checklist

Reviewers should check:

- The change matches the linked task and does not include unrelated work.
- API changes are RESTful and documented in Swagger when relevant.
- Tenant-scoped data stays isolated by tenant.
- Protected endpoints use the correct permission classes.
- Database changes include migrations.
- New behavior has focused tests.
- Querysets avoid obvious N+1 problems.
- Redis and Celery changes use the configured queues and cache keys.
- Frontend changes are responsive and follow existing Vue and Tailwind patterns.
- The pull request has passing CI checks before merge.

## Golden Rules

- Never push directly to `main`.
- Always pull the latest `main` before starting a task.
- One task should map to one branch and one pull request.
- Run Docker from `ecommerce-infra`.
- Commit small, focused changes.
- Tell the team when changing dependencies, Docker, migrations, or shared settings.
