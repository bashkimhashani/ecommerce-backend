# Entity Relationship Diagram

Task: #410 Create entity-relationship diagram covering all 20+ models.

This document covers the custom application models in the backend. It excludes Django framework tables such as auth groups, sessions, admin logs, and token blacklist tables.

## Model Coverage

The backend currently defines 21 custom application models:

| App | Models |
| --- | --- |
| `tenants` | `Tenant` |
| `users` | `User` |
| `vendor` | `VendorProfile` |
| `catalog` | `Brand`, `Category`, `Product`, `ProductVariant`, `ProductImage` |
| `inventory` | `Inventory` |
| `cart` | `Cart`, `CartItem` |
| `checkout` | `CheckoutSession` |
| `orders` | `Order`, `OrderItem`, `OrderEvent` |
| `ai` | `AIReport`, `Conversation`, `ConversationMessage` |
| `notifications` | `EmailLog`, `FailedTask` |
| `request_logs` | `RequestLog` |

Most business models inherit from `TenantModel`, which adds an optional `tenant_id` foreign key to `Tenant`. `RequestLog.tenant_id` stores the tenant id as a plain indexed integer, not as a database-enforced foreign key.

## ER Diagram

```mermaid
erDiagram
    USER ||--o{ TENANT : owns
    TENANT ||--o{ USER : contains
    TENANT ||--o{ VENDOR_PROFILE : contains
    USER ||--|| VENDOR_PROFILE : has

    TENANT ||--o{ BRAND : scopes
    TENANT ||--o{ CATEGORY : scopes
    TENANT ||--o{ PRODUCT : scopes
    TENANT ||--o{ PRODUCT_VARIANT : scopes
    TENANT ||--o{ PRODUCT_IMAGE : scopes
    CATEGORY ||--o{ CATEGORY : parent_of
    BRAND ||--o{ PRODUCT : brands
    CATEGORY ||--o{ PRODUCT : categorizes
    VENDOR_PROFILE ||--o{ PRODUCT : sells
    PRODUCT ||--o{ PRODUCT_VARIANT : has
    PRODUCT ||--o{ PRODUCT_IMAGE : has

    TENANT ||--o{ INVENTORY : scopes
    VENDOR_PROFILE ||--o{ INVENTORY : manages
    PRODUCT_VARIANT ||--o| INVENTORY : stocked_as

    TENANT ||--o{ CART : scopes
    TENANT ||--o{ CART_ITEM : scopes
    USER ||--o{ CART : owns
    CART ||--o{ CART_ITEM : contains
    PRODUCT_VARIANT ||--o{ CART_ITEM : selected_as

    TENANT ||--o{ CHECKOUT_SESSION : scopes
    USER ||--o{ CHECKOUT_SESSION : starts
    CART ||--o{ CHECKOUT_SESSION : checked_out_by

    TENANT ||--o{ ORDER : scopes
    TENANT ||--o{ ORDER_ITEM : scopes
    TENANT ||--o{ ORDER_EVENT : scopes
    USER ||--o{ ORDER : places
    CHECKOUT_SESSION ||--o| ORDER : creates
    ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT_VARIANT ||--o{ ORDER_ITEM : purchased_as
    ORDER ||--o{ ORDER_EVENT : records

    TENANT ||--o{ AI_REPORT : scopes
    TENANT ||--o{ CONVERSATION : scopes
    TENANT ||--o{ CONVERSATION_MESSAGE : scopes
    CONVERSATION ||--o{ CONVERSATION_MESSAGE : includes

    TENANT ||--o{ EMAIL_LOG : scopes
    TENANT ||--o{ FAILED_TASK : scopes
    TENANT ||--o{ REQUEST_LOG : referenced_by_tenant_id

    TENANT {
        bigint id PK
        string name
        string slug UK
        string domain UK
        bigint owner_id FK
        string plan
        boolean is_active
        datetime created_at
        datetime updated_at
    }

    USER {
        bigint id PK
        string email UK
        string first_name
        string last_name
        string role
        bigint tenant_id FK
        string phone
        boolean is_email_verified
        image avatar
        image avatar_thumbnail
        boolean is_active
        boolean is_staff
        datetime date_joined
        datetime updated_at
    }

    VENDOR_PROFILE {
        bigint id PK
        bigint user_id FK
        bigint tenant_id FK
        string store_name
        text store_description
        url logo
        string contact_email
        string contact_phone
        boolean is_active
        float rating
        decimal total_sales
        datetime created_at
        datetime updated_at
    }

    BRAND {
        bigint id PK
        bigint tenant_id FK
        string name
        string slug
        image logo
        string country_of_origin
        text description
        datetime created_at
        datetime updated_at
    }

    CATEGORY {
        bigint id PK
        bigint tenant_id FK
        string name
        string slug
        bigint parent_id FK
        url icon_url
        boolean is_active
        text description
        int tree_id
        int lft
        int rght
        int level
        datetime created_at
        datetime updated_at
    }

    PRODUCT {
        bigint id PK
        bigint tenant_id FK
        string name
        string slug
        string sku
        text description
        bigint brand_id FK
        bigint category_id FK
        bigint vendor_id FK
        string status
        decimal base_price
        json tech_specs
        datetime created_at
        datetime updated_at
    }

    PRODUCT_VARIANT {
        bigint id PK
        bigint tenant_id FK
        bigint product_id FK
        string color
        string storage
        string ram
        decimal variant_price
        int stock_quantity
        datetime created_at
        datetime updated_at
    }

    PRODUCT_IMAGE {
        bigint id PK
        bigint tenant_id FK
        bigint product_id FK
        image image
        image thumbnail
        image medium
        image large
        string alt_text
        int sort_order
        boolean is_primary
        datetime created_at
        datetime updated_at
    }

    INVENTORY {
        bigint id PK
        bigint tenant_id FK
        bigint product_variant_id FK
        bigint vendor_id FK
        int quantity
        int low_stock_threshold
        datetime created_at
        datetime last_updated
    }

    CART {
        bigint id PK
        bigint tenant_id FK
        bigint user_id FK
        string session_key
        string status
        datetime created_at
        datetime updated_at
    }

    CART_ITEM {
        bigint id PK
        bigint tenant_id FK
        bigint cart_id FK
        bigint product_variant_id FK
        int quantity
        decimal unit_price
        datetime created_at
        datetime updated_at
    }

    CHECKOUT_SESSION {
        bigint id PK
        bigint tenant_id FK
        bigint user_id FK
        bigint cart_id FK
        string idempotency_key
        json shipping_address
        string status
        datetime created_at
        datetime updated_at
    }

    ORDER {
        bigint id PK
        bigint tenant_id FK
        bigint user_id FK
        bigint checkout_session_id FK
        string order_number UK
        string status
        json shipping_address
        decimal subtotal
        decimal total_amount
        datetime created_at
        datetime updated_at
    }

    ORDER_ITEM {
        bigint id PK
        bigint tenant_id FK
        bigint order_id FK
        bigint product_variant_id FK
        string product_name
        string variant_label
        int quantity
        decimal unit_price
        decimal line_total
        datetime created_at
    }

    ORDER_EVENT {
        bigint id PK
        bigint tenant_id FK
        bigint order_id FK
        string from_status
        string to_status
        string transition
        text note
        json metadata
        datetime created_at
    }

    AI_REPORT {
        bigint id PK
        bigint tenant_id FK
        string report_type
        text content
        datetime generated_at
        int prompt_tokens
        int completion_tokens
    }

    CONVERSATION {
        bigint id PK
        bigint tenant_id FK
        string session_id
        datetime created_at
        datetime updated_at
    }

    CONVERSATION_MESSAGE {
        bigint id PK
        bigint tenant_id FK
        bigint conversation_id FK
        string role
        text content
        datetime created_at
    }

    EMAIL_LOG {
        bigint id PK
        bigint tenant_id FK
        string task_name
        string recipient
        string subject
        string status
        string related_object_id
        text message
        text error
        datetime created_at
    }

    FAILED_TASK {
        bigint id PK
        bigint tenant_id FK
        string task_name
        json arguments
        text exception
        text traceback
        datetime created_at
    }

    REQUEST_LOG {
        bigint id PK
        string method
        text path
        int status_code
        decimal response_time_ms
        bigint tenant_id
        datetime created_at
    }
```

## Relationship Summary

- `Tenant` is the main isolation boundary for users, vendors, catalog data, carts, checkout sessions, orders, AI records, notifications, and failed Celery tasks.
- `User` belongs to one tenant and can also own tenants through `Tenant.owner`.
- `VendorProfile` is one-to-one with `User` and belongs to one tenant.
- `Product` belongs to one `Brand`, one `Category`, and optionally one `VendorProfile`.
- `Category` is hierarchical through its self-referencing `parent` field and django-mptt tree fields.
- `ProductVariant` and `ProductImage` belong to `Product`.
- `Inventory` connects a `VendorProfile` to a `ProductVariant`, with one inventory row per tenant and variant.
- `Cart` belongs to either a user or a guest session key, and `CartItem` connects carts to product variants.
- `CheckoutSession` connects a user and cart before order creation.
- `Order` is created from one checkout session, has many `OrderItem` rows, and records status changes through `OrderEvent`.
- `Conversation` stores chat sessions and owns ordered `ConversationMessage` rows.
- `EmailLog` records transactional email send attempts, while `FailedTask` records exhausted background task failures.
- `RequestLog` stores request telemetry and keeps `tenant_id` as an indexed scalar value instead of an enforced FK.
