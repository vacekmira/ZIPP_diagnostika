import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, build_engine, get_db
from app.main import app


@pytest.fixture
def db(tmp_path):
    engine = build_engine(f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def project(client):
    response = client.post("/api/projects", json={
        "name": "Hala Test", "bay_count": 2, "default_truss_count": 4,
        "note": "Test", "technician_name": "Novák",
    })
    assert response.status_code == 201, response.text
    return response.json()
