import csv
import os


def load_dataset():

    file_path = os.path.join(
        "data",
        "instruction_actions.csv"
    )

    if not os.path.exists(file_path):

        print("❌ Dataset file not found:")
        print(file_path)

        return []


    dataset = []

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            dataset.append(row)


    return dataset


if __name__ == "__main__":

    data = load_dataset()

    print("=" * 60)
    print("🤖 ROBOT INSTRUCTION DATASET")
    print("=" * 60)

    print(
        f"Total records: {len(data)}"
    )

    print("=" * 60)


    if data:

        print("\nFirst 5 records:\n")

        for row in data[:5]:

            print(
                f"ID       : {row['id']}"
            )

            print(
                f"Instruction: {row['instruction']}"
            )

            print(
                f"Object   : {row['object']}"
            )

            print(
                f"Color    : {row['color']}"
            )

            print(
                f"Target   : {row['target']}"
            )

            print(
                f"Actions  : {row['actions']}"
            )

            print("-" * 60)