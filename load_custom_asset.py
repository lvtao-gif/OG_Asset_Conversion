import argparse
import os
from pathlib import Path

import omnigibson as og
from omnigibson.objects import USDObject
from omnigibson.scenes import Scene


DEFAULT_ASSET_DIR = "/Users/a54197/Documents/vcis文档/智源学者/cola_can_obj"
PREFERRED_USD_NAMES = ("cola_can.usd", "asset.usd")


def pick_usd_from_dir(asset_dir: Path) -> Path:
    usd_files = sorted(asset_dir.rglob("*.usd"))
    if not usd_files:
        raise FileNotFoundError(f"No .usd found under asset dir: {asset_dir}")

    lower_to_path = {p.name.lower(): p for p in usd_files}
    for name in PREFERRED_USD_NAMES:
        if name in lower_to_path:
            return lower_to_path[name]

    if len(usd_files) == 1:
        return usd_files[0]

    candidates = "\n".join(f"  - {p}" for p in usd_files[:50])
    raise RuntimeError(
        "Multiple .usd files found under asset dir. "
        "Please pass --usd-path explicitly.\n"
        f"{candidates}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load a custom OmniGibson asset from a folder or explicit USD path."
    )
    parser.add_argument(
        "--asset-dir",
        default=DEFAULT_ASSET_DIR,
        help="Asset folder containing the .usd file and optional textures/ dependencies.",
    )
    parser.add_argument(
        "--usd-path",
        default=None,
        help="Absolute path to a .usd file. If set, it overrides --asset-dir.",
    )
    parser.add_argument("--headless", action="store_true", help="Run without GUI.")
    parser.add_argument(
        "--steps",
        type=int,
        default=120,
        help="Simulation steps to run after loading.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=0.01,
        help="Uniform scale for the test object.",
    )
    parser.add_argument(
        "--name",
        default="cola_can_test",
        help="Object name registered inside the scene.",
    )
    parser.add_argument(
        "--z",
        type=float,
        default=1.0,
        help="Spawn height above the floor.",
    )
    return parser.parse_args()


def build_search_path(asset_dir: Path, usd_path: Path) -> str:
    candidates = [
        usd_path.parent,
        usd_path.parent / "textures",
        asset_dir,
        asset_dir / "textures",
    ]
    existing = os.environ.get("PXR_AR_DEFAULT_SEARCH_PATH", "")
    values = [str(path) for path in candidates if path.exists()]
    if existing:
        values.append(existing)
    return os.pathsep.join(values)


def main():
    args = parse_args()

    asset_dir = Path(args.asset_dir).expanduser().resolve()
    usd_path = (
        Path(args.usd_path).expanduser().resolve()
        if args.usd_path
        else pick_usd_from_dir(asset_dir)
    )

    if not usd_path.is_file():
        raise FileNotFoundError(f"USD file not found: {usd_path}")
    if usd_path.suffix.lower() != ".usd":
        raise ValueError(f"Expected a .usd file, got: {usd_path}")

    os.environ["OMNIGIBSON_HEADLESS"] = "1" if args.headless else "0"
    os.environ["PXR_AR_DEFAULT_SEARCH_PATH"] = build_search_path(asset_dir, usd_path)

    print("asset_dir:", asset_dir)
    print("loaded_usd:", usd_path)
    print("headless:", args.headless)
    print("scale:", args.scale)
    print("pxr_search_path:", os.environ["PXR_AR_DEFAULT_SEARCH_PATH"])

    og.launch()
    try:
        scene = Scene(use_floor_plane=True)
        og.sim.import_scene(scene)

        obj = USDObject(
            name=args.name,
            usd_path=str(usd_path),
            category="custom",
            fixed_base=False,
            scale=args.scale,
        )
        scene.add_object(obj)

        obj.set_position_orientation(
            position=[0, 0, args.z],
            orientation=[0, 0, 0, 1],
        )

        for _ in range(args.steps):
            og.sim.step()

        pos, quat = obj.get_position_orientation()
        registry_obj = scene.object_registry("name", args.name)

        print("load_success:", registry_obj is not None)
        print("final_position:", pos)
        print("final_orientation:", quat)

        if hasattr(obj, "get_base_aligned_bbox"):
            try:
                print("bbox:", obj.get_base_aligned_bbox())
            except Exception as exc:
                print("bbox_error:", exc)
    finally:
        og.shutdown()


if __name__ == "__main__":
    main()
