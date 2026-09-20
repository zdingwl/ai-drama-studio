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


def test_script_shelf_create_switch_and_invalidate_old_source(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    first = client.post(f"{base}/library/paste", json={
        "title": "第一份", "text": "内景·医院\n甲：你好。",
    })
    assert first.status_code == 201, first.text
    first_doc_id = first.json()["current_document_id"]
    first_asset_id = first.json()["scripts"][0]["id"]
    assert first.json()["scripts"][0]["is_active"]

    second = client.post(f"{base}/library/paste", json={
        "title": "第二份", "text": "外景·花园\n乙：再见。",
    })
    assert second.status_code == 201, second.text
    result = second.json()
    assert len(result["scripts"]) == 2
    assert result["current_document_id"] != first_doc_id
    assert client.get(f"{base}/source").json()["text"] == "外景·花园\n乙：再见。"

    selected = client.post(f"{base}/library/select", json={
        "source_asset_id": first_asset_id,
        "expected_current_document_id": result["current_document_id"],
    })
    assert selected.status_code == 200, selected.text
    new_doc = selected.json()["current_document_id"]
    assert new_doc not in {first_doc_id, result["current_document_id"]}
    assert client.get(f"{base}/source").json()["text"] == "内景·医院\n甲：你好。"
    assert len([row for row in selected.json()["scripts"] if row["is_active"]]) == 1
    assert client.get(f"{base}/state").json()["analysis"]["status"] == "NOT_BUILT"

    stale_request = client.post(f"{base}/library/select", json={
        "source_asset_id": result["scripts"][0]["id"],
        "expected_current_document_id": result["current_document_id"],
    })
    assert stale_request.status_code == 409
    assert stale_request.json()["error"]["code"] == "SCRIPT_TO_DRAMA_LIBRARY_SELECTION_CONFLICT"


def test_script_shelf_batch_upload_uses_existing_source_contract(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama"
    response = client.post(f"{base}/library/uploads", files=[
        ("files", ("第一集.txt", BytesIO("内景·学校\n甲：你好。".encode()), "text/plain")),
        ("files", ("第二集.md", BytesIO("外景·街道\n乙：再见。".encode()), "text/markdown")),
    ])
    assert response.status_code == 201, response.text
    result = response.json()
    assert len(result["scripts"]) == 2
    assert sum(item["is_active"] for item in result["scripts"]) == 1
    assert next(item for item in result["scripts"] if item["is_active"])["title"] == "第二集"
    assert client.get(f"{base}/source").json()["text"] == "外景·街道\n乙：再见。"


def test_script_shelf_cannot_read_or_select_other_projects_or_replica(client: TestClient) -> None:
    first_id = project(client)
    second_id = project(client)
    replica_id = project(client, "REPLICA")
    first_base = f"/api/v3/projects/{first_id}/script-to-drama/library"
    second_base = f"/api/v3/projects/{second_id}/script-to-drama/library"
    first = client.post(f"{first_base}/paste", json={"title": "隐私剧本", "text": "内景·客厅\n独有对白。"})
    assert first.status_code == 201
    asset_id = first.json()["scripts"][0]["id"]
    assert client.get(second_base).json()["scripts"] == []
    denied = client.post(f"{second_base}/select", json={"source_asset_id": asset_id})
    assert denied.status_code == 404
    assert client.get(f"/api/v3/projects/{replica_id}/script-to-drama/library").status_code == 422
    assert client.post(f"/api/v3/projects/{replica_id}/script-to-drama/library/paste",
                       json={"title": "禁止", "text": "不允许"}).status_code == 422


def test_script_shelf_rejects_path_titles_and_unsupported_batch_files(client: TestClient) -> None:
    project_id = project(client)
    base = f"/api/v3/projects/{project_id}/script-to-drama/library"
    assert client.post(f"{base}/paste", json={"title": "../unsafe", "text": "test"}).status_code == 422
    invalid = client.post(f"{base}/uploads", files=[
        ("files", ("unsafe.exe", BytesIO(b"bad"), "application/octet-stream")),
    ])
    assert invalid.status_code == 422
    assert client.get(base).json()["scripts"] == []
