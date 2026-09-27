import pytest

from freezer.db import connect, init_db


@pytest.fixture
def conn(tmp_path):
    connection = connect(str(tmp_path / "test.db"))
    init_db(connection)
    yield connection
    connection.close()
