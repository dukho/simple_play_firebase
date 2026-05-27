import os
import requests
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

@flask_app.get("/dev/url")
def dev_secret_url():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("Error: Slack Webhook URL secret is missing or not bound.")
        return jsonify({"error": "Slack Webhook URL secret is missing or not bound."}), 500
    return jsonify({"hook_url": webhook_url})

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

@flask_app.get("/dev/query2")
def read_query2():
    appstart_query = """
        SELECT
            event_timestamp,
            app_build_version,
            app_display_version,
            event_name,
            trace_info.duration_us,
            os_version
        FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
        WHERE
            event_type = 'DURATION_TRACE'
            AND event_name IN ('_app_start', 'app_initial_display')
            AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
    """
    rows = bq_client.query(appstart_query).result()
    data = [dict(row) for row in rows]
    return jsonify(data)

@flask_app.get("/dev/appstart")
def read_appstart():
    query = """
        SELECT
            event_timestamp,
            app_build_version,
            app_display_version,
            event_name,
            trace_info.duration_us,
            -- Calculate the 90th percentile for a realistic user experience metric
            PERCENTILE_CONT(trace_info.duration_us, 0.9) OVER(PARTITION BY app_build_version) / 1000 AS p90_duration_ms,
            os_version
        FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
        WHERE
            event_type = 'DURATION_TRACE'
            AND event_name ='_app_start'
            AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]
    return jsonify(data)

@flask_app.get("/dev/appinit")
def read_appinit():
    query = """
        SELECT
            event_timestamp,
            app_build_version,
            app_display_version,
            event_name,
            trace_info.duration_us,
            -- Calculate the 90th percentile for a realistic user experience metric
            PERCENTILE_CONT(trace_info.duration_us, 0.9) OVER(PARTITION BY app_build_version) / 1000 AS p90_duration_ms,
            os_version
        FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
        WHERE
            event_type = 'DURATION_TRACE'
            AND event_name ='app_initial_display'
            AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]
    return jsonify(data)

@https_fn.on_request(secrets=["SLACK_WEBHOOK_URL"])
def api(req: https_fn.Request) -> https_fn.Response:
    # This securely passes the incoming Firebase request into your Flask app
    with flask_app.request_context(req.environ):
        return flask_app.full_dispatch_request()