from django.db import models


class CIFieldMixin:
    """
    Field-mixin which uses case-insensitive lookup alternatives where possible
    """

    LOOKUP_CONVERSIONS = {
        "exact": "iexact",
        "contains": "icontains",
        "startswith": "istartswith",
        "endswith": "iendswith",
        "regex": "iregex",
    }

    def get_lookup(self, lookup_name):
        converted = self.LOOKUP_CONVERSIONS.get(lookup_name, lookup_name)
        return super().get_lookup(converted)


class CICharField(CIFieldMixin, models.CharField):
    """Case-insensitive CharField"""

    pass


class CIEmailField(CIFieldMixin, models.EmailField):
    """Case-insensitive EmailField"""

    pass
