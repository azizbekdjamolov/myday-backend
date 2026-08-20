from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """Default pagination: page-based, capped page size, metadata envelope."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LargeResultsSetPagination(StandardResultsSetPagination):
    page_size = 50
    max_page_size = 200


class NoPagination(PageNumberPagination):
    page_size = None

    def get_page_size(self, request):
        return None


def paginated_response(paginator, data: list) -> Response:
    """Build the standard paginated envelope from a serializer instance list."""
    return Response(
        {
            "results": data,
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
        }
    )