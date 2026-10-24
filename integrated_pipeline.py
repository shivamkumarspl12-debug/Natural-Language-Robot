# ============================================================
# 🍽️ AI RESTAURANT SERVICE ROBOT
# FULL INTEGRATED PIPELINE
# ============================================================

import json
import time

from src.instruction_parser import parse_instruction
from src.task_decomposer import decompose_task
from src.action_generator import generate_action_sequence
from src.robot_controller import RobotController
from src.failure_detector import check_action, analyze_execution


# ============================================================
# FULL RESTAURANT PIPELINE
# ============================================================

def run_pipeline(instruction):

    print("=" * 70)
    print("🍽️ AI RESTAURANT SERVICE ROBOT")
    print("🤖 NATURAL LANGUAGE TO ROBOT ACTION PIPELINE")
    print("=" * 70)

    start_time = time.time()

    # ========================================================
    # STEP 1 — INSTRUCTION PARSER
    # ========================================================

    print("\n" + "=" * 70)
    print("STEP 1 — 🧠 INSTRUCTION PARSER")
    print("=" * 70)

    print("Customer Instruction:")
    print(instruction)

    parsed_instruction = parse_instruction(instruction)

    print("\nParsed Instruction:")

    print(
        json.dumps(
            parsed_instruction,
            indent=4
        )
    )

    if not parsed_instruction:

        return {
            "success": False,
            "error": "Instruction parsing failed."
        }

    if (
        parsed_instruction.get("intent") == "DELIVERY"
        and "orders" in parsed_instruction
    ):
        from app import execute_delivery_orders

        result, _status_code = execute_delivery_orders(
            instruction,
            parsed_instruction,
        )
        return result

    # ========================================================
    # STEP 2 — TASK DECOMPOSITION
    # ========================================================

    print("\n" + "=" * 70)
    print("STEP 2 — 🔹 TASK DECOMPOSITION")
    print("=" * 70)

    task_steps = decompose_task(
        parsed_instruction
    )

    if not task_steps:

        return {
            "success": False,
            "error": "Task decomposition failed.",
            "parser": parsed_instruction
        }

    for step in task_steps:

        print(
            f"{step['step']}. "
            f"{step['task']} - "
            f"{step['description']}"
        )

    # ========================================================
    # STEP 3 — ACTION GENERATION
    # ========================================================

    print("\n" + "=" * 70)
    print("STEP 3 — ⚙️ ACTION GENERATION")
    print("=" * 70)

    action_objects = generate_action_sequence(
        task_steps
    )

    if not action_objects:

        return {
            "success": False,
            "error": "Action generation failed.",
            "parser": parsed_instruction,
            "task_decomposition": task_steps
        }

    for action in action_objects:

        print(
            f"{action['step']}. "
            f"{action['action']} "
            f"(from {action['source_task']})"
        )

    robot_commands = [
        action["action"]
        for action in action_objects
    ]

    print("\nRobot Commands:")
    print(robot_commands)

    # ========================================================
    # STEP 4 — ROBOT CONTROLLER
    # ========================================================

    print("\n" + "=" * 70)
    print("STEP 4 — 🤖 RESTAURANT ROBOT CONTROLLER")
    print("=" * 70)

    color = parsed_instruction.get(
        "color",
        ""
    )

    obj = parsed_instruction.get(
        "object",
        ""
    )

    item = parsed_instruction.get(
        "item",
        ""
    )

    target = parsed_instruction.get(
        "target",
        ""
    )

    quantity = parsed_instruction.get(
        "quantity",
        1
    )

    intent = parsed_instruction.get(
        "intent",
        ""
    )

    # --------------------------------------------------------
    # Object / Item Name
    # --------------------------------------------------------

    if color and obj:

        full_object_name = (
            f"{color} {obj}"
        )

    elif item:

        full_object_name = item

    else:

        full_object_name = obj

    print(
        f"Intent: {intent}"
    )

    print(
        f"Item/Object: {full_object_name}"
    )

    print(
        f"Quantity: {quantity}"
    )

    print(
        f"Target/Table: {target}"
    )

    # --------------------------------------------------------
    # Create Robot
    # --------------------------------------------------------

    robot = RobotController()

    execution = robot.execute_sequence(
        robot_commands,
        object_name=full_object_name,
        target=target
    )

    # ========================================================
    # DISPLAY ROBOT EXECUTION
    # ========================================================

    print("\nRobot Execution Results:")

    for result in execution["results"]:

        print(
            f"Step {result['step']} | "
            f"{result['command']} | "
            f"{result['status']} | "
            f"Attempts: {result['attempts']}"
        )

    # ========================================================
    # STEP 5 — FAILURE DETECTION
    # ========================================================

    print("\n" + "=" * 70)
    print("STEP 5 — 🚨 FAILURE DETECTION & RECOVERY")
    print("=" * 70)

    checked_results = []

    for result in execution["results"]:

        check = check_action(
            result
        )

        checked_results.append({

            "step": result["step"],

            "command": result["command"],

            "status": result["status"],

            "attempts": result["attempts"],

            "success": check["success"],

            "message": check["message"]

        })

        print(
            f"Step {result['step']} "
            f"{result['command']} → "
            f"{'SUCCESS' if check['success'] else 'FAILED'}"
        )

    # ========================================================
    # FAILURE ANALYSIS
    # ========================================================

    failure_analysis = analyze_execution(
        execution["results"]
    )

    print("\nFailure Analysis:")

    print(
        json.dumps(
            failure_analysis,
            indent=4
        )
    )

    # ========================================================
    # STEP 6 — FINAL RESULT
    # ========================================================

    execution_time = (
        time.time() - start_time
    )

    overall_status = (
        execution["overall_status"]
    )

    final_result = {

        "project":
            "AI-Powered Natural Language Restaurant Service Robot",

        "instruction":
            instruction,

        "intent":
            intent,

        "item":
            full_object_name,

        "quantity":
            quantity,

        "target":
            target,

        "parser":
            parsed_instruction,

        "task_decomposition":
            task_steps,

        "action_sequence":
            action_objects,

        "robot_commands":
            robot_commands,

        "robot_execution":
            execution,

        "checked_execution":
            checked_results,

        "failure_analysis":
            failure_analysis,

        "overall_status":
            overall_status,

        "execution_time_seconds":
            round(
                execution_time,
                3
            ),

        "success":
            overall_status == "SUCCESS"
    }

    # ========================================================
    # SAVE RESULT
    # ========================================================

    with open(
        "pipeline_result.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            final_result,
            file,
            indent=4
        )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n" + "=" * 70)
    print("📊 FINAL RESTAURANT ROBOT RESULT")
    print("=" * 70)

    print(
        "Intent:",
        intent
    )

    print(
        "Item:",
        full_object_name
    )

    print(
        "Target:",
        target
    )

    print(
        "Overall Status:",
        overall_status
    )

    print(
        "Failure Analysis:",
        failure_analysis["status"]
    )

    print(
        "Execution Time:",
        round(
            execution_time,
            3
        ),
        "seconds"
    )

    print(
        "\n💾 Result saved to:"
    )

    print(
        "pipeline_result.json"
    )

    print("\n" + "=" * 70)

    if overall_status == "SUCCESS":

        print(
            "✅ RESTAURANT ROBOT TASK COMPLETED SUCCESSFULLY"
        )

    else:

        print(
            "❌ RESTAURANT ROBOT TASK FAILED"
        )

    print("=" * 70)

    return final_result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # 🍽️ RESTAURANT DEMO COMMAND
    # --------------------------------------------------------

    instruction = (
        "Deliver the water bottle "
        "to table 3."
    )

    run_pipeline(
        instruction
    )