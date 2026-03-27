import shutil
import tempfile

import pytest

import app as app_module
import shared_state

_original_create_app = app_module.create_app

# Each test gets its own isolated shared state directory.
# We set this before create_app() runs so it picks up the temp path.
_test_shared_dir = None


def _create_app_no_csrf():
    if _test_shared_dir:
        shared_state._shared_dir = _test_shared_dir
    application = _original_create_app()
    application.config["WTF_CSRF_ENABLED"] = False
    if _test_shared_dir:
        # Re-set after create_app overwrites it from config
        shared_state._shared_dir = _test_shared_dir
    return application


app_module.create_app = _create_app_no_csrf


@pytest.fixture(autouse=True)
def _isolate_shared_state():
    """Give each test its own shared state directory."""
    global _test_shared_dir
    tmpdir = tempfile.mkdtemp()
    _test_shared_dir = tmpdir
    shared_state._shared_dir = tmpdir
    shared_state.init_dir()
    yield
    _test_shared_dir = None
    shutil.rmtree(tmpdir, ignore_errors=True)
