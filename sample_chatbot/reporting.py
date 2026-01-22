import os
import csv
import json
import logging

from datetime import datetime

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

                    logging.info(
                        f"Report limit ({report_max_files}) reached. "
                        f"Deleting {len(files_to_delete)} oldest report(s)."
                    )

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
            return False

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
                with open(filepath, "r", newline="", encoding="utf-8") as file:
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
                logging.warning(
                    f"Report file {filepath} disappeared during feedback update."
                )
                continue
            except OSError as e:
                logging.error(
                    f"Error reading/writing report file {filepath} during feedback update: {e}"
                )
                continue

        return updated