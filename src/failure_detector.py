# ============================================================
# FAILURE DETECTOR
# ============================================================


def check_action(action_result):
    """
    Check whether a single robot action was successful.
    """

    if action_result is None:
        return {
            "success": False,
            "message": "No action result received."
        }

    if not isinstance(action_result, dict):
        return {
            "success": False,
            "message": "Invalid action result."
        }

    status = action_result.get("status")

    if status == "SUCCESS":
        return {
            "success": True,
            "message": "Action completed successfully."
        }

    return {
        "success": False,
        "message": "Action failed. Recovery required."
    }


# ============================================================
# RECOVERY DECISION
# ============================================================


def recovery_action(
    action,
    attempt,
    max_attempts=3
):
    """
    Decide whether an action should be retried
    or the robot should stop.
    """

    if attempt < max_attempts:

        return {
            "action": action,
            "decision": "RETRY",
            "attempt": attempt + 1,
            "message": f"Retrying {action}..."
        }

    return {
        "action": action,
        "decision": "STOP",
        "attempt": attempt,
        "message": (
            f"Maximum retry attempts reached "
            f"for {action}."
        )
    }


# ============================================================
# COMPLETE EXECUTION ANALYSIS
# ============================================================


def analyze_execution(execution_results):
    """
    Analyze the results of the complete robot execution.
    """

    if not isinstance(execution_results, list):

        return {
            "status": "FAILED",
            "failed_actions": [],
            "message": "Invalid execution results."
        }

    failed_actions = []

    for result in execution_results:

        if not isinstance(result, dict):
            continue

        if result.get("status") != "SUCCESS":

            failed_actions.append({
                "step": result.get("step"),
                "command": result.get("command"),
                "status": result.get("status"),
                "message": result.get("message")
            })

    # --------------------------------------------------------
    # All actions successful
    # --------------------------------------------------------

    if not failed_actions:

        return {
            "status": "SUCCESS",
            "failed_actions": [],
            "message": (
                "All robot actions "
                "completed successfully."
            )
        }

    # --------------------------------------------------------
    # One or more actions failed
    # --------------------------------------------------------

    return {
        "status": "FAILED",
        "failed_actions": failed_actions,
        "message": (
            "One or more robot actions failed."
        )
    }


# ============================================================
# TESTING
# ============================================================


if __name__ == "__main__":

    print("=" * 65)
    print("🚨 FAILURE DETECTOR TEST")
    print("=" * 65)

    # --------------------------------------------------------
    # Test 1: Successful action
    # --------------------------------------------------------

    print("\nTest 1: Successful Action")

    success_result = {
        "step": 1,
        "command": "DETECT",
        "status": "SUCCESS",
        "message": "Object detected."
    }

    result = check_action(
        success_result
    )

    print("Input:", success_result)
    print("Output:", result)

    # --------------------------------------------------------
    # Test 2: Failed action
    # --------------------------------------------------------

    print("\nTest 2: Failed Action")

    failed_result = {
        "step": 2,
        "command": "MOVE",
        "status": "FAILED",
        "message": "Obstacle detected."
    }

    result = check_action(
        failed_result
    )

    print("Input:", failed_result)
    print("Output:", result)

    # --------------------------------------------------------
    # Test 3: Recovery decision
    # --------------------------------------------------------

    print("\nTest 3: Recovery Decision")

    recovery = recovery_action(
        "MOVE",
        attempt=1,
        max_attempts=3
    )

    print("Output:", recovery)

    # --------------------------------------------------------
    # Test 4: Maximum retry reached
    # --------------------------------------------------------

    print("\nTest 4: Maximum Retry Reached")

    recovery = recovery_action(
        "MOVE",
        attempt=3,
        max_attempts=3
    )

    print("Output:", recovery)

    # --------------------------------------------------------
    # Test 5: Complete successful execution
    # --------------------------------------------------------

    print("\nTest 5: Complete Successful Execution")

    successful_execution = [

        {
            "step": 1,
            "command": "DETECT",
            "status": "SUCCESS",
            "message": "Object detected."
        },

        {
            "step": 2,
            "command": "MOVE",
            "status": "SUCCESS",
            "message": "Robot moved."
        },

        {
            "step": 3,
            "command": "GRAB",
            "status": "SUCCESS",
            "message": "Object grabbed."
        },

        {
            "step": 4,
            "command": "MOVE",
            "status": "SUCCESS",
            "message": "Robot moved."
        },

        {
            "step": 5,
            "command": "RELEASE",
            "status": "SUCCESS",
            "message": "Object released."
        }
    ]

    analysis = analyze_execution(
        successful_execution
    )

    print("Analysis:")
    print(analysis)

    # --------------------------------------------------------
    # Test 6: Failed execution
    # --------------------------------------------------------

    print("\nTest 6: Failed Execution")

    failed_execution = [

        {
            "step": 1,
            "command": "DETECT",
            "status": "SUCCESS",
            "message": "Object detected."
        },

        {
            "step": 2,
            "command": "MOVE",
            "status": "FAILED",
            "message": "Obstacle detected."
        },

        {
            "step": 3,
            "command": "GRAB",
            "status": "SUCCESS",
            "message": "Object grabbed."
        }
    ]

    analysis = analyze_execution(
        failed_execution
    )

    print("Analysis:")
    print(analysis)

    print("\n" + "=" * 65)
    print("✅ FAILURE DETECTOR TEST COMPLETED")
    print("=" * 65)