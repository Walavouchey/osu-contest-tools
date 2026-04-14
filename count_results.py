# /// script
# requires-python = ">=3.14"
# ///

"""
You'll need a `judges.csv` file with "id" and "username" fields for each judge.
This one has to be created manually.

You'll also need a `spoiler.csv` file with at least a "masked_name" field. As a
contest host you should've received this file when results were anonymised.

If the contest has categories that the entries compete in separately, add a
"category" column to the `spoiler.csv` file to specify the category of each
entry. The the output files will get a `-{category}` suffix appended to them.

Run (or ask an osu! team member to run) `!export-contest-results <id>` and save
the resulting 4 json files into a `results` folder beside this script:

- judges.csv
- spoiler.csv
- results
  - judge_votes.json
  - judge_scores.json
  - entries.json
  - categories.json

Run this script with `uv run count_results.py` if you have uv installed,
or `python count_results.py` assuming you have python >=3.14 installed

Outputs 3 files (or more, in the case of multiple categories):

- results.json  # stats ordered by standardised scoring
- results.csv  # same thing except without the "sql" or nested "votes" column
- results.md  # markdown table for the wiki
"""


import argparse
import csv
import json
import re
import sys
import os
from statistics import mean
from math import sqrt

def read_json(file):
    with open(file, "r", encoding="utf-8") as file:
        return json.loads(file.read())


def read_csv(file):
    with open(file, "r", encoding="utf-8", newline="") as file:
        reader =csv.DictReader(file)
        return list(reader)


def first(iterable, predicate):
    return list(filter(predicate, iterable))[0]


def where(iterable, predicate):
    return list(filter(predicate, iterable))


def sanitise_file_name(string, replacement=" "):
    for c in ["<", ">", ":", "\"", "/", "\\", "*", "?"]:
        string = string.replace(c, replacement)
    return string


def sanitise(string):
    for c in ["\\", "_", "~", "|", "<", ">", "[", "]"]:
        string = string.replace(c, "\\" + c)
    string = re.sub(r"!$", r"\!", string)
    return string

def parse_args(args):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-f", "--folder", action='store', default="results", help="folder with the exported results .json file (\"results\" by default)")
    return parser.parse_args(args)

