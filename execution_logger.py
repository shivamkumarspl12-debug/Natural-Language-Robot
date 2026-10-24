import json
import os
from datetime import datetime


LOG_FILE = "execution_logs.json"


def save_execution_log(
    instruction,
    actions,
    status,
    failure="NONE",
    retry_count=0,
    execution_time=0
):
    """
    Save one robot execution result.
    """

    log_entry = {
        "timestamp": datetime.now().isoformat(),

        "instruction": instruction,

        "actions": actions,

        "failure": failure,

        "retry_count": retry_count,

        "execution_time_seconds": round(
            execution_time, 2
        ),

        "status": status
    }


    # Existing logs load karo
    if os.path.exists(LOG_FILE):

        try:

            with open(
                LOG_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                logs = json.load(file)

        except (json.JSONDecodeError, OSError):

            logs = []

    else:

        logs = []


    logs.append(log_entry)


    # Save
    with open(
        LOG_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            logs,
            file,
            indent=4
        )


    print("\n📝 Execution log saved successfully.")

    return log_entry


# ==========================================
# TEST
# ==========================================

if __name__ == "__main__":

    actions = [
        "DETECT",
        "MOVE_TO_OBJECT",
        "GRAB",
        "MOVE_TO_TARGET",
        "RELEASE"
    ]


    result = save_execution_log(

        instruction=
        "Pick up the red block and put it in the box",

        actions=actions,

        status="SUCCESS",

        failure="MOVE_FAILED",

        retry_count=1,

        execution_time=5.21
    )


    print("\nSaved Record:")
    print(json.dumps(
        result,
        indent=4
    ))