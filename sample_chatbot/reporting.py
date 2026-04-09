import os
import csv
import json
import logging

from datetime import datetime

# Upper bound for a single CSV field when reading reports (avoids multi‑GB allocations if a file is corrupt or hostile).
# Kept separate from the per-chatbot report file size so a mis-set config cannot request unbounded memory.
CSV_FIELD_HARD_CAP_BYTES = 100 * 1024 * 1024

def _csv_field_limit_bytes_for_read(report_max_size_mb):
    mb = max(1, int(report_max_size_mb or 1))
    file_budget = mb * 1024 * 1024
    return min(CSV_FIELD_HARD_CAP_BYTES, file_budget)

def _apply_csv_field_limit(limit_bytes):
    limit = int(limit_bytes)
    while limit > 0:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10
    for fallback in (2**31 - 1, 10**9, 50 * 1024 * 1024, 10 * 1024 * 1024, 1024 * 1024):
        try:
            csv.field_size_limit(fallback)
            return
        except (OverflowError, ValueError):
            continue
    logging.warning("Could not set csv.field_size_limit; feedback CSV reads may fail on moderately large cells.")

def get_report_filename(report_max_size_mb, report_max_files, report_folder="reports", base_filename="user_report"):
    base_path = os.path.join(report_folder, base_filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    report_max_size_bytes = report_max_size_mb * 1024 * 1024

    try:
        existing_files = [
            f
            for f in os.listdir(report_folder)
            if f.startswith(base_filename) and f.endswith(".csv")
        ]
    except FileNotFoundError:
        existing_files = []

    if not existing_files:
        return f"{base_path}_{timestamp}.csv"

    full_file_paths = [os.path.join(report_folder, f) for f in existing_files]

    latest_file = max(
        full_file_paths,
        key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
    )

    try:
        if os.path.exists(latest_file) and os.path.getsize(latest_file) >= report_max_size_bytes:
            if report_max_files > 0:
                num_to_delete = len(existing_files) - (report_max_files - 1)

                if num_to_delete > 0:
                    sorted_files = sorted(
                        full_file_paths,
                        key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0,
                    )

                    files_to_delete = sorted_files[:num_to_delete]

                    logging.info(f"Report limit ({report_max_files}) reached. Deleting {len(files_to_delete)} oldest report(s).")

                    for f_path in files_to_delete:
                        try:
                            os.remove(f_path)
                        except OSError as e:
                            logging.error(f"Error deleting old report file {f_path}: {e}")

            return f"{base_path}_{timestamp}.csv"
    except FileNotFoundError:
        return f"{base_path}_{timestamp}.csv"

    return latest_file


def write_to_report(
    report_lock,
    report_max_size_mb,
    report_max_files,
    question,
    answer,
    username,
    report_folder="reports",
    base_filename="user_report",
):
    event_type = answer.get("type")
    if event_type not in ("done", "tool_end"):
        return

    with report_lock:
        filename = get_report_filename(
            report_max_size_mb,
            report_max_files,
            report_folder,
            base_filename,
        )
        file_exists = os.path.exists(filename)

        try:
            with open(filename, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file, delimiter=";")

                if not file_exists:
                    writer.writerow(
                        [
                            "uuid",
                            "timestamp",
                            "type",
                            "question",
                            "answer",
                            "chatbot_llm",
                            "tool_name",
                            "tool_call_id",
                            "tool_content",
                            "tool_artifact",
                            "user",
                            "feedback",
                            "feedback_details",
                        ]
                    )

                timestamp = datetime.now().isoformat()
                uuid = answer.get("uuid", "")

                if event_type == "done":
                    final_answer = answer.get("answer", "")
                    if isinstance(final_answer, str):
                        final_answer = final_answer.split("<related_question>")[0].strip()
                    else:
                        final_answer = str(final_answer)

                    chatbot_llm = answer.get("chatbot_llm", "")
                    row = [
                        uuid,
                        timestamp,
                        event_type,
                        question,
                        final_answer,
                        chatbot_llm,
                        "",
                        "",
                        "",
                        "",
                        username,
                        "not_received",
                        "",
                    ]
                else:
                    tool_name = answer.get("tool_name", "")
                    tool_call_id = answer.get("tool_call_id", "")
                    content = answer.get("content", "")
                    artifact = answer.get("artifact", "")

                    if not isinstance(content, str):
                        try:
                            content = json.dumps(content, ensure_ascii=False)
                        except (TypeError, ValueError):
                            content = str(content)

                    if not isinstance(artifact, str):
                        try:
                            artifact = json.dumps(artifact, ensure_ascii=False)
                        except (TypeError, ValueError):
                            artifact = str(artifact)

                    row = [
                        uuid,
                        timestamp,
                        event_type,
                        question,
                        "",
                        "",
                        tool_name,
                        tool_call_id,
                        content,
                        artifact,
                        username,
                        "not_received",
                        "",
                    ]

                writer.writerow(row)
        except OSError as e:
            logging.error(f"Error writing to report file {filename}: {e}")

def update_feedback_in_report(
    report_lock,
    report_max_size_mb,
    uuid,
    feedback_value,
    feedback_details,
    report_folder="reports",
    base_filename="user_report",
):
    with report_lock:
        _apply_csv_field_limit(_csv_field_limit_bytes_for_read(report_max_size_mb))
        try:
            report_files = [
                f
                for f in os.listdir(report_folder)
                if f.startswith(base_filename) and f.endswith(".csv")
            ]
        except FileNotFoundError:
            logging.error(
                f"Report directory '{report_folder}' not found during feedback update."
            )
            return {
                "success": False,
                "error": "report_directory_missing",
                "message": "Feedback could not be saved because the report directory is missing on the server.",
            }

        report_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(report_folder, f))
            if os.path.exists(os.path.join(report_folder, f))
            else 0,
            reverse=True,
        )

        updated = False

        for report_file in report_files:
            filepath = os.path.join(report_folder, report_file)
            rows = []
            found_in_this_file = False

            try:
                with open(filepath, newline="", encoding="utf-8") as file:
                    reader = csv.reader(file, delimiter=";")
                    try:
                        header = next(reader)
                        rows.append(header)
                    except StopIteration:
                        continue

                    for row in reader:
                        if len(row) > 0 and row[0] == uuid:
                            while len(row) < 13:
                                row.append("")
                            row[11] = feedback_value
                            row[12] = feedback_details
                            found_in_this_file = True
                            updated = True
                        rows.append(row)

                if found_in_this_file:
                    with open(filepath, "w", newline="", encoding="utf-8") as file:
                        writer = csv.writer(file, delimiter=";")
                        writer.writerows(rows)

                    break

            except FileNotFoundError:
                logging.warning(f"Report file {filepath} disappeared during feedback update.")
                continue
            except csv.Error as e:
                basename = os.path.basename(filepath)
                err_str = str(e)
                if "field larger than field limit" in err_str:
                    logging.error(
                        f"""
Failed to update feedback for question id {uuid} because the report row reached the system's memory limit (CSV field size cap).
The user's feedback for question id {uuid} was: value={feedback_value!r}, details={feedback_details!r}.
Please update it manually in the report file {filepath}
"""
                    )
                    err_code = "report_csv_field_limit"
                else:
                    logging.error(
                        f"""
Failed to update feedback for question id {uuid} because reading the report CSV failed ({e}).
The user's feedback for question id {uuid} was: value={feedback_value!r}, details={feedback_details!r}.
Please update it manually in the report file {filepath}
"""
                    )
                    err_code = "report_csv_parse_error"
                msg = f"""
Feedback could not be saved while reading the report ({basename}): {err_str}.
Your feedback was: value={feedback_value!r}, details={feedback_details!r}.
Please update the feedback columns manually in that CSV on the server.
"""
                return {
                    "success": False,
                    "error": err_code,
                    "message": msg,
                }
            except MemoryError:
                basename = os.path.basename(filepath)
                logging.error(
                    f"""
Failed to update feedback for question id {uuid} because the report row exceeded the system's memory limit while loading the CSV.
The user's feedback for question id {uuid} was: value={feedback_value!r}, details={feedback_details!r}.
Please update it manually in the report file {filepath}
"""
                )
                msg = f"""
Feedback could not be saved because the report row is too large to process in memory ({basename}).
Your feedback was: value={feedback_value!r}, details={feedback_details!r}.
Please update the feedback columns manually in that CSV on the server.
"""
                return {
                    "success": False,
                    "error": "report_memory_limit",
                    "message": msg,
                }
            except OSError as e:
                logging.error(f"Error reading/writing report file {filepath} during feedback update: {e}")
                continue

        if not updated:
            return {
                "success": False,
                "error": "uuid_not_found",
                "message": "Failed to save feedback. No matching conversation was found in the report files.",
            }
        return {"success": True}
