from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app
from flask import Flask, jsonify

initialize_app()
set_global_options(max_instances=10)

flask_app = Flask(__name__)

@flask_app.get("/dev/test")
def dev_test():
    return jsonify({"message": "Hello from Flask!"})

@https_fn.on_request()
def api(req: https_fn.Request) -> https_fn.Response:
    with flask_app.request_context(req.environ):
        return flask_app.full_dispatch_request()