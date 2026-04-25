from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_replace(context, **kwargs):
    """Return the current request querystring with the given kwargs replaced.

    Usage in templates:
        {% load url_tags %}
        <a href="?{% querystring_replace page=page_obj.next_page_number %}">Next</a>

    Preserves existing GET params (search, filters) so pagination + filters
    coexist per CLAUDE.md "Filter Implementation Rules". Equivalent to
    Django 5.1's built-in {% querystring %} tag, backported for Django 4.2.
    """
    request = context.get('request')
    params = request.GET.copy() if request else None
    if params is None:
        from django.http import QueryDict
        params = QueryDict(mutable=True)
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
