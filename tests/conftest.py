import app as app_module

_original_create_app = app_module.create_app


def _create_app_no_csrf():
    application = _original_create_app()
    application.config["WTF_CSRF_ENABLED"] = False
    return application


app_module.create_app = _create_app_no_csrf
