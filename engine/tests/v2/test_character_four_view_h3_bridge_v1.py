from engine.app import character_assets_routes_v1 as routes
from engine.app import source_person_assets_v1 as people
from engine.app.h3_reference_assets_v1 import current_target_character_reference_assets_v1
from engine.tests.v2.test_character_assets_workflow_v1 import setup


def test_accepted_v2_four_views_are_consumed_by_h3_reference_bridge(monkeypatch, tmp_path):
    project, _ = setup(monkeypatch, tmp_path)
    inventory = people.inventory(project)
    inventory = people.assign(
        project,
        [inventory["observations"][0]["key"]],
        "原演员",
        None,
        inventory["revision"],
    )
    source_id = inventory["characters"][0]["id"]
    context = {"source_name": "原演员", "signature": "source-signature"}
    monkeypatch.setattr(
        routes,
        "target_context",
        lambda _: ({"source_fingerprint": "snapshot"}, {source_id: context}),
    )

    workspace = routes.save_design(
        project,
        routes.Design(
            source_character_id=source_id,
            expected_revision=inventory["revision"],
            target_name="Emma",
            appearance_profile="New adult actor in a blue suit",
            generation_prompt="Consistent fictional actor",
        ),
    )
    target = workspace["targets"][0]

    task = routes.create_task(
        project_id=project,
        task_type="CHARACTER_FOUR_VIEWS",
        title="v2 four views",
    )
    receipt = {
        "target_id": target["id"],
        "fingerprint": target["fingerprint"],
        "view_schema": routes.VIEW_SCHEMA_V2,
        "accepted": False,
    }
    routes.finish_task(task["id"], result=receipt)
    root = routes.version_root(project, task["id"])
    root.mkdir(parents=True)
    for view in routes.VIEWS_V2:
        (root / f"{view}.jpg").write_bytes(b"validated v2 reference image")

    # Starting the four-view workflow blocks fallback references until a current version is accepted.
    assert current_target_character_reference_assets_v1(target) == []

    routes.accept_views(
        task["id"],
        routes.GenerateRequest(fingerprint=target["fingerprint"]),
    )
    selected = current_target_character_reference_assets_v1(target)

    assert [path.name for path in selected] == [
        "front.jpg",
        "three_quarter.jpg",
        "side.jpg",
        "back.jpg",
    ]
