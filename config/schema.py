API_TAG_BY_PREFIX = (
    ('/api/v1/auth/', 'auth'),
    ('/api/v1/users/', 'auth'),
    ('/api/v1/tenants/', 'auth'),
    ('/api/v1/catalog/', 'catalog'),
    ('/api/v1/cart/', 'cart'),
    ('/api/v1/checkout/', 'cart'),
    ('/api/v1/chat/', 'chat'),
    ('/api/v1/orders/', 'orders'),
    ('/api/v1/webhooks/', 'orders'),
    ('/api/v1/vendor/', 'vendor'),
    ('/api/v1/admin/', 'admin'),
)

HTTP_METHODS = {
    'delete',
    'get',
    'head',
    'options',
    'patch',
    'post',
    'put',
    'trace',
}


def group_endpoints_by_domain_tag(result, generator, request, public):
    for path, path_item in result.get('paths', {}).items():
        tag = get_domain_tag(path)
        if not tag:
            continue

        for method, operation in path_item.items():
            if method.lower() in HTTP_METHODS:
                operation['tags'] = [tag]

    return result


def get_domain_tag(path):
    for prefix, tag in API_TAG_BY_PREFIX:
        if path.startswith(prefix):
            return tag
    return None
