from io import BytesIO

from fastapi.testclient import TestClient


def project(client: TestClient, kind: str = "SCRIPT_TO_DRAMA") -> str:
    payload = {"name": "剧本库测试", "project_type": kind,
               "target_language": "zh-CN", "target_region": "CN"}
    if kind == "REPLICA":
        payload["source_language"] = "zh-CN"
    response = client.post("/api/v3/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_shelf_creates_independent_scripts_without_changing_current_source(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    first = client.post(f"{base}/library/paste", json={"title": "第一集", "text": "内景·医院\n甲：你好。"})
    assert first.status_code == 201, first.text
    first_id = first.json()["scripts"][0]["id"]
    assert first.json()["current_document_id"] is None
    assert not first.json()["scripts"][0]["is_active"]

    second = client.post(f"{base}/library/paste", json={"title": "第二集", "text": "外景·花园\n乙：再见。"})
    assert second.status_code == 201, second.text
    second_id = next(row["id"] for row in second.json()["scripts"] if row["title"] == "第二集")
    assert second_id != first_id
    assert second.json()["current_document_id"] is None
    assert all(not row["is_active"] for row in second.json()["scripts"])
    assert client.get(f"{base}/source").json()["text"] is None
    assert client.get(f"{base}/library/{first_id}").json()["text"] == "内景·医院\n甲：你好。"
    assert client.get(f"{base}/library/{second_id}").json()["text"] == "外景·花园\n乙：再见。"

    selected = client.post(f"{base}/library/select", json={
        "source_asset_id": first_id, "expected_current_document_id": None,
    })
    assert selected.status_code == 200, selected.text
    first_doc = selected.json()["current_document_id"]
    assert first_doc is not None
    assert client.get(f"{base}/source").json()["text"] == "内景·医院\n甲：你好。"

    imported = client.post(f"{base}/library/uploads", files=[
        ("files", ("第三集.txt", BytesIO("内景·学校\n丙：来了。".encode()), "text/plain")),
        ("files", ("第四集.md", BytesIO("外景·街道\n丁：再见。".encode()), "text/markdown")),
    ])
    assert imported.status_code == 201, imported.text
    assert len(imported.json()["scripts"]) == 4
    assert imported.json()["current_document_id"] == first_doc
    assert next(row for row in imported.json()["scripts"] if row["id"] == first_id)["is_active"]
    assert client.get(f"{base}/source").json()["text"] == "内景·医院\n甲：你好。"

    change = client.post(f"{base}/library/select", json={
        "source_asset_id": second_id, "expected_current_document_id": first_doc,
    })
    assert change.status_code == 200, change.text
    assert change.json()["current_document_id"] != first_doc
    assert client.get(f"{base}/source").json()["text"] == "外景·花园\n乙：再见。"
    assert sum(row["is_active"] for row in change.json()["scripts"]) == 1
    assert client.post(f"{base}/library/select", json={
        "source_asset_id": first_id, "expected_current_document_id": first_doc,
    }).status_code == 409


def test_edit_one_script_retains_other_text_and_versions(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama/library"
    first = client.post(f"{base}/paste", json={"title": "同文一", "text": "一样的正文"}).json()
    first_id = first["scripts"][0]["id"]
    second = client.post(f"{base}/paste", json={"title": "同文二", "text": "一样的正文"}).json()
    second_id = next(row["id"] for row in second["scripts"] if row["title"] == "同文二")
    assert second_id != first_id  # Content deduplication must not merge scripts.
    edit = client.put(f"{base}/{second_id}", json={
        "expected_revision": 1, "title": "第二集·已修改", "text": "修改后的第二份完整正文",
    })
    assert edit.status_code == 200, edit.text
    assert edit.json()["latest_revision"] == 2
    assert edit.json()["text"] == "修改后的第二份完整正文"
    assert client.get(f"{base}/{first_id}").json()["text"] == "一样的正文"
    assert client.get(f"{base}/{first_id}").json()["latest_revision"] == 1
    assert client.put(f"{base}/{second_id}", json={
        "expected_revision": 1, "title": "旧编辑", "text": "过期编辑",
    }).status_code == 409
    rename = client.put(f"{base}/{second_id}", json={
        "expected_revision": 2, "title": "仅修改名称", "text": "修改后的第二份完整正文",
    })
    assert rename.status_code == 200, rename.text
    assert rename.json()["latest_revision"] == 2
    assert client.get(f"{base}/{second_id}").json()["title"] == "仅修改名称"


def test_edit_current_script_publishes_only_its_new_source(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    first = client.post(f"{base}/library/paste", json={"title": "当前", "text": "旧正文"}).json()
    first_id = first["scripts"][0]["id"]
    second = client.post(f"{base}/library/paste", json={"title": "未选", "text": "另一份"}).json()
    second_id = next(row["id"] for row in second["scripts"] if row["title"] == "未选")
    active = client.post(f"{base}/library/select", json={
        "source_asset_id": first_id, "expected_current_document_id": None,
    }).json()
    old_document = active["current_document_id"]
    changed = client.put(f"{base}/library/{first_id}", json={
        "expected_revision": 1, "title": "当前", "text": "新正文",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["latest_revision"] == 2
    assert changed.json()["is_active"] is True
    assert client.get(f"{base}/source").json()["text"] == "新正文"
    assert client.get(f"{base}/library").json()["current_document_id"] != old_document
    assert client.get(f"{base}/library/{second_id}").json()["text"] == "另一份"


def test_legacy_source_is_adopted_and_stays_current(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    original = client.post(f"{base}/paste", json={"text": "旧接口导入的正文"})
    assert original.status_code == 201, original.text
    existing_doc = original.json()["id"]
    shelf = client.get(f"{base}/library")
    assert shelf.status_code == 200, shelf.text
    assert shelf.json()["current_document_id"] == existing_doc
    assert len(shelf.json()["scripts"]) == 1
    old_script = shelf.json()["scripts"][0]
    assert old_script["is_active"]
    assert client.get(f"{base}/library/{old_script['id']}").json()["text"] == "旧接口导入的正文"
    assert client.get(f"{base}/library").json()["scripts"][0]["id"] == old_script["id"]


def test_shelf_project_isolation_and_invalid_files(client: TestClient) -> None:
    first_id = project(client)
    second_id = project(client)
    replica_id = project(client, "REPLICA")
    first_base = f"/api/v3/projects/{first_id}/script-to-drama/library"
    second_base = f"/api/v3/projects/{second_id}/script-to-drama/library"
    first = client.post(f"{first_base}/paste", json={"title": "隐私剧本", "text": "内景·客厅\n独有对白。"})
    assert first.status_code == 201, first.text
    script_id = first.json()["scripts"][0]["id"]
    assert client.get(second_base).json()["scripts"] == []
    assert client.get(f"{second_base}/{script_id}").status_code == 404
    assert client.put(f"{second_base}/{script_id}", json={
        "expected_revision": 1, "title": "跨项目", "text": "不允许",
    }).status_code == 404
    assert client.post(f"{second_base}/select", json={"source_asset_id": script_id}).status_code == 404
    assert client.get(f"/api/v3/projects/{replica_id}/script-to-drama/library").status_code == 422
    assert client.post(f"/api/v3/projects/{replica_id}/script-to-drama/library/paste",
                       json={"title": "禁止", "text": "不允许"}).status_code == 422
    assert client.post(f"{first_base}/paste", json={"title": "../unsafe", "text": "test"}).status_code == 422
    invalid = client.post(f"{first_base}/uploads", files=[
        ("files", ("unsafe.exe", BytesIO(b"bad"), "application/octet-stream")),
    ])
    assert invalid.status_code == 422
    assert len(client.get(first_base).json()["scripts"]) == 1
