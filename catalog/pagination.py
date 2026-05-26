from rest_framework.pagination import CursorPagination


class ProductCursorPagination(CursorPagination):
    page_size = 24
    ordering = "id"
