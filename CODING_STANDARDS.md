# Coding Standards

Task: #413 Write `CODING_STANDARDS.md` documenting ViewSet, serializer, service, and model conventions.

These standards keep the Django backend consistent across authentication, catalog, cart, checkout, orders, AI, notifications, inventory, vendor, and tenant features.

## General Backend Rules

- Keep code tenant-aware unless the feature is explicitly global.
- Keep views thin. Views should authenticate, authorize, validate, call services, and return responses.
- Put business workflows in `services.py`.
- Put database structure and data integrity rules in models and migrations.
- Put request and response shape rules in serializers.
- Keep functions and methods small enough to test directly.
- Prefer existing local patterns over introducing new abstractions.
- Add tests for every meaningful behavior change.
- Use `select_related()` and `prefetch_related()` for response endpoints that return related data.
- Use `transaction.atomic()` for multi-step writes that must succeed or fail together.

## View And ViewSet Conventions

The current backend mostly uses `APIView`. If a future feature uses DRF `ViewSet` or `ModelViewSet`, follow the same boundaries.

Views and ViewSets should:

- Declare `permission_classes` explicitly when the endpoint is not public.
- Use project permission classes such as `IsVendorAdmin`, `IsCustomer`, `IsStoreStaff`, or `IsSuperAdmin`.
- Use `@extend_schema` on every endpoint method or action.
- Include request serializers, response serializers, examples, and tags in Swagger documentation.
- Validate request data with serializers before calling services.
- Delegate business logic to a service class.
- Return `Response(...)` objects only from the view layer.
- Convert service exceptions into appropriate API status codes.
- Keep tenant filtering in services or query helpers, not scattered through response formatting.
- Avoid raw model writes in views unless the endpoint is a very small CRUD operation.

Recommended `APIView` shape:

```python
class ExampleView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        request=ExampleWriteSerializer,
        responses={status.HTTP_200_OK: ExampleReadSerializer},
        tags=['vendor'],
    )
    def post(self, request):
        serializer = ExampleWriteSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        instance = ExampleService.create_for_user(request.user, serializer.validated_data)
        return Response(ExampleReadSerializer(instance).data)
```

Recommended `ViewSet` shape when standard CRUD is useful:

```python
class ExampleViewSet(ModelViewSet):
    permission_classes = [IsVendorAdmin]
    lookup_field = 'slug'

    def get_queryset(self):
        return ExampleService.visible_to_user(self.request.user)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ExampleWriteSerializer
        return ExampleReadSerializer

    def perform_create(self, serializer):
        ExampleService.create_for_user(self.request.user, serializer)
```

ViewSets should not hide complicated workflows inside `perform_create()` or `perform_update()`. If a write has branching logic, cache invalidation, external calls, Celery scheduling, or multiple model updates, move it to a service method.

## Serializer Conventions

Use serializers for input validation and output representation.

Serializers should:

- Use `ModelSerializer` for model-backed request or response shapes.
- Use plain `Serializer` for non-model payloads, commands, filters, and small API responses.
- Keep list and detail serializers separate when response shapes differ.
- Use write serializers for create and update endpoints when write fields differ from read fields.
- Mark generated fields, timestamps, ids, and derived fields as read-only.
- Use `context={'request': request}` when URL building or tenant-aware querysets depend on the request.
- Restrict foreign key querysets by tenant in `__init__()` for write serializers.
- Use `validate()` for cross-field validation.
- Return clear field-level errors when possible.
- Avoid database writes in serializers except through `serializer.save()` when called by a service or view.
- Avoid calling Celery tasks, cache invalidation, external APIs, or complex domain workflows from serializers.

Naming conventions:

- `ProductListSerializer` for lightweight collection responses.
- `ProductDetailSerializer` for nested detail responses.
- `ProductCreateSerializer` or `ProductWriteSerializer` for create and update requests.
- `ExampleSummarySerializer` for nested compact objects.
- `ExampleBulkUpdateSerializer` for batch payloads.

Tenant-scoped serializer fields should use `all_objects` only when the current request tenant is applied manually:

```python
class ProductWriteSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant = getattr(getattr(self.context.get('request'), 'user', None), 'tenant', None)
        self.fields['brand'].queryset = Brand.all_objects.filter(tenant=tenant)
```

## Service Conventions

Use services for business workflows, cross-model operations, and reusable query logic.

Services should:

