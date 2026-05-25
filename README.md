# Vendora Backend

Vendora Backend is the Django REST API for a multi-tenant ecommerce platform
focused on technology products. It powers the Vue frontend through REST
endpoints and is normally run through the `ecommerce-infra` Docker Compose
stack.

## Project Overview

The backend provides:

- JWT authentication, registration, logout, email verification, and password reset
- Role-based access for customers, vendors, and superadmins
- Tenant-aware catalog data for brands, categories, products, variants, and images
- Search and filtering for catalog browsing
- Redis-backed shopping cart support
- Checkout sessions, address validation, atomic order creation, and Stripe payment intents
- Stripe webhook handling for payment success
- Order history, cancellation, vendor order transitions, and audit events
- Vendor dashboard, inventory, order exports, and analytics APIs
- AI chat and sales insight endpoints
- Celery background jobs for emails, exports, and scheduled work
- Request logging middleware and admin log endpoints
- Swagger UI and ReDoc documentation

## Tech Stack

- Python 3.12
- Django 6
- Django REST Framework
- PostgreSQL
- Redis
- Celery and Celery Beat
- Simple JWT
- drf-spectacular
- django-filter
- django-mptt
- django-fsm
- Stripe SDK
- OpenAI SDK
- Pillow
- django-storages with optional AWS S3
- Docker

## Related Repositories

The full project uses three sibling repositories:

```text
Vendora/
  ecommerce-backend/
  ecommerce-frontend/
  ecommerce-infra/
```

Run Docker commands from `ecommerce-infra`.

## Main Apps

- `users` - authentication, JWT, roles, profile, avatar upload
- `tenants` - tenant registration and tenant data isolation
- `catalog` - products, categories, variants, product images, search
- `cart` - cart and cart item APIs with Redis caching
- `checkout` - checkout sessions, order creation, Stripe integration
- `orders` - customer and vendor order workflows
- `vendor` - dashboard, inventory, exports, analytics
- `inventory` - vendor inventory records and low-stock alerts
- `ai` - chatbot and sales insight APIs
- `notifications` - notification tasks and failed task records
- `request_logs` - request log persistence and admin listing

## Local Setup

Clone all repositories into the same parent folder:

```bash
git clone https://github.com/bashkimhashani/ecommerce-backend.git
git clone https://github.com/bashkimhashani/ecommerce-frontend.git
git clone https://github.com/bashkimhashani/ecommerce-infra.git
```

Create the infra `.env` file:

```bash
cd path/to/Vendora/ecommerce-infra
cp .env.example .env
```

Start the full stack:

```bash
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
```

## Local URLs

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Django admin: `http://localhost:8000/admin/`

Use `http://localhost:5173` for the frontend because local CORS is configured
for that origin.

## Demo Accounts

After running `seed_demo_data`, these users are available:

```text
admin@example.com
vendor@example.com
gaming.vendor@example.com
office.vendor@example.com
customer@example.com
```

Password for all demo users:

```text
DemoPass123!
```

## Product Images

Seed product images are stored in:

```text
catalog/seed_images/products/
```

The generated `media/` directory is local runtime output. Do not commit it.
Running `seed_demo_data` creates `ProductImage` records and generates local
media files automatically.

## Environment Notes

Important values live in `ecommerce-infra/.env`:

- `CORS_ALLOWED_ORIGINS`
- `REDIS_URL`
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `OPENAI_API_KEY`
- `AWS_STORAGE_BUCKET_NAME`
- `AWS_S3_REGION_NAME`

AWS S3 is disabled until S3 variables are filled in. Without S3, media files are
stored locally.

## Daily Commands

Run from `ecommerce-infra`:

```bash
docker compose up -d
docker compose logs -f web
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
docker compose exec web python manage.py test
docker compose exec web flake8
docker compose down
```

Rebuild after dependency changes:

```bash
docker compose up --build -d
```

Reset local database volumes:

```bash
docker compose down -v
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
```

## Git Workflow

```bash
git checkout main
git pull origin main
git checkout -b feature/yourname/task-name
```

Commit and push:

```bash
git add .
git commit -m "type: describe the change"
git push origin feature/yourname/task-name
```

Avoid committing runtime folders such as `media/`, `staticfiles/`, or `venv/`.
