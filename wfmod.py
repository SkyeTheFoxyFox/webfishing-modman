#!/usr/bin/python3

from sys import argv, exit
from inspect import signature
import urllib.request, json, re, pathlib, zipfile, io, shutil, os, zlib, base64

MOD_LOADER_NAME = "NotNet-GDWeave"
DATA_FILE_PATH = pathlib.Path.home() / ".wfmod"

USER_AGENT = "SkyeTheFoxyFox webfishing_mod_manager/1.0"

MOD_LIST_URL = "https://thunderstore.io/c/webfishing/api/v1/package/"
MOD_LIST_REQUEST = urllib.request.Request(MOD_LIST_URL, headers={"User-Agent": USER_AGENT})

HELP_MESSAGE = f"""
Syntax:
    {pathlib.Path(argv[0]).name} <command> [arguments]

Available commands:

    help
        Shows this help text

    list [options]
        Shows a list of mods filtered based on the supplied filters

        -m <regex>
            Filters the output with regex

        -c <category>
            Filters for mods with a specific category

        -n [only]
            Allows nsfw results to show, if 'only' is supplied it won't show sfw results

        -d
            Allows depricated mods to show

    info <mod>
        Shows some info about a mod

    installed
        Shows all your installed mods

    install <mod> [<mod> ...] -i
        Installs supplied mods

        -i
            Won't install dependencies 

    uninstall <mod> [<mod> ...]
        Uninstalls supplied mods

    update
        Attempts to update all your mods

    export
        Exports current mod list to a string

    load
        Reads an exported string and tries to make your mod list match it

"""

class Main():
    def __init__(self):
        prompt_for_path()
        try_install_mod_loader()

        if len(argv) <= 1:
            Main.help()
        else:
            command = argv[1]
            args = argv[2:]
            pos_args = []
            named_args = {}
            itr = enumerate(args)
            for index, arg in itr:
                if arg[0] == '-' and len(arg) > 1:
                    if arg[1:] not in named_args:
                        named_args[arg[1:]] = [] 
                    if(len(args) < index + 2 or args[index+1][0] == '-'):
                        named_args[arg[1:]].append("true")
                    else:
                        named_args[arg[1:]].append(args[index+1])
                        next(itr)
                else:
                    pos_args.append(arg)
            if(command[0] != "_"):
                try:
                    getattr(Main, command)(*pos_args, **named_args)
                except AttributeError as e:
                    print(e)
                    print(f"Unknown command '{command}'")
                    exit(2)
                except TypeError as e:
                    print(e)
                    print(f"Invalid arguments")
                    exit(2)
            else:
                print(f"Unknown command '{command}'")
                exit(2)

    def help():
        print(HELP_MESSAGE)

    def list(*, c=[],n=[],m=[],d=[]):
        mods = get_mods()
        for mod in mods:
            should_show = True
            for cat in c:
                if not cat in mod["categories"]:
                    should_show = False
                    break
            if len(n) == 0 or n[0] == "false":
                if mod["has_nsfw_content"] == True:
                    should_show = False
            elif (n[0] == "only") and (mod["has_nsfw_content"] == False):
                should_show = False

            for reg in m:
                if not re.search(reg, mod["full_name"], re.I):
                    should_show = False
                    break

            if len(d) == 0 and mod["is_deprecated"]:
                should_show = False

            if should_show:
                print(mod["full_name"])

    def installed():
        installed_mods = get_installed_mods()
        for key, value in installed_mods.items():
            print(f"{key}-{value['version']}")

    def info(mod_name):
        try:
            mod = get_mod(mod_name)
        except UnknownModError:
            exit(2)
        print(f"Name: {mod['name']}")
        print(f"Author: {mod['owner']}")
        print(f"Description: {mod['latest']['description']}")
        if(len(mod['community_listings'][0]['categories']) > 0):
            print(f"Categories: [\n    {'\n    '.join(mod['community_listings'][0]['categories'])}\n]")
        if(len(mod['latest']["dependencies"]) > 0):
            print(f"Dependencies: [\n    {'\n    '.join(mod['latest']['dependencies'])}\n]")

    def install(*mods, i=[]):
        for mod_name in mods:
            try:
                mod_data = get_mod(mod_name)
            except UnknownModError:
                continue
            installed_mods = get_installed_mods()

            if mod_name not in installed_mods or compare_versions(mod_data["latest"]["version_number"], installed_mods[mod_name]["version"]):
                if mod_name not in installed_mods:
                    print(f"Downloading {mod_data['latest']['full_name']}")
                else:
                    print(f"Updating {mod_name} {installed_mods[mod_name]['version']} > {mod_data['latest']['version_number']}")

                installed_mods[mod_name] = {}
                installed_mods[mod_name]["version"] = mod_data["latest"]["version_number"]

                mod_url = mod_data["latest"]["download_url"]
                request = urllib.request.Request(mod_url, headers={"User-Agent": USER_AGENT})
                zipped_mod = urllib.request.urlopen(request).read()
                zipped_mod = zipfile.ZipFile(io.BytesIO(zipped_mod), "r")
                has_subdir = True
                for f in zipped_mod.namelist():
                    if re.match("^GDWeave/mods/[^/]+$", f):
                        has_subdir = False

                if has_subdir:
                    for f in zipped_mod.namelist():
                        if re.match("^GDWeave/mods/.", f):
                            if "dir" not in installed_mods[mod_name]:
                                installed_mods[mod_name]["dir"] = f
                            zipped_mod.extract(f, get_game_path())
                else:
                    mod_path = get_game_path()/"GDWeave"/"mods"/mod_name
                    installed_mods[mod_name]["dir"] = str(mod_path)
                    try:
                        os.makedirs(mod_path)
                    except:
                        pass
                    for f in zipped_mod.namelist():
                        if re.match("^GDWeave/mods/.", f):
                            with open(mod_path / re.sub("^GDWeave/mods/", "", f), 'wb') as file:
                                file.write(zipped_mod.read(f))

                write_installed_mods(installed_mods)

                if len(i) == 0:
                    for dep in mod_data["latest"]["dependencies"]:
                        if not dep.startswith(MOD_LOADER_NAME):
                            dep = dep.split('-')
                            Main.install(f"{dep[0]}-{dep[1]}")

            else:
                print(f"{mod_name} is up to date")

    def uninstall(*mods):
        for mod_name in mods:
            installed_mods = get_installed_mods()
            if mod_name not in installed_mods:
                print(f"Unknown mod {mod_name}")
                continue
            try:
                shutil.rmtree(str(get_game_path() / installed_mods[mod_name]["dir"]))
            except:
                pass
            installed_mods.pop(mod_name)
            write_installed_mods(installed_mods)
            print(f"Uninstalled {mod_name}")

    def update():
        print("Updating mods")
        updated = False
        for mod, data in get_installed_mods().items():
            new_mod = get_mod(mod)
            if compare_versions(new_mod["latest"]["version_number"], data["version"]):
                Main.install(mod, i=["true"])
                updated = True
        if updated == False:
            print("All mods up to date")

    def export():
        installed_mods = get_installed_mods()
        mods = list(installed_mods.keys())
        mods = ";".join(mods)
        mods = b"wfmod"+zlib.compress(bytes(mods, "utf8"), level=9)
        mods = base64.standard_b64encode(mods).decode()
        print(mods)

    def load(b64_string):
        mods = base64.standard_b64decode(bytes(b64_string, "utf8"))
        if mods[:5] != b"wfmod":
            print("Invalid input")
            exit(2)
        mods = zlib.decompress(mods[5:]).decode()
        mods = mods.split(";")

        for mod in mods:
            Main.install(mod, i=["true"])

        for mod in get_installed_mods().keys():
            if mod not in mods:
                Main.uninstall(mod)