- Live in the app-level `services.py` file.
- Be named after the domain workflow, such as `CartService`, `OrderService`, `CatalogQueryService`, or `ProductImageService`.
- Use `@staticmethod` or `@classmethod` for stateless operations.
- Return domain objects, querysets, dictionaries, or simple values.
- Raise explicit service exceptions for expected domain failures.
- Avoid importing DRF `Response` or returning HTTP-specific objects.
- Use `transaction.atomic()` for multi-model writes.
- Use `select_for_update()` for stock, order, checkout, or inventory writes that need row locks.
- Use `transaction.on_commit()` before scheduling Celery tasks that depend on committed database rows.
- Keep cache key construction centralized in the relevant service or cache helper.
- Keep tenant filtering close to the query method.
- Prefer `get_object_or_404()` in services only when the service is directly supporting an API lookup.
- Use `all_objects` only when a service intentionally bypasses the tenant-aware manager and then applies tenant filtering manually.

Service methods should accept the user or request context needed to enforce tenant and permission boundaries:

```python
class OrderService:
    @staticmethod
    def list_customer_orders(user):
        return Order.objects.filter(
            user=user,
            tenant=user.tenant,
        ).select_related('checkout_session')
```

Write services should make ownership and tenant assignment explicit:

```python
class ProductWriteService:
    @classmethod
    def create_product(cls, user, serializer):
        return serializer.save(
            tenant=user.tenant,
            vendor=cls.get_request_vendor(user),
        )
```

## Model Conventions

Models should define database structure, relationships, constraints, indexes, and small domain helpers.

Tenant-scoped business models should:

- Inherit from `TenantModel` unless the model is intentionally global.
- Keep `tenant` populated on create.
- Use `objects` for tenant-aware queries.
- Use `all_objects` only in background jobs, admin-style operations, or services that manually apply tenant filters.
- Include indexes for common tenant, status, foreign key, and ordering lookups.
- Include database constraints for unique business rules.
- Use `TextChoices` for status fields and role-like enums.
- Use `PROTECT` when deleting a related row would break historical records.
- Use `CASCADE` for dependent children that should not outlive the parent.
- Use `SET_NULL` only when historical records can remain valid without the related object.
- Keep `__str__()` readable and stable.
- Keep model properties cheap. Avoid hidden queries in frequently serialized properties.

Model methods are appropriate for:

- State-machine transitions.
- Small derived values.
- Automatic tenant assignment when the tenant can be derived safely from a parent.
- Simple file path helpers.

Model methods should not:

- Return API responses.
- Parse request objects.
- Call external services.
- Trigger long workflows directly.
- Duplicate serializer validation.

Example tenant assignment pattern:

```python
def save(self, *args, **kwargs):
    if self.cart_id and self.tenant_id is None:
        self.tenant = self.cart.tenant
    super().save(*args, **kwargs)
```

## Query And Performance Conventions

- List endpoints should return optimized querysets.
- Detail endpoints with nested objects should use `select_related()` for single-valued relations.
- Use `prefetch_related()` or `Prefetch()` for reverse and many-valued relations.
- Avoid querying inside serializer method fields unless the queryset is already prefetched.
- Use cursor pagination for large product-style collections.
- Use service methods for reusable query optimization.
- Add tests for N+1-sensitive endpoints when possible.

## Caching And Background Task Conventions

- Keep Redis keys tenant-aware.
- Put cache key helpers in services or app cache modules.
- Invalidate caches from model signals only when the invalidation is tied to model changes.
- Use Celery tasks for slow email, report, export, AI, or notification work.
- Route tasks to named queues when the task belongs to `emails`, `ai`, or `default`.
- Use `transaction.on_commit()` when queueing work after a database write.
- Log failed task exhaustion through `FailedTask`.
- Log transactional email attempts through `EmailLog`.

## Testing Conventions

Tests should cover the layer where behavior lives:

- Serializer tests for validation and response shape.
- Service tests for business workflows and tenant boundaries.
- API tests for permissions, status codes, routing, and response contracts.
- Model tests for constraints, state transitions, and derived fields.
- Signal tests for cache invalidation, image generation, logging, and task scheduling.

When adding or changing tenant-scoped behavior, include tests that prove data from another tenant is not visible or writable.

## Formatting And Linting

- Follow `.flake8` for linting rules.
- Follow `pyproject.toml` when Black is configured.
- Run pre-commit hooks when `.pre-commit-config.yaml` is available in the branch.
- Keep generated files, local media, virtual environments, and static build output out of task commits.
