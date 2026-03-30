# /// script
# requires-python = ">=3.14"
# ///

"""
You'll need FFmpeg (https://ffmpeg.org/) installed and available in $PATH

Provide a "contest-###.zip" archive (ask an admin for a contest page export)
and put it into the same folder as this script.

The archive should contain folders named "{user} ({user_id})", each containing
the submission .osz file.

If you extract the archive yourself, the extracted "contest-###" folder will
be used instead (allowing you to filter submissions).

For team contests, provide a "team.json" file with the following structure:

[
  { "team_name": "Team 1", "mappers": [{"name": "peppy", "id": 2}]},
  ...
]

If specific entries need specific tags, add a "tags.csv" file with the
following columns:

- creator_id (the submitter)
- tags (the tags to set)

Otherwise, use the --tags argument to apply one set of tags to every entry

Use the --help argument to see all options
"""


import argparse
import itertools
import json
import os
import random
import re
import shutil
import subprocess as sp
import sys
import csv
from urllib.parse import quote
from textwrap import indent
from zipfile import ZipFile

EMOTIONS = ["accepting", "accommodating", "afraid", "aggressive", "agitated", "alarmed", "amazed", "amused", "antagonistic", "anxious", "apathetic", "apprehensive", "arrogant", "astonished", "astounded", "attentive", "blase", "bold", "bothered", "brave", "calm", "capable", "casual", "charming", "cheerful", "cheery", "churlish", "collected", "comfortable", "competitive", "composed", "compulsive", "concerned", "confident", "conflicted", "conscientious", "conservative", "considerate", "conspicuous", "contemptible", "content", "convivial", "cool", "courageous", "covetous", "creative", "critical", "curious", "cynical", "dazzled", "debilitated", "defensive", "dejected", "delighted", "demeaned", "depressed", "destructive", "devious", "devoted", "dictatorial", "diffident", "disdainful", "distracted", "distraught", "distressed", "downcast", "earnest", "edgy", "elated", "empathetic", "enthusiastic", "euphoric", "exhausted", "expectant", "explosive", "exuberant", "ferocious", "fierce", "flabbergasted", "flexible", "focused", "forgiving", "forlorn", "frightened", "furtive", "gloomy", "good", "grateful", "grouchy", "guilty", "happy", "harassed", "heroic", "hesitant", "hopeful", "hostile", "humble", "humorous", "hysterical", "idealistic", "ignorant", "ill-tempered", "impartial", "impolite", "imprudent", "indifferent", "infuriated", "insightful", "insulted", "intense", "intimidated", "intolerant", "irascible", "jealous", "jolly", "jovial", "joyful", "jubilant", "jumpy", "kind", "languid", "liberal", "loving", "loyal", "magical", "magnificent", "malevolent", "malicious", "mysterious", "needy", "negative", "neglected", "nervy", "opinionated", "panicky", "passionate", "patient", "perturbed", "petrified", "petulant", "placid", "pleased", "powerful", "prejudicial", "prideful", "quarrelsome", "queasy", "quivering", "rancorous", "rational", "reasonable", "reckless", "reflective", "remorseful", "repugnant", "resilient", "resolute", "resourceful", "respectful", "responsible", "responsive", "restorative", "reverent", "rude", "ruthless", "sad", "safe", "scared", "scornful", "seething", "selfish", "sensible", "sensitive", "serene", "shaky", "shivering", "shocked", "sickly", "simple", "sober", "solemn", "somber", "sour", "speechless", "spooked", "stern", "successful", "sullen", "superior", "supportive", "surly", "suspicious", "sweet", "sympathetic", "tactful", "tenacious", "tense", "terrific", "testy", "thoughtful", "thoughtless", "timorous", "tolerant", "tranquil", "treacherous", "trembling", "truthful", "ultimate", "uncivil", "uncouth", "uneasy", "unethical", "unfair", "unique", "unmannerly", "unnerved", "unrefined", "unruffled", "unsavory", "unworthy", "uplifting", "upset", "uptight", "versatile", "vicious", "vigilant", "vigorous", "vile", "villainous", "virtuous", "vivacious", "volatile", "vulnerable", "warm", "wary", "waspish", "weak", "welcoming", "wicked", "wild", "wise", "wishy-washy", "wistful", "witty", "woeful", "wonderful", "worrying", "worthy", "youthful", "zany", "zealous",]

