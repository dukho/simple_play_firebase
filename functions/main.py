import json
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
    # @#sym:dev_test
    test_key = os.environ.get("TEST_KEY", "")
    logger.info(f"TEST_KEY from runtime env: {test_key}")
    logger.error("This is test ERROR")
    logger.info("This is test INFO")
    return jsonify({"message": "Hello from Flask!", "test_key": test_key})

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
        logger.error(f"Failed to send to Slack: {response.status_code} - {response.text}")
        return jsonify({"error": "Failed to send to Slack"}), 500

def generate_report_block_json(title, metric, data):
    blocks = []

    blocks.append({
        'type': 'section',
        'text': {
            'type': 'mrkdwn',
            'text': f"Checking *{title}*, (`{metric}`)"
        }
    })

    if len(data) == 0:
        blocks.append({
            'type': 'section',
            'text': {
                'type': 'plain_text',
                'text': "No data available"
            }
        })
    elif len(data) == 1:
        current_entry = data[0]
        current_time = int(current_entry['duration_ms'])
        formatted_current_time = format_milliseconds(current_time)
        blocks.append({
            'type': 'section',
            'text': {
                'type': 'plain_text',
                'text': f"version {current_entry['app_display_version']} ({current_entry['app_build_version']}) time = {formatted_current_time}"
            }
        })
    else:
        blocks.append({
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': "```\n" + format_result_in_table(data) + "\n```"
            }
        })
    return {
        "blocks": blocks
    }

def format_result_in_table(data):
    col_widths = [12, 12, 25, 25, 10]  # version, build, duration, delta, change%

    def row(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, col_widths))

    lines = [
        row(["version", "build", "duration", "delta", "change %"]),
        "-" * (sum(col_widths) + 2 * (len(col_widths) - 1)),
    ]

    for i in range(len(data) - 1):
        current = data[i]
        previous = data[i + 1]
        current_time = int(current['duration_ms'])
        previous_time = int(previous['duration_ms'])
        delta = current_time - previous_time
        change = (delta / previous_time) * 100 if previous_time != 0 else float('inf')
        lines.append(row([
            current['app_display_version'],
            current['app_build_version'],
            format_milliseconds(current_time),
            format_milliseconds(delta),
            f"{change:.2f} %",
        ]))

    return "\n".join(lines)

def format_milliseconds(ms):
    if ms == 0:
        return "0 ms"

    # 1. Track the sign and convert ms to a positive number
    is_negative = ms < 0
    ms = abs(ms)

    # Define time constants in milliseconds
    ms_in_sec = 1000
    ms_in_min = ms_in_sec * 60
    ms_in_hr = ms_in_min * 60
    ms_in_day = ms_in_hr * 24

    # 2. Extract each time unit
    days = ms // ms_in_day
    ms %= ms_in_day

    hours = ms // ms_in_hr
    ms %= ms_in_hr

    minutes = ms // ms_in_min
    ms %= ms_in_min

    seconds = ms // ms_in_sec
    msecs = ms % ms_in_sec

    # 3. Build the final string dynamically
    time_parts = []
    if days > 0:
        time_parts.append(f"{days} d")
    if hours > 0:
        time_parts.append(f"{hours} h")
    if minutes > 0:
        time_parts.append(f"{minutes} m")
    if seconds > 0:
        time_parts.append(f"{seconds} s")
    if msecs > 0:
        time_parts.append(f"{msecs} ms")

    formatted_time = " ".join(time_parts)

    # 4. Add the negative sign if the initial input was negative
    if is_negative:
        formatted_time = f"- {formatted_time}"

    return formatted_time

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

# _app_start, report to slack
@flask_app.get("/dev/appstart_report")
def read_appstart_report():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Error: Slack Webhook URL secret is missing or not bound.")
        return jsonify({"error": "Slack Webhook URL secret is missing or not bound."}), 500
    return report_appstart(webhook_url)

def report_appstart(webhook_url):
    query = build_query_for("_app_start")
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]

    report_message_json = generate_report_block_json("App Start Time", "_app_start", data)
    return report_to_slack(webhook_url, report_message_json)

@flask_app.get("/dev/appinit_report")
def read_appinit_report():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Error: Slack Webhook URL secret is missing or not bound.")
        return jsonify({"error": "Slack Webhook URL secret is missing or not bound."}), 500
    return report_appinit(webhook_url)

def report_appinit(webhook_url):
    query = build_query_for("app_initial_display")
    rows = bq_client.query(query).result()
    data = [dict(row) for row in rows]

    report_message_json = generate_report_block_json("App Initial Display Time", "app_initial_display", data)
    return report_to_slack(webhook_url, report_message_json)


def build_query_for(event_name, interval_in_days = 60):
    query = f"""
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
                AND event_name ='{event_name}'
                AND event_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {interval_in_days} DAY)
                AND app_build_version != '99000'
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
    return query

@https_fn.on_request(secrets=["SLACK_WEBHOOK_URL"])
def api(req: https_fn.Request) -> https_fn.Response:
    # This securely passes the incoming Firebase request into your Flask app
    with flask_app.request_context(req.environ):
        return flask_app.full_dispatch_request()

@scheduler_fn.on_schedule(
    schedule="0 */12 * * *",
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