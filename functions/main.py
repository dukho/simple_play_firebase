import os
import requests
from firebase_functions import https_fn, scheduler_fn, logger
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app
from flask import Flask, jsonify, request
from google.cloud import bigquery

initialize_app()
set_global_options(max_instances=10)

flask_app = Flask(__name__)

bq_client = bigquery.Client()  # reuse across requests (module-level)

@flask_app.get("/dev/test")
def dev_test():
    logger.error("This is test ERROR")
    logger.info("This is test INFO")
    return jsonify({"message": "Hello from Flask!"})

@flask_app.get("/dev/url")
def dev_secret_url():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("Error: Slack Webhook URL secret is missing or not bound.")
        return jsonify({"error": "Slack Webhook URL secret is missing or not bound."}), 500
    return jsonify({"hook_url": webhook_url})

# use query param 'message' to customize the Slack message
@flask_app.get("/dev/slack")
def dev_slack_test():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        return jsonify({"error": "Secret not found"}), 500
    
    message = request.args.get("message", "Hello from Flask!")
    
    # Send the alert to Slack
    slack_message = {"text": f"✴️ Hello from functions: {message}"}
    response = requests.post(webhook_url, json=slack_message)
    
    if response.status_code == 200:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"error": "Failed to send to Slack"}), 500

def report_to_slack(webhook_url, message_json):
    if not webhook_url:
        print("Error: Slack Webhook URL secret is missing or not bound.")
        return

    response = requests.post(webhook_url, json=message_json)

    if response.status_code == 200:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"error": "Failed to send to Slack"}), 500

def generate_report(title, data):
  message = f"Checking {title}"

  if len(data) == 0:
    message = message + """
      No data available
    """
    
  elif len(data) == 1:
    entry = data[0]
    message = message + f"""
      version {entry['app_display_version']} ({entry['app_build_version']}) time = {entry['duration_ms']:.2f} msec
    """

  else:
    for i in range(len(data) - 1):
      current_entry = data[i]
      previous_entry = data[i + 1]

      current_time = current_entry['duration_ms']
      previous_time = previous_entry['duration_ms']

      delta = current_time - previous_time
      change_percentile = (delta / previous_time) * 100 if previous_time != 0 else float('inf')
      message = message + f"""
        version {current_entry['app_display_version']} ({current_entry['app_build_version']}) time = {current_entry['duration_ms']:.2f} msec, delta = {delta:.2f} msec ({change_percentile:.2f}%)
      """

  return message

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

# _app_start, but p90 only
@flask_app.get("/dev/appstart_p90")
def read_appstart_p90():
    query = """
        WITH VersionStats AS (
            SELECT
                app_build_version,
                app_display_version,
                event_timestamp,
                -- Calculate the 90th percentile for a realistic user experience metric
                PERCENTILE_CONT(trace_info.duration_us, 0.9) OVER(PARTITION BY app_build_version) / 1000 AS p90_duration_ms,
                os_version
            FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
            WHERE
                event_type = 'DURATION_TRACE'
                AND event_name ='_app_start'
                AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
        )
        SELECT
        app_build_version,
        app_display_version,
        MAX(p90_duration_ms) as duration_ms
        FROM VersionStats
        GROUP BY app_build_version, app_display_version
        ORDER BY
            app_build_version DESC,
            app_display_version DESC
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]
    return jsonify(data)

@flask_app.get("/dev/appinit_p90")
def read_appinit_p90():
    query = """
        WITH VersionStats AS (
            SELECT
                app_build_version,
                app_display_version,
                event_timestamp,
                -- Calculate the 90th percentile for a realistic user experience metric
                PERCENTILE_CONT(trace_info.duration_us, 0.9) OVER(PARTITION BY app_build_version) / 1000 AS p90_duration_ms,
                os_version
            FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
            WHERE
                event_type = 'DURATION_TRACE'
                AND event_name ='app_initial_display'
                AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
        )
        SELECT
        app_build_version,
        app_display_version,
        MAX(p90_duration_ms) as duration_ms
        FROM VersionStats
        GROUP BY app_build_version, app_display_version
        ORDER BY
            app_build_version DESC,
            app_display_version DESC
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]
    return jsonify(data)


# _app_start, report to slack
@flask_app.get("/dev/appstart_report")
def read_appstart_report():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Error: Slack Webhook URL secret is missing or not bound.")
        return jsonify({"error": "Slack Webhook URL secret is missing or not bound."}), 500
    report_appstart(webhook_url)

def report_appstart(webhook_url):
    query = """
        WITH VersionStats AS (
            SELECT
                app_build_version,
                app_display_version,
                event_timestamp,
                -- Calculate the 90th percentile for a realistic user experience metric
                PERCENTILE_CONT(trace_info.duration_us, 0.9) OVER(PARTITION BY app_build_version) / 1000 AS p90_duration_ms,
                os_version
            FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
            WHERE
                event_type = 'DURATION_TRACE'
                AND event_name ='_app_start'
                AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
        )
        SELECT
        app_build_version,
        app_display_version,
        MAX(p90_duration_ms) as duration_ms
        FROM VersionStats
        GROUP BY app_build_version, app_display_version
        ORDER BY
            app_build_version DESC,
            app_display_version DESC
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]

    report_message = generate_report("App Start Time (_app_start)", data)
    return report_to_slack(webhook_url, {"text": report_message})

@flask_app.get("/dev/appinit_report")
def read_appinit_report():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Error: Slack Webhook URL secret is missing or not bound.")
        return jsonify({"error": "Slack Webhook URL secret is missing or not bound."}), 500
    report_appinit(webhook_url)

def report_appinit(webhook_url):
    query = """
        WITH VersionStats AS (
            SELECT
                app_build_version,
                app_display_version,
                event_timestamp,
                -- Calculate the 90th percentile for a realistic user experience metric
                PERCENTILE_CONT(trace_info.duration_us, 0.9) OVER(PARTITION BY app_build_version) / 1000 AS p90_duration_ms,
                os_version
            FROM `simpleplay-c585b.firebase_performance.com_nomad_simpleplay_ANDROID`
            WHERE
                event_type = 'DURATION_TRACE'
                AND event_name ='app_initial_display'
                AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
        )
        SELECT
        app_build_version,
        app_display_version,
        MAX(p90_duration_ms) as duration_ms
        FROM VersionStats
        GROUP BY app_build_version, app_display_version
        ORDER BY
            app_build_version DESC,
            app_display_version DESC
    """
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]

    report_message = generate_report("App Initial Display Time (app_initial_display)", data)
    return report_to_slack(webhook_url, {"text": report_message})

@https_fn.on_request(secrets=["SLACK_WEBHOOK_URL"])
def api(req: https_fn.Request) -> https_fn.Response:
    # This securely passes the incoming Firebase request into your Flask app
    with flask_app.request_context(req.environ):
        return flask_app.full_dispatch_request()

@scheduler_fn.on_schedule(
    schedule="*/10 * * * *",
    secrets=["SLACK_WEBHOOK_URL"]
)
def scheduled_slack_alert(event: scheduler_fn.ScheduledEvent) -> None:
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not slack_webhook_url:
        logger.error("Error: SLACK_WEBHOOK_URL secret is not available.")
        return

    logger.info("Ok, scheduled_slack_alert can proceed")

    # Send the alert to Slack
    report_appstart(slack_webhook_url)
    report_appinit(slack_webhook_url)