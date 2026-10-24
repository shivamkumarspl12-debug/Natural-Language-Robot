import csv
import os

from instruction_parser import parse_instruction


TEST_PATH = os.path.join(
    "data",
    "test.csv"
)


# ============================================================
# LOAD TEST DATA
# ============================================================

def load_test_data():

    with open(
        TEST_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        return list(reader)


# ============================================================
# NORMALIZE ACTIONS
# ============================================================

def normalize_actions(actions):

    if not actions:
        return []

    return [
        action.strip().upper()
        for action in actions.split(",")
        if action.strip()
    ]


# ============================================================
# CHECK PARSER RESULT
# ============================================================

def check_result(
    prediction,
    actual
):

    correct = 0
    total = 4


    # Object
    if (
        prediction.get("object")
        == actual.get("object")
    ):

        correct += 1


    # Color
    if (
        prediction.get("color")
        == actual.get("color")
    ):

        correct += 1


    # Target
    if (
        prediction.get("target")
        == actual.get("target")
    ):

        correct += 1


    # Actions
    predicted_actions = set(
        prediction.get(
            "actions",
            []
        )
    )

    actual_actions = set(
        normalize_actions(
            actual.get(
                "actions",
                ""
            )
        )
    )


    if predicted_actions == actual_actions:

        correct += 1


    return correct, total


# ============================================================
# MAIN EVALUATION
# ============================================================

def main():

    print("=" * 65)

    print(
        "🤖 INSTRUCTION PARSER EVALUATION"
    )

    print("=" * 65)


    test_data = load_test_data()


    total_fields = 0

    correct_fields = 0

    completely_correct = 0


    for index, row in enumerate(
        test_data,
        start=1
    ):


        instruction = row[
            "instruction"
        ]


        print(
            f"\nTest {index}"
        )

        print(
            f"Instruction: {instruction}"
        )


        # Parse instruction
        prediction = parse_instruction(
            instruction
        )


        # Compare
        correct, total = check_result(
            prediction,
            row
        )


        total_fields += total

        correct_fields += correct


        if correct == total:

            completely_correct += 1

            status = "✅ CORRECT"

        else:

            status = "❌ PARTIAL / INCORRECT"


        print(
            f"Object predicted : "
            f"{prediction.get('object')}"
        )

        print(
            f"Color predicted  : "
            f"{prediction.get('color')}"
        )

        print(
            f"Target predicted : "
            f"{prediction.get('target')}"
        )

        print(
            f"Actions predicted: "
            f"{prediction.get('actions')}"
        )


        print(
            f"Result: {status}"
        )


    # ========================================================
    # ACCURACY
    # ========================================================

    if total_fields > 0:

        field_accuracy = (
            correct_fields
            / total_fields
        ) * 100

    else:

        field_accuracy = 0


    if len(test_data) > 0:

        complete_accuracy = (
            completely_correct
            / len(test_data)
        ) * 100

    else:

        complete_accuracy = 0


    # ========================================================
    # FINAL RESULT
    # ========================================================

    print("\n")

    print("=" * 65)

    print(
        "📊 FINAL EVALUATION"
    )

    print("=" * 65)


    print(
        f"Total test instructions : "
        f"{len(test_data)}"
    )


    print(
        f"Correct fields          : "
        f"{correct_fields}/{total_fields}"
    )


    print(
        f"Field-level accuracy    : "
        f"{field_accuracy:.2f}%"
    )


    print(
        f"Completely correct      : "
        f"{completely_correct}/{len(test_data)}"
    )


    print(
        f"Complete instruction accuracy: "
        f"{complete_accuracy:.2f}%"
    )


    print("=" * 65)


if __name__ == "__main__":

    main()