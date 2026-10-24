import json
import sys
import os

# Project root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.instruction_parser import parse_instruction


def decompose_task(parsed_data):
    """
    Convert parsed natural-language instruction
    into robot-oriented atomic subtasks.
    """

    object_name = parsed_data.get("object")
    color = parsed_data.get("color")
    target = parsed_data.get("target")

    if not object_name or not target:
        return []

    steps = [
        {
            "step": 1,
            "action": "DETECT",
            "description": f"Detect the {color} {object_name}"
        },
        {
            "step": 2,
            "action": "MOVE_TO_OBJECT",
            "description": f"Move robot to the {color} {object_name}"
        },
        {
            "step": 3,
            "action": "GRAB",
            "description": f"Grab the {color} {object_name}"
        },
        {
            "step": 4,
            "action": "MOVE_TO_TARGET",
            "description": f"Move the {object_name} to the {target}"
        },
        {
            "step": 5,
            "action": "RELEASE",
            "description": f"Release the {object_name} in the {target}"
        }
    ]

    return steps


# -----------------------------------------
# Test with test.json
# -----------------------------------------

with open("test.json", "r", encoding="utf-8") as file:
    test_data = json.load(file)


print("=" * 70)
print("ROBOT TASK DECOMPOSITION EVALUATION")
print("=" * 70)

successful = 0

for index, record in enumerate(test_data, start=1):

    instruction = record["instruction"]

    print("\n" + "-" * 70)
    print(f"Test {index}")
    print("Instruction:", instruction)

    # Parser
    parsed = parse_instruction(instruction)

    # Decompose
    steps = decompose_task(parsed)

    # Expected robot actions
    expected_actions = [
        "DETECT",
        "MOVE_TO_OBJECT",
        "GRAB",
        "MOVE_TO_TARGET",
        "RELEASE"
    ]

    predicted_actions = [
        step["action"]
        for step in steps
    ]

    # Check
    if predicted_actions == expected_actions:
        successful += 1
        result = "PASS"
    else:
        result = "FAIL"

    print("\nParsed:")
    print(json.dumps(parsed, indent=4))

    print("\nTask Decomposition:")

    for step in steps:
        print(
            f"{step['step']}. "
            f"{step['action']} → "
            f"{step['description']}"
        )

    print("\nExpected Actions:")
    print(expected_actions)

    print("\nResult:", result)


# -----------------------------------------
# Final Result
# -----------------------------------------

accuracy = (successful / len(test_data)) * 100

print("\n" + "=" * 70)
print("TASK DECOMPOSITION RESULT")
print("=" * 70)

print(f"\nSuccessful decompositions : {successful}/{len(test_data)}")
print(f"Failed decompositions     : {len(test_data) - successful}/{len(test_data)}")
print(f"Decomposition accuracy    : {accuracy:.2f}%")

print("\nTask decomposition completed.")