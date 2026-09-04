from engine.app.character_auto_resolve_routes_v1 import AutoResolveRequest
from engine.app.main import app
from engine.app.source_person_auto_resolver_v1 import _bbox


def test_auto_resolve_request_requires_workspace_revision():
    payload = AutoResolveRequest(expected_revision="revision-1")
    assert payload.expected_revision == "revision-1"


def test_auto_resolve_route_is_registered_as_explicit_post_write():
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/api/projects/{project_id}/character-assets/auto-resolve", "POST") in routes
    assert ("/api/projects/{project_id}/character-assets/auto-resolve", "GET") not in routes


def test_character_track_bbox_parser_accepts_v10_xywh_and_rejects_bad_boxes():
    assert _bbox("[100, 200, 300, 400]") == (100.0, 200.0, 300.0, 400.0)
    assert _bbox("[100, 200, 0, 400]") is None
    assert _bbox("not-json") is None
