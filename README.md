# Vendora Backend

Vendora Backend is the Django REST API for Vendora, a multi-tenant ecommerce
platform for technology products. The API supports customer shopping, vendor
operations, checkout, order lifecycle management, AI-assisted features, and
project administration.

This repository is one part of the Vendora system:

```text
Vendora/
  ecommerce-backend/    Django REST API
  ecommerce-frontend/   Vue customer and vendor interface
  ecommerce-infra/      Docker Compose and local environment orchestration
```

## System Role

The backend is responsible for business logic, persistence, security, and
external integrations. The frontend communicates with this service over REST
only, using endpoints under `/api/v1/`.

Core responsibilities include:

- Authentication and authorization with JWT and role-based permissions
- Tenant-aware data isolation for companies and stores
- Product catalog, categories, brands, variants, product images, search, and filtering
- Redis-backed cart state for guests and authenticated customers
- Checkout sessions, shipping address validation, order creation, and inventory updates
- Stripe payment intent creation and webhook processing
- Customer order history and cancellation rules
- Vendor order management, inventory workflows, dashboard data, and exports
- AI chat and sales insight endpoints
- Celery background jobs for notifications, reports, exports, and external APIs
- Middleware-based API request logging and admin log visibility
- OpenAPI documentation through Swagger UI and ReDoc

## Tech Stack

| Area | Technology |
| --- | --- |
| Language | Python 3.12 |
| Framework | Django 6, Django REST Framework |
| Database | PostgreSQL |
| Cache and broker | Redis |
| Async jobs | Celery, Celery Beat |
| Auth | Simple JWT, custom Redis token blacklist |
| API documentation | drf-spectacular, Swagger UI, ReDoc |
| Filtering and trees | django-filter, django-mptt |
| State transitions | django-fsm |
| Payments | Stripe SDK |
| AI | OpenAI SDK |
| Media | Pillow, local filesystem storage, optional AWS S3 |
| Containers | Docker |

## Application Modules

| App | Purpose |
| --- | --- |
| `users` | Registration, login, profile, roles, avatar upload, password reset |
| `tenants` | Tenant registration and tenant-aware model isolation |
| `catalog` | Brands, categories, products, variants, images, search, filters |
| `cart` | Cart and cart item APIs with Redis-backed state |
| `checkout` | Checkout sessions, addresses, order creation, Stripe payment intents |
| `orders` | Customer orders, vendor transitions, audit events, status emails |
| `vendor` | Dashboard summary, analytics, inventory, exports |
| `inventory` | Stock records and low-stock workflows |
| `ai` | Chatbot and sales insight endpoints |
| `notifications` | Notification tasks and failed task tracking |
| `request_logs` | Persisted API request logs for admin review |

## Local Development

Use the infrastructure repository to run the complete project:

```bash
cd path/to/Vendora/ecommerce-infra
cp .env.example .env
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
```

The seed command prepares a demo tenant, catalog data, product images, inventory,
cart data, orders, and demo users. Credentials should be shared through the team
channel or read from the seed command output, not committed to documentation.

## Local URLs

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/api/docs/` |
| ReDoc | `http://localhost:8000/api/redoc/` |
| OpenAPI schema | `http://localhost:8000/api/schema/` |
| Django admin | `http://localhost:8000/admin/` |

Use `http://localhost:5173` for the frontend because the local CORS setting is
configured for that origin.

## Environment Configuration

Runtime values are supplied by `ecommerce-infra/.env`. Important groups:

- Database: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DB_HOST`, `DB_PORT`
- Redis: `REDIS_URL`, `CACHE_KEY_PREFIX`
- Frontend and CORS: `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`
- Email: `EMAIL_BACKEND`, `SENDGRID_API_KEY`
- Stripe: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
- AI: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- Media storage: `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_S3_CUSTOM_DOMAIN`

Do not commit real secrets or API keys.

## Product Images and Media

Source images used for local demo data are stored in:

```text
catalog/seed_images/products/
```

During `seed_demo_data`, these files are copied into the configured Django
storage and linked to `ProductImage` records. The generated `media/` directory is
local runtime output and should not be committed.

If AWS S3 variables are configured, Django stores uploaded/generated media in S3.
Otherwise, local filesystem media storage is used.

## Common Commands

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

Reset local database and containers:

```bash
docker compose down -v
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
```

## API Documentation

The backend exposes generated OpenAPI documentation:

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- Raw schema: `/api/schema/`

The test suite includes coverage that verifies the documentation views are
accessible and that the generated schema contains the required endpoint count.

## Development Notes

- Keep changes scoped to the relevant app when possible.
- Add tests for API behavior, permissions, state transitions, and service logic.
- Run migrations after pulling model changes.
- Run `seed_demo_data` after catalog or demo data changes.
- Do not commit `media/`, `staticfiles/`, virtual environments, or local secrets.