def main(*args):
    args = parse_args(args)
    exit_code = 0

    votes = read_json(f"{args.folder}/judge_votes.json")
    scores = read_json(f"{args.folder}/judge_scores.json")
    entry_ids = read_json(f"{args.folder}/entries.json")
    judging_categories = read_json(f"{args.folder}/categories.json")
    category_by_id = {e["id"]: {"name": e["name"], "max_value": e["max_value"]} for e in judging_categories}

    entries_full = read_csv("spoiler.csv")

    entry_categories = set(entry.get("category", "") for entry in entries_full)

    for entry_category in entry_categories:

        if entry_category:
            entries = list(filter(lambda entry: entry["category"] == entry_category, entries_full))
            category_suffix = "-" + entry_category
        else:
            entries = entries_full
            category_suffix = ""

        for entry in entries:
            try:
                first(entry_ids, lambda e: e["masked_name"] == entry["masked_name"])["id"]
            except IndexError:
                masked_name = entry["masked_name"]
                print(f"{masked_name} is not included in the contest results, skipping", file=sys.stderr)
                entries = list(filter(lambda entry: entry["masked_name"] != masked_name, entries))

        judges = []
        for row in read_csv("judges.csv"):
            judge_id = int(row["id"])
            username = row["username"]
            scores_by_judge = []
            scores_by_judge = [
                sum(
                    sum(score["value"] for score in where(scores, lambda score: score["contest_judge_vote_id"] == vote["id"]))
                    for vote in votes
                    if vote["user_id"] == judge_id
                    and vote["contest_entry_id"] == first(entry_ids, lambda e: e["masked_name"] == entry["masked_name"])["id"]
                )
                for entry in entries
            ]

            average = mean(scores_by_judge)
            standard_deviation = sqrt(sum((score - average) ** 2 for score in scores_by_judge) / len(scores_by_judge))

            if not scores_by_judge:
                print(f"couldn't find any judge scores by {username} ({judge_id})", file=sys.stderr)
                exit_code = 1

            if standard_deviation == 0:
                print(f"{username}'s ({judge_id}) standard deviation is 0", file=sys.stderr)
                print({scores_by_judge}, file=sys.stderr)
                exit_code = 1

            judges.append({
                "id": judge_id,
                "username": username,
                "scores": scores_by_judge,
                "average": average,
                "standard_deviation": standard_deviation,
            })

        if exit_code > 0:
            return exit_code

        for entry in entries:
            entry["contest_entry_id"] = first(entry_ids, lambda e: e["masked_name"] == entry["masked_name"])["id"]
            entry["votes"] = where(votes, lambda vote: vote["contest_entry_id"] == entry["contest_entry_id"])
            for vote_idx, vote in enumerate(entry["votes"]):
                vote_scores = where(scores, lambda score: score["contest_judge_vote_id"] == vote["id"])
                for score_idx, score in enumerate(vote_scores):
                    vote_scores[score_idx]["contest_scoring_category_name"] = category_by_id[score["contest_scoring_category_id"]]["name"]
                entry["votes"][vote_idx]["scores"] = vote_scores
                entry["votes"][vote_idx]["score_sum"] = sum(score["value"] for score in vote_scores)
                entry["votes"][vote_idx]["username"] = first(judges, lambda judge: judge["id"] == entry["votes"][vote_idx]["user_id"])["username"]

            entry["total_score"] = sum([vote["score_sum"] for vote in entry["votes"]])
            entry["average_score"] = entry["total_score"] / len(judges)

            for judge in judges:
                raw_score = sum(vote["score_sum"] for vote in entry["votes"] if vote["user_id"] == judge["id"])

                entry[f"standardised_score ({judge["username"]})"] = (raw_score - judge["average"]) / judge["standard_deviation"]

                try:
                    comment = first(entry["votes"], lambda vote: vote["user_id"] == judge["id"])["comment"]
                except IndexError:
                    comment = ""

                entry[f"comment ({judge["username"]})"] = comment

                for category in judging_categories:
                    try:
                        score = first(first(entry["votes"], lambda vote: vote["user_id"] == judge["id"])["scores"], lambda score: score["contest_scoring_category_name"] == category["name"])["value"]
                    except IndexError:
                        print(f"{judge["username"]} didn't set {category["name"]} score on {entry["masked_name"]}", file=sys.stderr)
                        score = None
                    entry[f"{category["name"]} ({judge["username"]})"] = score

            entry["standardised_score"] = sum(entry[f"standardised_score ({judge["username"]})"] for judge in judges)
            print(f"{entry["masked_name"]}: {entry["standardised_score"]:.2f}")

            for category in judging_categories:
                entry[f"{category["name"]}"] = sum([
                    sum(score["value"] for score in vote["scores"] if score["contest_scoring_category_id"] == category["id"])
                    for vote in entry["votes"]
                ])

        entries = sorted(entries, key=lambda entry: entry["standardised_score"], reverse=True)

        with open(f"results{category_suffix}.json", "w", encoding="utf-8") as file:
            file.write(json.dumps(entries))

        with open(f"results{category_suffix}.csv", "w", encoding="utf-8") as file:
            fieldnames = list(entries[0].keys())
            fieldnames.remove("votes")
            try:
                fieldnames.remove("sql")
            except ValueError:
                pass
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in entries:
                writer.writerow(row)

        with open(f"results{category_suffix}.md", "w", encoding="utf-8") as file:
            print("| # | Score | User | Beatmap |", file=file)
            print("| :-: | --: | :-: | :-- |", file=file)
            rank = 0
            previous_standardised_score = None
            for entry in entries:
                if previous_standardised_score != entry["standardised_score"]:
                    rank += 1
                print(f"| {rank} | {entry["standardised_score"]:.2f} | {sanitise(entry["creator"])} | [{sanitise(entry["artist"])} - {sanitise(entry["title"])}](LINK) |", file=file)
                previous_standardised_score = entry["standardised_score"]

    return exit_code


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
