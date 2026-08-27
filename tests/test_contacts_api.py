BASE = "/api/v1/contacts"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_create_contact(client, payload):
    response = client.post(BASE, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Lovelace"
    assert body["created_at"] and body["updated_at"]


def test_create_requires_valid_email(client, payload):
    response = client.post(BASE, json={**payload, "email": "not-an-email"})
    assert response.status_code == 422


def test_create_requires_names(client, payload):
    response = client.post(BASE, json={**payload, "first_name": ""})
    assert response.status_code == 422


def test_duplicate_email_conflicts(client, payload):
    assert client.post(BASE, json=payload).status_code == 201
    response = client.post(BASE, json={**payload, "email": "ADA@example.com"})
    assert response.status_code == 409


def test_get_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.get(f"{BASE}/{contact_id}")
    assert response.status_code == 200
    assert response.json()["id"] == contact_id


def test_get_missing_contact_returns_404(client):
    assert client.get(f"{BASE}/9999").status_code == 404


def test_list_pagination_and_total(client, payload):
    for index in range(5):
        client.post(BASE, json={**payload, "email": f"user{index}@example.com"})

    response = client.get(BASE, params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_search(client, payload):
    client.post(BASE, json=payload)
    client.post(
        BASE,
        json={**payload, "first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com", "company": "US Navy"},
    )

    hits = client.get(BASE, params={"search": "hopper"}).json()
    assert hits["total"] == 1
    assert hits["items"][0]["last_name"] == "Hopper"

    by_company = client.get(BASE, params={"search": "navy"}).json()
    assert by_company["total"] == 1

    misses = client.get(BASE, params={"search": "nobody"}).json()
    assert misses["total"] == 0


def test_list_sorting(client, payload):
    client.post(BASE, json={**payload, "last_name": "Zhang", "email": "z@example.com"})
    client.post(BASE, json={**payload, "last_name": "Adams", "email": "a@example.com"})

    names = [
        item["last_name"]
        for item in client.get(BASE, params={"sort_by": "last_name", "order": "asc"}).json()["items"]
    ]
    assert names == ["Adams", "Zhang"]


def test_list_rejects_bad_sort_field(client):
    assert client.get(BASE, params={"sort_by": "; DROP TABLE contacts"}).status_code == 422


def test_patch_updates_only_sent_fields(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-000-000-0000"})
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+1-000-000-0000"
    assert body["first_name"] == "Ada"
    assert body["company"] == "Analytical Engines"


def test_patch_duplicate_email_conflicts(client, payload):
    first = client.post(BASE, json=payload).json()["id"]
    client.post(BASE, json={**payload, "email": "grace@example.com"})
    response = client.patch(f"{BASE}/{first}", json={"email": "grace@example.com"})
    assert response.status_code == 409


def test_patch_same_email_is_allowed(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"email": payload["email"]})
    assert response.status_code == 200


def test_put_replaces_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["company"] is None  # omitted fields are cleared by PUT


def test_put_missing_contact_returns_404(client):
    response = client.put(
        f"{BASE}/9999",
        json={"first_name": "A", "last_name": "B", "email": "ab@example.com"},
    )
    assert response.status_code == 404


def test_delete_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    assert client.get(f"{BASE}/{contact_id}").status_code == 404
    assert client.delete(f"{BASE}/{contact_id}").status_code == 404


def test_root_lists_entrypoints(client):
    body = client.get("/").json()
    assert body["contacts"] == BASE


def test_contact_has_no_photo_by_default(client, payload):
    body = client.post(BASE, json=payload).json()
    assert body["photo"] is None


def test_create_contact_with_photo(client, payload, photo):
    response = client.post(BASE, json={**payload, "photo": photo})
    assert response.status_code == 201
    assert response.json()["photo"] == photo

    contact_id = response.json()["id"]
    assert client.get(f"{BASE}/{contact_id}").json()["photo"] == photo


def test_photo_must_be_a_data_url(client, payload):
    response = client.post(BASE, json={**payload, "photo": "https://example.com/ada.png"})
    assert response.status_code == 422


def test_photo_rejects_svg(client, payload):
    # SVG can carry script, so it is not in the allow-list even though browsers render it.
    svg = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="
    assert client.post(BASE, json={**payload, "photo": svg}).status_code == 422


def test_photo_rejects_contents_that_are_not_an_image(client, payload):
    # Correctly formed base64 claiming to be a PNG, but the bytes are text.
    disguised = "data:image/png;base64,bm90IGFuIGltYWdl"
    assert client.post(BASE, json={**payload, "photo": disguised}).status_code == 422


def test_photo_rejects_signature_only_png(client, payload):
    truncated = "data:image/png;base64,iVBORw0KGgo="
    assert client.post(BASE, json={**payload, "photo": truncated}).status_code == 422


def test_photo_rejects_oversized_image(client, payload):
    from app.photo import MAX_PHOTO_BYTES

    oversized = "data:image/png;base64," + "A" * ((MAX_PHOTO_BYTES + 2) // 3 * 4 + 4)
    assert client.post(BASE, json={**payload, "photo": oversized}).status_code == 422


def test_patch_preserves_photo(client, payload, photo):
    contact_id = client.post(BASE, json={**payload, "photo": photo}).json()["id"]

    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-415-555-0199"})
    assert response.status_code == 200
    assert response.json()["photo"] == photo


def test_patch_can_clear_photo(client, payload, photo):
    contact_id = client.post(BASE, json={**payload, "photo": photo}).json()["id"]

    response = client.patch(f"{BASE}/{contact_id}", json={"photo": None})
    assert response.status_code == 200
    assert response.json()["photo"] is None


def test_put_replaces_photo(client, payload, photo):
    contact_id = client.post(BASE, json=payload).json()["id"]

    added = client.put(f"{BASE}/{contact_id}", json={**payload, "photo": photo})
    assert added.status_code == 200
    assert added.json()["photo"] == photo

    # PUT is a full replace: omitting the photo clears it, same as every other
    # optional field. Clients that only want to change one field should PATCH.
    cleared = client.put(f"{BASE}/{contact_id}", json=payload)
    assert cleared.json()["photo"] is None