BIRDS = ["Hawk", "Eagle", "Harrier", "Kite", "Osprey", "Lark", "Kingfisher", "Duck", "Mallard", "Wigeon", "Teal", "Pintail", "Goose", "Bufflehead", "Merganser", "Swift", "Heron", "Waxwing", "Nighthawk", "Vulture", "Creeper", "Dove", "Crow", "Jay", "Magpie", "Cuckoo", "Blackbird", "Sparrow", "Bunting", "Warbler", "Bobolink", "Oriole", "Finch", "Loon", "Crane", "Catbird", "Thrasher", "Thrush", "Gnatcatcher", "Kinglet", "Bluebird", "Robin", "Chickadee", "Pelican", "Cormorant", "Pheasant", "Woodpecker", "Sapsucker", "Coot", "Sandpiper", "Willet", "Snipe", "Owl", "Starling", "Ibis", "Hummingbird", "Wren", "Wood-pewee", "Flycatcher", "Phoebe", "Vireo",]

LIZARDS = ["Gecko", "Chameleon", "Iguana", "Anole", "Dragon", "Monitor", "Tegu", "Skink",]

MAMMALS = ["Shrew", "Bat", "Jackrabbit", "Beaver", "Rat", "Muskrat", "Mouse", "Porcupine", "Gopher", "Dog", "Squirrel", "Coyote", "Fox", "Bobcat", "Tiger", "Lion", "Skunk", "Weasel", "Badger", "Raccoon", "Chipmunk", "Monkey", "Gorilla", "Lemur", "Emu", "Kangaroo", "Elephant", "Opossum", "Armadillo", "Prairie Dog", "Marmot", "Vole", "Whale", "Shrew", "Bear", "Stoat", "Sea Lion", "Walrus", "Seal", "Elk", "Pronghorn", "Bison", "Sheep", "Manatee", "Dolphin", "Unicorn", "Zebra", "Cheetah",]

REPTILES = ["Alligator", "Tortoise", "Turtle", "Crocodile", "Rattlesnake", "Cottonmouth", "Viper",]


GAME_MODES = {
    "osu": 0,
    "taiko": 1,
    "catch": 2,
    "mania": 3,
}


def read_file(file):
    with open(file, "r", encoding="utf-8") as file:
        return file.read()


def list_all_files(path):
    for root, _, filenames in os.walk(path):
        for f in filenames:
            filepath = os.path.join(root, f).replace("\\", "/")
            yield filepath


def s(count, string):
    # returns `string` pluralised (by appending "s") depending on `count`
    return f"{count} {string}{'s' if count != 1 else ''}"


def quote_if_spaces(s):
    return f"\"{s}\"" if " " in s else s


def unquote(s):
    return s[1:-1] if s[0] == '"' and s[-1] == '"' else s


def sanitise_file_name(s, replacement=" "):
    return (s.replace("<", replacement)
            .replace(">", replacement)
            .replace(":", replacement)
            .replace("\"", replacement)
            .replace("/", replacement)
            .replace("\\", replacement)
            .replace("*", replacement)
            .replace("?", replacement))



def extract_archive(src, dst):
    # Extracts a zip archive while sanitising any problematic file names
    with ZipFile(src) as zipdata:
        zipinfos = zipdata.infolist()

        for zipinfo in zipinfos:
            zipinfo.filename = sanitise_file_name(zipinfo.filename)
            zipdata.extract(zipinfo, path=dst)


def trash(submission, name):
    try:
        os.mkdir("./bad")
    except FileExistsError:
        pass

    ext = submission.split(".")[-1]
    shutil.copy(submission, f"./bad/{name}.{ext}")


