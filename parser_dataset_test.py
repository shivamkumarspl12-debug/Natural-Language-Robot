import json
import sys
import os

# Project root ko Python path mein add karo
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.instruction_parser import parse_instruction


# -----------------------------
# Load Test Dataset
# -----------------------------

with open("test.json", "r", encoding="utf-8") as file:
    test_data = json.load(file)


print("=" * 70)
print("INSTRUCTION PARSER - ROBOT DATASET EVALUATION")
print("=" * 70)

print(f"\nTest records: {len(test_data)}")


correct = 0
total = len(test_data)


# -----------------------------
# Evaluate Each Instruction
# -----------------------------

for i, record in enumerate(test_data, start=1):

    instruction = record["instruction"]

    expected_object = record["object"]["name"]
    expected_color = record["object"]["color"]
    expected_target = record["target"]["name"]

    # Expected actions
    expected_actions = record["actions"]

    # Parser
    result = parse_instruction(instruction)

    predicted_object = result.get("object")
    predicted_color = result.get("color")
    predicted_target = result.get("target")
    predicted_actions = result.get("actions", [])

    # Compare
    object_ok = predicted_object == expected_object
    color_ok = predicted_color == expected_color
    target_ok = predicted_target == expected_target

    # Actions compare
    actions_ok = predicted_actions == expected_actions

    record_correct = (
        object_ok
        and color_ok
        and target_ok
        and actions_ok
    )

    if record_correct:
        correct += 1

    print("\n" + "-" * 70)
    print(f"Test {i}")
    print(f"Instruction : {instruction}")

    print("\nExpected:")
    print(f"Object : {expected_object}")
    print(f"Color  : {expected_color}")
    print(f"Target : {expected_target}")
    print(f"Actions: {expected_actions}")

    print("\nPredicted:")
    print(f"Object : {predicted_object}")
    print(f"Color  : {predicted_color}")
    print(f"Target : {predicted_target}")
    print(f"Actions: {predicted_actions}")

    if record_correct:
        print("\nResult: PASS")
    else:
        print("\nResult: FAIL")


# -----------------------------
# Accuracy
# -----------------------------

accuracy = (correct / total) * 100


print("\n" + "=" * 70)
print("PARSER EVALUATION RESULT")
print("=" * 70)

print(f"\nCorrect instructions : {correct}/{total}")
print(f"Incorrect instructions: {total - correct}/{total}")
print(f"Accuracy              : {accuracy:.2f}%")

print("\n" + "=" * 70)