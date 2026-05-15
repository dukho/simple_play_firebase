from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app
from flask import Flask, jsonify
from google.cloud import bigquery

initialize_app()
set_global_options(max_instances=10)

flask_app = Flask(__name__)

bq_client = bigquery.Client()  # reuse across requests (module-level)

@flask_app.get("/dev/test")
def dev_test():
    return jsonify({"message": "Hello from Flask!"})

@flask_app.get("/dev/query")
def read_query():
    query = """
        SELECT
            event_timestamp,
            app_build_version,
            event_name,
            trace_info.duration_us,
            country,
            os_version,
            device_name
        FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
        WHERE event_type = 'DURATION_TRACE'
        AND event_name IN ('_app_start', 'app_initial_display')
        LIMIT 50
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]
    return jsonify(data)

@https_fn.on_request()
def api(req: https_fn.Request) -> https_fn.Response:
    with flask_app.request_context(req.environ):
        return flask_app.full_dispatch_request()