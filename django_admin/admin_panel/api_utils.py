import re
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


def to_camel_case(name: str) -> str:
    if '_' not in name:
        return name
    parts = [p for p in name.split('_') if p]
    if not parts:
        return name
    return parts[0] + ''.join(p[:1].upper() + p[1:] for p in parts[1:])


def to_snake_case(name: str) -> str:
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def expand_dual_case(obj, *, max_depth: int = 16, max_nodes: int = 10000):
    nodes = 0

    def _walk(val, depth):
        nonlocal nodes
        if depth > max_depth:
            raise ParseError('Слишком глубокая вложенность JSON.')
        nodes += 1
        if nodes > max_nodes:
            raise ParseError('Слишком большой объект JSON.')
        if isinstance(val, list):
            return [_walk(item, depth + 1) for item in val]
        if not isinstance(val, dict):
            return val
        result = {k: _walk(v, depth + 1) for k, v in val.items()}
        for key, value in list(result.items()):
            if not isinstance(key, str):
                continue
            for alias in (to_camel_case(key), to_snake_case(key)):
                if alias and alias not in result:
                    result[alias] = value
        return result

    return _walk(obj, 0)


class DualCaseJSONParser(JSONParser):
    """JSON parser that seamlessly accepts both camelCase and snake_case keys."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type=media_type, parser_context=parser_context)
        return expand_dual_case(data)


def qparam(request, *names, default=None):
    for name in names:
        if name in request.query_params:
            return request.query_params.get(name)
        snake = to_snake_case(name)
        if snake in request.query_params:
            return request.query_params.get(snake)
        camel = to_camel_case(name)
        if camel in request.query_params:
            return request.query_params.get(camel)
    return default


def parse_bool_param(value):
    if value is None:
        return None
    low = str(value).strip().lower()
    if low in ('true', '1', 'yes', 'on'):
        return True
    if low in ('false', '0', 'no', 'off'):
        return False
    return None


def resolve_ordering(raw_ordering, allowed_map, default_ordering):
    if not raw_ordering:
        return default_ordering
    resolved = []
    for part in str(raw_ordering).split(','):
        token = part.strip()
        if not token:
            continue
        desc = token.startswith('-')
        key = token[1:] if desc else token
        field = allowed_map.get(key) or allowed_map.get(to_snake_case(key)) or allowed_map.get(to_camel_case(key))
        if field:
            resolved.append(('-' + field) if desc else field)
    return resolved or default_ordering


def paginate_list_or_qs(request, qs_or_list, *, max_unpaginated: int = 200):
    raw_page = qparam(request, 'page')
    raw_limit = qparam(request, 'limit', 'pageSize', 'page_size')
    if raw_page is None and raw_limit is None:
        return None, list(qs_or_list[:max_unpaginated])
    try:
        page = max(1, int(raw_page or 1))
        limit = min(200, max(1, int(raw_limit or 50)))
    except ValueError:
        return {'error': 'Invalid pagination'}, None
    total = qs_or_list.count() if hasattr(qs_or_list, 'count') else len(qs_or_list)
    start = (page - 1) * limit
    items = list(qs_or_list[start:start + limit])
    meta = {
        'total': total,
        'page': page,
        'limit': limit,
        'totalPages': max(1, (total + limit - 1) // limit),
    }
    return meta, items