class UnknownModError(Exception):
    pass

def get_mods(): 
    mods = json.loads(urllib.request.urlopen(MOD_LIST_REQUEST).read())
    return mods

def get_mod(name):
    try:
        owner, mod = name.split("-")
        url = f"https://thunderstore.io/api/experimental/package/{owner}/{mod}/"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        return json.loads(urllib.request.urlopen(request).read())
    except:
        print(f"Unknown mod '{name}'")
        raise UnknownModError()

def get_installed_mods():
    path = get_game_path() / "installed_mods"
    if not path.exists():
        with open(path, "w") as f:
            f.write("{}")
    with open(path, "r") as f:
        return json.loads(f.read())

def write_installed_mods(mods):
    path = get_game_path() / "installed_mods"
    if not path.exists():
        with open(path, "w") as f:
            f.write("[]")
    with open(path, "w") as f:
        return f.write(json.dumps(mods))

def get_game_path():
    try:
        with open(DATA_FILE_PATH, "r") as file:
            return pathlib.Path(file.read())
    except FileNotFoundError:
        return ""

def set_game_path(path):
    with open(DATA_FILE_PATH, "w") as file:
        file.write(str(path))

def prompt_for_path():
    if get_game_path() == "":
        p = None
        while True:
            p = pathlib.Path(input("Please input the path to the game files:\n"))
            if p.exists() and p.is_dir() and (p / "webfishing.exe").exists():
                break
        set_game_path(str(p))
        
def try_install_mod_loader():
    if not (get_game_path() / "winmm.dll").exists():
        print("Downloading mod loader")
        loader_url = get_mod(MOD_LOADER_NAME)["latest"]["download_url"]
        request = urllib.request.Request(loader_url, headers={"User-Agent": USER_AGENT})
        zipped_loader = urllib.request.urlopen(request).read()
        print("Installing")
        zipped_loader = zipfile.ZipFile(io.BytesIO(zipped_loader), "r")
        zipped_loader.extract("winmm.dll", get_game_path())
        for f in zipped_loader.namelist():
            if f.startswith("GDWeave/"):
                zipped_loader.extract(f, get_game_path())
        print("Finished")

def compare_versions(ver1, ver2):
    version1 = ver1.split('.')
    version2 = ver2.split('.')
    for i in range(3):
        if version1[i] > version2[i]:
            return True
    return False

Main()
