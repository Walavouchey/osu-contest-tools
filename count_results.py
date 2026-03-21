# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "ossapi>=5.3.3",
# ]
# ///
#
# you'll need an osu! api client with OSU_API_CLIENT and OSU_API_SECRET
# environment variables set
#
# you'll also need an info.csv with at least a "masked_name" column. as a
# contest host you should've received this file when results were anonymised
#
# (ask someone with pink role to) run `!export-contest-results <id>` and save
# the resulting 4 json files into a `results` folder beside this script:
#
# - info.csv
# - results
#   - judge_votes.json
#   - judge_scores.json
#   - entries.json
#   - categories.json
#
# run this script with `uv run count_results.py` if you have uv installed.
# otherwise, manually install the dependency first before running:
#
# ```sh
# pip install ossapi
# ```
#
# outputs 3 files
# - results.json  # stats ordered by standardised scoring
# - results.csv  # same thing except without the nested "votes" column
# - results.md  # markdown table for the wiki


import csv
import json
import re
import sys
import os
from statistics import mean
from math import sqrt

from ossapi import Ossapi

client_id = os.getenv("OSU_CLIENT_ID")
client_secret = os.getenv("OSU_CLIENT_SECRET")

if not client_id:
    print("client id missing, set the OSU_CLIENT_ID env var")
if not client_secret:
    print("client secret missing, set the OSU_CLIENT_SECRET env var")
if not client_id or not client_secret:
    sys.exit(1)

RESULTS_FOLDER = "results"


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


def main(*args):
    votes = read_json(f"{RESULTS_FOLDER}/judge_votes.json")
    scores = read_json(f"{RESULTS_FOLDER}/judge_scores.json")
    entry_ids = read_json(f"{RESULTS_FOLDER}/entries.json")
    entries_full = read_csv("spoiler.csv")
    judging_categories = read_json(f"{RESULTS_FOLDER}/categories.json")

    category_by_id = {e["id"]: {"name": e["name"], "max_value": e["max_value"]} for e in judging_categories}
    judge_ids = set(e["user_id"] for e in votes)

    api = Ossapi(client_id, client_secret)

    judges = []
    for judge_id in judge_ids:
        username = api.user(judge_id).username
        scores_by_judge = [
            sum(
                sum(score["value"] for score in where(scores, lambda score: score["contest_judge_vote_id"] == vote["id"]))
                for vote in votes
                if vote["user_id"] == judge_id
                and vote["contest_entry_id"] == first(entry_ids, lambda e: e["masked_name"] == entry["masked_name"])["id"]
            )
            for entry in entries_full
        ]
        average = mean(scores_by_judge)
        standard_deviation = sqrt(sum((score - average) ** 2 for score in scores_by_judge) / len(scores_by_judge))
        judges.append({
            "id": judge_id,
            "username": username,
            "scores": scores_by_judge,
            "average": average,
            "standard_deviation": standard_deviation,
        })

    for entry in entries_full:
        entry["contest_entry_id"] = first(entry_ids, lambda e: e["masked_name"] == entry["masked_name"])["id"]
        entry["votes"] = where(votes, lambda vote: vote["contest_entry_id"] == entry["contest_entry_id"])
        for vote_idx, vote in enumerate(entry["votes"]):
            vote_scores = where(scores, lambda score: score["contest_judge_vote_id"] == vote["id"])
            for score_idx, score in enumerate(vote_scores):
                vote_scores[score_idx]["contest_scoring_category_name"] = category_by_id[score["contest_scoring_category_id"]]["name"]
            entry["votes"][vote_idx]["scores"] = vote_scores
            entry["votes"][vote_idx]["score_sum"] = sum(score["value"] for score in vote_scores)

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

        for category in judging_categories:
            entry[f"{category["name"]}"] = sum([
                sum(score["value"] for score in vote["scores"] if score["contest_scoring_category_id"] == category["id"])
                for vote in entry["votes"]
            ])

    entries_full = sorted(entries_full, key=lambda entry: entry["standardised_score"], reverse=True)

    with open("results.json", "w", encoding="utf-8") as file:
        file.write(json.dumps(entries_full))

    with open("results.csv", "w", encoding="utf-8") as file:
        fieldnames = list(entries_full[0].keys())
        fieldnames.remove("votes")
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in entries_full:
            writer.writerow(row)

    with open("results.md", "w", encoding="utf-8") as file:
        print("| # | Score | User | Beatmap |", file=file)
        print("| :-: | --: | :-: | :-- |", file=file)
        rank = 0
        previous_standardised_score = None
        for entry in entries_full:
            if previous_standardised_score != entry["standardised_score"]:
                rank += 1
            print(f"| {rank} | {entry["standardised_score"]:.2f} | {sanitise(entry["creator"])} | [{sanitise(entry["artist"])} - {sanitise(entry["title"])}](LINK) |", file=file)
            previous_standardised_score = entry["standardised_score"]


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
