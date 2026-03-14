from collections import defaultdict, deque

from django.db.models import Q

from app.models import ItemRelationship, MediaTypes, RelationType, Status

_STATUS_PRIORITY = {
    Status.IN_PROGRESS.value: 0,
    Status.PAUSED.value: 1,
    Status.PLANNING.value: 2,
    Status.COMPLETED.value: 3,
    Status.DROPPED.value: 4,
}

_GROUPABLE_TYPES = frozenset({MediaTypes.SEASON.value, MediaTypes.ANIME.value})


def group_media_list(media_items, media_type):
    """Group related media items and return a list with group annotations.

    Grouped items have: is_group=True, group_items, group_count.
    Non-grouped items have: is_group=False.
    """
    items = list(media_items)
    if not items or media_type not in _GROUPABLE_TYPES:
        return _annotate_ungrouped(items)

    if media_type == MediaTypes.SEASON.value:
        return _apply_tv_grouping(items)
    if media_type == MediaTypes.ANIME.value:
        return _apply_anime_grouping(items)

    return _annotate_ungrouped(items)


def _annotate_ungrouped(items):
    for item in items:
        item.is_group = False
    return items


def _media_id_sortkey(media_id):
    try:
        return (0, int(media_id))
    except (ValueError, TypeError):
        return (1, media_id)


def _pick_representative(group_items):
    statuses = {m.status for m in group_items}
    all_same_status = len(statuses) == 1
    if all_same_status:
        return min(
            group_items,
            key=lambda m: (
                m.item.season_number or 0,
                _media_id_sortkey(m.item.media_id),
            ),
        )
    return min(
        group_items,
        key=lambda m: (
            _STATUS_PRIORITY.get(m.status, 99),
            m.item.season_number or 0,
            _media_id_sortkey(m.item.media_id),
        ),
    )


def _make_group_entry(group_items):
    rep = _pick_representative(group_items)
    rep.is_group = True
    rep.group_items = [m for m in group_items if m.id != rep.id]
    rep.group_count = len(group_items)
    return rep


def _apply_tv_grouping(items):
    show_groups = defaultdict(list)
    non_season = []

    for item in items:
        if item.item.media_type == MediaTypes.SEASON.value:
            key = (item.item.media_id, item.item.source)
            show_groups[key].append(item)
        else:
            non_season.append(item)

    result = []
    for group_items in show_groups.values():
        if len(group_items) == 1:
            group_items[0].is_group = False
            result.append(group_items[0])
        else:
            group_items.sort(key=lambda m: m.item.season_number or 0)
            result.append(_make_group_entry(group_items))

    for item in non_season:
        item.is_group = False
    result.extend(non_season)
    return result


def _build_relationship_graph(tracked_item_ids):
    relationships = ItemRelationship.objects.filter(
        Q(from_item_id__in=tracked_item_ids) | Q(to_item_id__in=tracked_item_ids),
        relation_type__in=[RelationType.SEQUEL, RelationType.PREQUEL],
    ).values_list("from_item_id", "to_item_id")
    graph = defaultdict(set)
    for from_id, to_id in relationships:
        graph[from_id].add(to_id)
        graph[to_id].add(from_id)
    return graph


def _bfs_component(start, graph, visited):
    component = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        component.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return component


def _find_connected_components(tracked_item_ids, graph):
    visited = set()
    groups = []
    grouped_item_ids = set()
    for item_id in tracked_item_ids:
        if item_id in visited:
            continue
        component = _bfs_component(item_id, graph, visited)
        tracked_in_component = component & tracked_item_ids
        if len(tracked_in_component) > 1:
            groups.append(tracked_in_component)
            grouped_item_ids |= tracked_in_component
    return groups, grouped_item_ids


def _build_group_result(items, groups, grouped_item_ids, item_id_to_media):
    result = []
    for group_ids in groups:
        group_items = [item_id_to_media[iid] for iid in group_ids]
        group_items.sort(key=lambda m: _media_id_sortkey(m.item.media_id))
        result.append(_make_group_entry(group_items))
    for item in items:
        if item.item_id not in grouped_item_ids:
            item.is_group = False
            result.append(item)
    return result


def _apply_anime_grouping(items):
    item_id_to_media = {m.item_id: m for m in items}
    tracked_item_ids = set(item_id_to_media.keys())
    if not tracked_item_ids:
        return _annotate_ungrouped(items)
    graph = _build_relationship_graph(tracked_item_ids)
    groups, grouped_ids = _find_connected_components(tracked_item_ids, graph)
    return _build_group_result(items, groups, grouped_ids, item_id_to_media)
