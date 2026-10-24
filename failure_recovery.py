import json
import os
import time
from datetime import datetime


MAX_RETRIES = 3
LOG_FILE = "execution_logs.json"


FAILURE_MESSAGES = {
    "OBJECT_NOT_DETECTED": "Object was not detected",
    "UNEXPECTED_OBSTACLE": "Unexpected obstacle detected",
    "MOVE_FAILED": "Robot movement failed",
    "TIMEOUT": "Operation timed out",
    "RELEASE_FAILED": "Object release failed"
}


FAILURE_ACTIONS = {
    "OBJECT_NOT_DETECTED": "DETECT",
    "UNEXPECTED_OBSTACLE": "MOVE_TO_OBJECT",
    "MOVE_FAILED": "MOVE_TO_OBJECT",
    "TIMEOUT": "MOVE_TO_OBJECT",
    "RELEASE_FAILED": "RELEASE"
}


def save_log(
    instruction,
    actions,
    status,
    failure,
    retry_count,
    execution_time
):

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


    return log_entry


def execute_action(
    action,
    failure_type,
    failure_used
):

    print(f"  Executing: {action}")

    time.sleep(0.4)


    # Failure sirf relevant action par inject hoga
    if (
        failure_type != "NONE"
        and not failure_used
        and FAILURE_ACTIONS.get(
            failure_type
        ) == action
    ):

        print(
            "  ❌ FAILURE:",
            FAILURE_MESSAGES.get(
                failure_type,
                failure_type
            )
        )

        return False


    print(
        f"  ✅ {action} SUCCESS"
    )

    return True


def execute_with_recovery(
    instruction,
    actions,
    failure_type="NONE"
):

    start_time = time.time()

    retry_count = 0
    failure_used = False


    print("\n" + "=" * 55)

    print("INSTRUCTION:")
    print(instruction)

    print("\nACTION SEQUENCE:")

    print(" → ".join(actions))

    print("\nFAILURE MODE:")
    print(failure_type)

    print("=" * 55)


    action_index = 0


    while action_index < len(actions):

        action = actions[action_index]


        success = execute_action(
            action,
            failure_type,
            failure_used
        )


        if success:

            action_index += 1

            continue


        # Failure detected
        failure_used = True

        retry_count += 1


        print(
            f"  🔄 Recovery attempt "
            f"{retry_count}/{MAX_RETRIES}"
        )


        if retry_count > MAX_RETRIES:

            execution_time = (
                time.time() - start_time
            )


            print("\n❌ MAX RETRIES EXCEEDED")
            print("❌ Overall Execution FAILED")


            log = save_log(
                instruction,
                actions,
                "FAILED",
                failure_type,
                retry_count,
                execution_time
            )


            return log


        print(
            "  🔧 Recovery / replanning performed"
        )


        time.sleep(0.5)


        # Same failed action dobara execute hoga


    execution_time = (
        time.time() - start_time
    )


    print("\n🎉 Overall Execution SUCCESS")


    log = save_log(
        instruction,
        actions,
        "SUCCESS",
        failure_type,
        retry_count,
        execution_time
    )


    return log


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


    instruction = (
        "Pick up the red block "
        "and put it in the box"
    )


    print(
        "\nTEST 1: NORMAL EXECUTION"
    )

    result1 = execute_with_recovery(
        instruction,
        actions,
        "NONE"
    )


    print("\nRESULT:")
    print(result1)


    print(
        "\nTEST 2: MOVE FAILURE"
    )

    result2 = execute_with_recovery(
        instruction,
        actions,
        "MOVE_FAILED"
    )


    print("\nRESULT:")
    print(result2)


    print(
        "\nTEST 3: DETECTION FAILURE"
    )

    result3 = execute_with_recovery(
        instruction,
        actions,
        "OBJECT_NOT_DETECTED"
    )


    print("\nRESULT:")
    print(result3)