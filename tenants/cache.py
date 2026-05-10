from tenants.middleware import get_current_tenant


def tenant_cache_key(key, key_prefix, version):
    tenant = get_current_tenant()
    tenant_prefix = f'tenant:{tenant.id}' if tenant else 'tenant:public'
    return f'{key_prefix}:{tenant_prefix}:v{version}:{key}'
