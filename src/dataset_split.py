import csv
import os
import random


DATASET_PATH = os.path.join(
    "data",
    "instruction_actions.csv"
)


TRAIN_PATH = os.path.join(
    "data",
    "train.csv"
)


TEST_PATH = os.path.join(
    "data",
    "test.csv"
)


# ============================================================
# LOAD DATASET
# ============================================================

def load_dataset():

    with open(
        DATASET_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        data = list(reader)

    return data


# ============================================================
# SAVE DATASET
# ============================================================

def save_dataset(
    data,
    file_path,
    fieldnames
):

    with open(
        file_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(data)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "🤖 DATASET TRAIN / TEST SPLIT"
    )

    print("=" * 60)


    # Load
    data = load_dataset()


    print(
        f"Total records: {len(data)}"
    )


    # Shuffle
    random.seed(42)

    random.shuffle(data)


    # 80% training
    train_size = int(
        len(data) * 0.8
    )


    train_data = data[:train_size]

    test_data = data[train_size:]


    # Fields
    fieldnames = [
        "id",
        "instruction",
        "object",
        "color",
        "target",
        "actions"
    ]


    # Save
    save_dataset(
        train_data,
        TRAIN_PATH,
        fieldnames
    )


    save_dataset(
        test_data,
        TEST_PATH,
        fieldnames
    )


    print(
        f"Training records: {len(train_data)}"
    )

    print(
        f"Testing records : {len(test_data)}"
    )


    print("=" * 60)

    print("✅ Dataset split completed.")

    print("=" * 60)


if __name__ == "__main__":

    main()