def cmd(*cmd, expected_code=0, ignore_error=False):
    proc = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    try:
        out, err = proc.communicate(timeout=10)
    except Exception as e:
        if ignore_error:
            out, err = ("", "")
        else:
            raise e
    out = out.decode("utf-8", 'replace') if out else ""
    err = err.decode("utf-8", 'replace') if err else ""
    if proc.returncode != expected_code and not ignore_error:
        raise RuntimeError(
            "{} failed:\n"
            "- exit code: {}\n"
            "- stdout: {}\n"
            "- stderr: {}\n".format(
                cmd, proc.returncode, out, err
            )
        )
    return out


class NameGenerator():
    def __init__(self):
        self.seen = set()
        self.emotions = EMOTIONS
        self.animals = BIRDS + LIZARDS + MAMMALS + REPTILES
        self.combinations = list(itertools.product(self.emotions, self.animals))
        random.shuffle(self.combinations)

    def next(self):
        # raises IndexError if there are no more possible name combinations
        emotion, name = self.combinations.pop()
        return f"{emotion} {name}".title()


class UniqueRNG():
    def __init__(self, min, max):
        self.sequence = list(range(min, max + 1))
        random.shuffle(self.sequence)

    def next(self):
        # raises IndexError if there are no more values
        return self.sequence.pop()


def parse_args(args):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-n", "--name", action='store', help="contest name, used as a prefix for output .osz files")
    parser.add_argument("-t", "--tags", action='store', default=None, help="tags to set to anonymised entries. if omitted, will try to look for a tags.csv with \"creator_id\" and \"tags\" columns, otherwise tags are cleared")
    parser.add_argument("-b", "--backgrounds", action=argparse.BooleanOptionalAction, help="whether to include backgrounds (no by default)")
    parser.add_argument("-v", "--videos", action=argparse.BooleanOptionalAction, help="whether to include videos (no by default)")
    parser.add_argument("-m", "--mode", choices=list(GAME_MODES.keys()), default="osu", help="the game mode to expect")
    parser.add_argument("--bookmarks", action=argparse.BooleanOptionalAction, help="whether to include bookmarks (no by default)")
    return parser.parse_args(args)


def check_is_taiko(map_file):
    lines = read_file(map_file).split("\n")
    section = ""

    for i, line in enumerate(lines):
        if line.startswith("["):
            section = line[1:line.find("]")]
            continue

        if section == "General":
            if line.startswith("Mode: 1"):
                return True

    return False


lines = []
line_index = 0


def get(setting):
    global lines
    global line_index
    if lines[line_index].startswith(setting + ":"):
        try:
            return ":".join(lines[line_index].rsplit(":")[1:]).strip()
        except:
            pass


def ensure(setting):
    global lines
    global line_index
    split = setting.split(":")
    if len(split) <= 1:
        return False
    if lines[line_index].startswith(f"{split[0]}:"):
        lines[line_index] = setting
        return True
    return False


def check_beatmap(beatmap_folder, creator, game_mode):
    """
    Ensures that beatmap metadata is correct

    - The beatmap creator is the same as the submitter (fixes automatically)
    - All .osu file names are correct (fixes automatically)
    - The game mode is set as expected (errors otherwise)
    - Artist and title fields are set (errors otherwise)
    """

    global lines
    global line_index

    for map_file in os.listdir(beatmap_folder):
        if map_file.endswith(".osu"):
            is_taiko = check_is_taiko(f"{beatmap_folder}/{map_file}")

            lines = read_file(f"{beatmap_folder}/{map_file}").split("\n")
            section = ""
            diff = ""
            artist = None
            title = None
            mode = ""

            for i, line in enumerate(lines):
                line_index = i

                if line.startswith("Version:"):
                    diff = line[len("Version:"):].strip()
                if line.startswith("["):
                    section = line[1:line.find("]")]
                    continue

                elif section == "General":
                    mode = get("Mode") or mode

                elif section == "Metadata":
                    ensure(f"Creator:{creator}")
                    ensure("BeatmapID:0")
                    ensure("BeatmapSetID:-1")
                    artist = get("Artist") or artist
                    title = get("Title") or title

            if not (artist and title):
                raise RuntimeError(f"artist or title is not set ({creator})")

            if mode.strip() != str(game_mode):
                raise RuntimeError(f"game mode is incorrectly set to {mode} ({creator})")

            new_map_file = "\n".join([line.rstrip() for line in lines]) + "\n"
            os.remove(f"{beatmap_folder}/{map_file}")
            file_name = sanitise_file_name(f"{artist} - {title} ({creator}) [{diff}]")
            with open(f"{beatmap_folder}/{file_name}.osu", "w", encoding="utf-8") as file:
                file.write(new_map_file)

    return artist, title


