from pathlib import Path


def repo_root():
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AxiaDriver").is_dir() and (parent / "pixi.toml").exists():
            return parent
    return Path.cwd()


def default_sensor_yaml():
    return str(repo_root() / "Axia_Joe_Config.yaml")
