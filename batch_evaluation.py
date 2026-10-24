import json
import os
import statistics
from failure_recovery import execute_with_recovery

TEST_FILE = "test.json"
RESULT_FILE = "evaluation_results.json"


def load_test_data():
    with open(TEST_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def main():
    print("\n" + "=" * 60)
    print("PHASE 8 - BATCH EVALUATION")
    print("=" * 60)

    data = load_test_data()

    total = len(data)
    successful = 0
    failed = 0
    recovery_cases = 0
    recovery_success = 0

    retry_counts = []
    execution_times = []
    results = []

    print(f"\nTotal Test Cases: {total}")

    for i, record in enumerate(data, start=1):

        instruction = record["instruction"]

        actions = record.get(
            "actions",
            [
                "DETECT",
                "MOVE_TO_OBJECT",
                "GRAB",
                "MOVE_TO_TARGET",
                "RELEASE"
            ]
        )

        execution = record.get("execution", {})

        failure_type = execution.get("failure", "NONE")

        print("\n" + "-" * 60)
        print(f"TEST CASE {i}/{total}")
        print("Instruction:", instruction)
        print("Failure Mode:", failure_type)

        result = execute_with_recovery(
            instruction,
            actions,
            failure_type
        )

        results.append({
            "test_id": record.get("id", i),
            "instruction": instruction,
            "failure_mode": failure_type,
            "retry_count": result["retry_count"],
            "execution_time_seconds": result["execution_time_seconds"],
            "status": result["status"]
        })

        retry_counts.append(result["retry_count"])
        execution_times.append(
            result["execution_time_seconds"]
        )

        if result["status"] == "SUCCESS":
            successful += 1
        else:
            failed += 1

        if failure_type != "NONE":
            recovery_cases += 1

            if result["status"] == "SUCCESS":
                recovery_success += 1

    # Metrics
    success_rate = (successful / total) * 100 if total else 0

    recovery_rate = (
        (recovery_success / recovery_cases) * 100
        if recovery_cases else 0
    )

    avg_retry = (
        statistics.mean(retry_counts)
        if retry_counts else 0
    )

    avg_time = (
        statistics.mean(execution_times)
        if execution_times else 0
    )

    evaluation = {
        "total_test_cases": total,
        "successful_executions": successful,
        "failed_executions": failed,
        "overall_success_rate_percent": round(success_rate, 2),
        "failure_cases": recovery_cases,
        "recovery_success_cases": recovery_success,
        "recovery_success_rate_percent": round(recovery_rate, 2),
        "average_retry_count": round(avg_retry, 2),
        "average_execution_time_seconds": round(avg_time, 2),
        "test_results": results
    }

    # Save results
    with open(
        RESULT_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            evaluation,
            file,
            indent=4
        )

    # Final report
    print("\n\n" + "=" * 60)
    print("FINAL EVALUATION REPORT")
    print("=" * 60)

    print(f"Total Test Cases       : {total}")
    print(f"Successful Executions  : {successful}")
    print(f"Failed Executions      : {failed}")

    print(
        f"Overall Success Rate   : "
        f"{success_rate:.2f}%"
    )

    print(f"Failure Cases           : {recovery_cases}")
    print(f"Recovery Success Cases  : {recovery_success}")

    print(
        f"Recovery Success Rate   : "
        f"{recovery_rate:.2f}%"
    )

    print(
        f"Average Retry Count    : "
        f"{avg_retry:.2f}"
    )

    print(
        f"Average Execution Time : "
        f"{avg_time:.2f} seconds"
    )

    print("\nEvaluation results saved to:")
    print(RESULT_FILE)

    print("\n" + "=" * 60)
    print("PHASE 8 EVALUATION COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()