def main(*args):
    global lines
    global line_index

    args = parse_args(args)

    contest_id = None
    paths = os.listdir(".")
    for path in paths:
        match = re.match(r"contest-(\d+)$", path)
        if match:
            contest_id = int(match.group(1))
            contest_dir = path
            break

    if not contest_id:
        for path in paths:
            match = re.match(r"contest-(\d+)\.zip$", path)
            if match:
                contest_id = int(match.group(1))
                contest_dir = path[:-4]
                print("extracting archive")
                shutil.unpack_archive(path, contest_dir, "zip")
                break

    if not contest_id:
        print("put a \"contest-{contest number}.zip\" archive into the same folder as this script")
        sys.exit(1)

    file_paths = list(list_all_files(contest_dir))

    print(f"anonymising {s(len(file_paths), "submission")}")

    output_dirs = [
            "original",
            "unpacked-osz",
            "repacked-osz",
            "output",
            "bad",
    ]
    for dir in output_dirs:
        shutil.rmtree(dir, ignore_errors=True)
    for dir in output_dirs[:-1]:
        os.mkdir(dir)

    info_csv = []

    try:
        teams = json.loads(read_file("./teams.json"))
        print(f"found {s(len(teams), "team")} in \"teams.json\"")
    except Exception:
        print("no \"teams.json\" file found, continuing without")
        teams = None

    previous_masked_names = None
    try:
        with open("spoiler.csv", "r", encoding="utf-8") as file:
            previous_masked_names = {row["creator_id"]: row["masked_name"] for row in csv.DictReader(file)}
            print("found \"spoiler.csv\" from a previous run, using generated anonymous names from that")
    except Exception:
        pass

    tags_csv = None
    if not args.tags:
        try:
            with open("tags.csv", "r", encoding="utf-8") as file:
                tags_csv = {int(row["creator_id"]): row["tags"] for row in csv.DictReader(file)}
                print("found \"tags.csv\", populating tags in anonymised submissions from that")
        except Exception:
            pass

    name_generator = NameGenerator()

    for i, file_path in enumerate(file_paths):
        folder, file_name = file_path.replace("\\", "/").split("/")[-2:]
        match = re.match(r"(.*)/(.*) \((.*)\)/(.*)", file_path.replace("\\", "/"))
        creator = match.group(2)
        creator_id_str = match.group(3)
        creator_id = int(creator_id_str)

        tags = args.tags or ""
        if tags_csv:
            tags = tags_csv.get(creator_id, tags)

        if previous_masked_names is not None and creator_id_str in previous_masked_names:
            masked_name = previous_masked_names[creator_id_str]
        else:
            try:
                masked_name = name_generator.next()
            except IndexError:
                print(f"ran out of possible name combinations ({len(name_generator.combinations)} max)")

        file_name = match.group(4)
        file_ext = file_name.split(".")[-1]
        file_base_name = ".".join(file_name.split(".")[:-1]).strip()
        masked_file_base_name = f"{args.name + ' - ' if args.name else ''}{masked_name}"
        unpacked_dir_name = f"{creator} ({creator_id}) - {file_base_name}"

        print(f"{creator} ({creator_id}) -> {masked_name}")

        if teams is not None:
            try:
                team_name = list(filter(lambda team: any(creator_id == mapper["id"] for mapper in team["mappers"]), teams))[0]["team_name"]
            except IndexError:
                print(f"could not find the team for {creator} ({creator_id})!")
                trash(file_path, unpacked_dir_name)
                continue
        else:
            team_name = ""

        if file_ext != "osz":
            print(f"didn't submit a .osz file ({file_path})")
            trash(file_path, unpacked_dir_name)
            continue

        extract_archive(file_path, f"./unpacked-osz/{unpacked_dir_name}/")

        map_files = os.listdir(f"./unpacked-osz/{unpacked_dir_name}")
        osu_files = [f for f in map_files if f.endswith(".osu")]

        if len(osu_files) != 1:
            if len(osu_files) > 1:
                print(f"multiple .osu files ({file_path}):{indent("\n".join(osu_files), "  ")}")
            elif not osu_files:
                print(f"no .osu files ({file_path})")
            trash(file_path, unpacked_dir_name)
            continue

        try:
            artist, title = check_beatmap(f"./unpacked-osz/{unpacked_dir_name}", creator, GAME_MODES[args.mode])
        except RuntimeError as e:
            print(e)
            trash(file_path, unpacked_dir_name)
            continue

        # map files may have been modified by check_beatmap
        map_files = os.listdir(f"./unpacked-osz/{unpacked_dir_name}")
        osu_files = [f for f in map_files if f.endswith(".osu")]

        unmasked_file_base_name = sanitise_file_name(f"{artist} - {title} ({team_name or creator})")

        # repack original map
        shutil.make_archive(f"./original/{unmasked_file_base_name}", "zip", f"./unpacked-osz/{unpacked_dir_name}")
        shutil.move(f"./original/{unmasked_file_base_name}.zip", f"./original/{unmasked_file_base_name}.osz")

        os.mkdir(f"./repacked-osz/{unpacked_dir_name}")

        rng_sequence = UniqueRNG(1, 727)

        backgrounds = set()

        for map_file in map_files:
            if map_file.endswith(".osu"):
                is_taiko = check_is_taiko(f"./unpacked-osz/{unpacked_dir_name}/{map_file}")

                try:
                    # random number for multiple diffs in file
                    rng = rng_sequence.next()
                except IndexError:
                    print(f"ran out of unique indices for {masked_name}'s diffs (max 727)")

                lines = read_file(f"./unpacked-osz/{unpacked_dir_name}/{map_file}").split("\n")
                if ("v128" in lines[0]):
                    print(f"{creator} - lazer map")
                section = ""
                tags_set = False

                for i, line in enumerate(lines):
                    line_index = i

                    if line.startswith("["):
                        # it's apparently not guaranteed that the field exists
                        # so due to how lines are iterated here, this is the
                        # quick and dumb way to ensure it's inserted
                        if section == "Metadata" and not tags_set:
                            lines[i-2] = lines[i-2] + f"\nTags:{tags}"

                        section = line[1:line.find("]")]
                        continue

                    elif section == "Metadata":
                        ensure("Creator:Anonymous")
                        if len(osu_files) > 1:
                            ensure(f"Version:{masked_name}{rng}")
                        else:
                            ensure(f"Version:{masked_name}")
                        tags_set = ensure(f"Tags:{tags}") or tags_set
                        ensure("Source:")
                        ensure("BeatmapID:0")
                        ensure("BeatmapSetID:-1")

                    elif not args.bookmarks and section == "Editor":
                        ensure("Bookmarks:")

                    elif section == "Events" and (line.startswith("Background,") or line.startswith("0,")):
                        if args.backgrounds:
                            split = line.split(",")
                            background_name = unquote(split[2])
                            backgrounds.add(background_name)
                            ext = background_name.split(".")[-1]
                            split[2] = f"background.{ext}"
                            lines[i] = ",".join(split)
                        else:
                            lines[i] = None

                    elif section == "Events" and (line.startswith("Video,") or line.startswith("1,")):
                        if args.videos:
                            split = line.split(",")
                            video_name = unquote(split[2])
                            ext = video_name.split(".")[-1]
                            split[2] = f"video.{ext}"
                            lines[i] = ",".join(split)
                        else:
                            lines[i] = None

                    elif section == "Events" and (
                            line.startswith("Sprite,") or line.startswith("4,") or
                            line.startswith("Sample,") or line.startswith("5,") or
                            line.startswith("Animation,") or line.startswith("6,") or
                            line.startswith(" ") or line.startswith("_")
                            ):
                        lines[i] = None

                    if is_taiko:
                        if section == "HitObjects":
                            split = line.split(",")
                            if len(split) <= 1:
                                continue
                            split[0] = "256"
                            split[0] = "192"
                            lines[i] = ",".join(split)

                        elif section == "Difficulty":
                            ensure("CircleSize:5")
                            ensure("ApproachRate:9")
                        elif section == "General":
                            ensure("StackLeniency: 0.7")

                new_map_file = "\n".join([line.rstrip() for line in lines if line is not None]) + "\n"
                full_title_sanitised = sanitise_file_name(f"{artist} - {title}")
                with open(f"./repacked-osz/{unpacked_dir_name}/{full_title_sanitised} (Anonymous) [{masked_name}].osu", "w", encoding="utf-8") as file:
                    file.write(new_map_file)

        for map_file in map_files:
            if args.backgrounds and map_file in backgrounds:
                ext = map_file.split(".")[-1]
                cmd(  # strip away any metadata
                    "ffmpeg",
                    "-i", f"./unpacked-osz/{unpacked_dir_name}/{map_file}",
                    "-map_metadata", "-1",
                    "-c:v", "copy",
                    f"./repacked-osz/{unpacked_dir_name}/background.{ext}"
                )

            elif any(map_file.lower().endswith(ext) for ext in [".mp3", ".ogg", ".wav"]):
                ext = map_file.split(".")[-1]
                shutil.copy(f"./unpacked-osz/{unpacked_dir_name}/{map_file}", f"./repacked-osz/{unpacked_dir_name}/{map_file}")
                #cmd(  # strip away any metadata (TODO: the following can break hitsounds for stable)
                #    "ffmpeg",
                #    "-i", f"./unpacked-osz/{unpacked_dir_name}/{map_file}",
                #    "-map_metadata", "-1",
                #    "-c:a", "copy",
                #    f"./repacked-osz/{unpacked_dir_name}/{map_file}"
                #)

        shutil.make_archive(f"./output/{masked_file_base_name}", "zip", f"./repacked-osz/{unpacked_dir_name}")
        shutil.move(f"./output/{masked_file_base_name}.zip", f"./output/{masked_file_base_name}.osz")

        entry_name = f"{artist} - {title} by team {team_name}" if team_name else f"{artist} - {title}"
        sql = f"INSERT INTO contest_entries (name, masked_name, entry_url, user_id, contest_id, created_at, updated_at) VALUES ('{entry_name}', '{masked_name}', '', '{creator_id}', '{contest_id}', NOW(), NOW());"

        info_entry = {
            "creator": creator,
            "creator_id": creator_id,
            "artist": artist,
            "title": title,
            "masked_name": masked_name,
            "sql": sql,
        }

        if teams is not None:
            info_entry["team_name"] = team_name

        info_csv.append(info_entry)

    with open("spoiler.csv", "w", encoding="utf-8", newline="") as file:
        fieldnames = "team_name creator creator_id artist title masked_name sql".split(" ")
        if teams is None:
            fieldnames.pop(0)
        writer = csv.DictWriter(file, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL, fieldnames=fieldnames)
        writer.writeheader()
        for row in info_csv:
            writer.writerow(row)

    shutil.make_archive("./anonymised", "zip", "./output")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
