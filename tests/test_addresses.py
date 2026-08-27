from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Address

BASE = "/api/v1/contacts"


def _work_address(**overrides) -> dict:
    return {
        "type": "Work",
        "street": "1355 Market St",
        "city": "San Francisco",
        "state": "CA",
        "postal_code": "94103",
        "country": "USA",
        "is_primary": False,
        **overrides,
    }


def test_create_contact_with_two_addresses_preserves_order(client, payload, address):
    addresses = [address, _work_address()]
    response = client.post(BASE, json={**payload, "addresses": addresses})

    assert response.status_code == 201
    body = response.json()
    assert [row["type"] for row in body["addresses"]] == ["Home", "Work"]
    assert [row["city"] for row in body["addresses"]] == ["San Francisco", "San Francisco"]
    assert all(row["id"] > 0 for row in body["addresses"])


def test_create_contact_with_no_addresses_returns_empty_array(client, payload):
    response = client.post(BASE, json={**payload, "addresses": []})

    assert response.status_code == 201
    assert response.json()["addresses"] == []


def test_get_contact_round_trips_addresses(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address, _work_address()]}).json()["id"]

    response = client.get(f"{BASE}/{contact_id}")

    assert response.status_code == 200
    assert [row["type"] for row in response.json()["addresses"]] == ["Home", "Work"]


def test_put_replaces_the_address_collection(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address]}).json()["id"]

    replacement = _work_address(city="Oakland", is_primary=True)
    response = client.put(f"{BASE}/{contact_id}", json={**payload, "addresses": [replacement]})

    assert response.status_code == 200
    assert len(response.json()["addresses"]) == 1
    assert response.json()["addresses"][0]["city"] == "Oakland"


def test_put_omitting_addresses_clears_collection(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address]}).json()["id"]

    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["addresses"] == []


def test_patch_omitting_addresses_leaves_collection_untouched(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address]}).json()["id"]

    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-415-555-0199"})

    assert response.status_code == 200
    assert response.json()["addresses"][0]["street"] == address["street"]


def test_patch_with_empty_addresses_clears_collection(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address]}).json()["id"]

    response = client.patch(f"{BASE}/{contact_id}", json={"addresses": []})

    assert response.status_code == 200
    assert response.json()["addresses"] == []


def test_address_only_patch_advances_contact_updated_at(client, payload, address):
    created = client.post(BASE, json={**payload, "addresses": [address]}).json()

    response = client.patch(f"{BASE}/{created['id']}", json={"addresses": [_work_address()]})

    assert response.status_code == 200
    assert response.json()["updated_at"] != created["updated_at"]


def test_delete_contact_cascades_to_addresses(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address, _work_address()]}).json()["id"]

    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    with SessionLocal() as db:
        remaining = db.execute(select(func.count()).select_from(Address)).scalar_one()
    assert remaining == 0


def test_rejects_more_than_one_primary_address(client, payload, address):
    response = client.post(
        BASE,
        json={**payload, "addresses": [address, _work_address(is_primary=True)]},
    )

    assert response.status_code == 422
    assert "at most one address may be marked primary" in response.text


def test_patch_rejects_more_than_one_primary_address(client, payload, address):
    contact_id = client.post(BASE, json=payload).json()["id"]

    response = client.patch(
        f"{BASE}/{contact_id}",
        json={"addresses": [address, _work_address(is_primary=True)]},
    )

    assert response.status_code == 422
    assert "at most one address may be marked primary" in response.text


def test_rejects_invalid_address_type(client, payload, address):
    response = client.post(BASE, json={**payload, "addresses": [{**address, "type": "Cabin"}]})

    assert response.status_code == 422


def test_rejects_more_than_twenty_addresses(client, payload, address):
    response = client.post(BASE, json={**payload, "addresses": [{**address, "is_primary": False}] * 21})

    assert response.status_code == 422


def test_put_reorders_addresses_using_submitted_order(client, payload, address):
    contact_id = client.post(BASE, json={**payload, "addresses": [address, _work_address()]}).json()["id"]

    response = client.put(f"{BASE}/{contact_id}", json={**payload, "addresses": [_work_address(), address]})

    assert response.status_code == 200
    assert [row["type"] for row in response.json()["addresses"]] == ["Work", "Home"]
