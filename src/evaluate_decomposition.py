import sys
import os

# Allow imports from src when running this file directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from instruction_parser import parse_instruction
from task_decomposer import decompose_task


EXPECTED_STEPS = [
    "DETECT_OBJECT",
    "MOVE_TO_OBJECT",
    "PICK",
    "MOVE_TO_TARGET",
    "PLACE"
]


TEST_INSTRUCTIONS = [
    "Transfer the blue ball to the box",
    "Lift the red cube and put it in the box",
    "Move the red cube into the box",
    "Transfer the blue bottle to the basket",
    "Grab the green cube and put it in the box",
    "Transfer the red block to the box",
    "Pick up the green ball and put it on the table",
    "Move the red bottle into the box",
    "Lift the green block and put it into the container",
    "Move the yellow ball into the container",
    "Take the blue bottle to the basket",
    "Grab the blue block and place it inside the basket",
    "Lift the blue block and put it in the basket",
    "Transfer the red cube to the box",
    "Grab the green cube and place it inside the container",
    "Lift the green cube and put it in the container",
    "Transfer the yellow bottle to the bin",
    "Move the red block into the box",
    "Take the blue block to the basket",
    "Move the green bottle into the container"
]


def evaluate_decomposition():

    total = len(TEST_INSTRUCTIONS)
    correct = 0

    print("=" * 65)
    print("🤖 TASK DECOMPOSITION EVALUATION")
    print("=" * 65)

    for i, instruction in enumerate(TEST_INSTRUCTIONS, 1):

        parsed = parse_instruction(instruction)

        result = decompose_task(parsed)

        predicted_steps = [
            step["task"]
            for step in result
        ]

        is_correct = predicted_steps == EXPECTED_STEPS

        print(f"\nTest {i}")
        print("Instruction:", instruction)

        print("Expected:")
        print(EXPECTED_STEPS)

        print("Predicted:")
        print(predicted_steps)

        if is_correct:
            correct += 1
            print("Result: ✅ CORRECT")
        else:
            print("Result: ❌ INCORRECT")

    accuracy = (correct / total) * 100

    print("\n" + "=" * 65)
    print("📊 FINAL DECOMPOSITION EVALUATION")
    print("=" * 65)

    print("Total test instructions :", total)
    print("Correct decompositions   :", f"{correct}/{total}")
    print("Decomposition accuracy   :", f"{accuracy:.2f}%")

    if correct == total:
        print("Overall result           : ✅ SUCCESS")
    else:
        print("Overall result           : ⚠️ NEEDS IMPROVEMENT")

    print("=" * 65)


if __name__ == "__main__":
    evaluate_decomposition()