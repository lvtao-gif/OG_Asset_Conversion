import argparse
from pathlib import Path

from pxr import Sdf, Usd, UsdGeom, UsdPhysics


def parse_args():
    parser = argparse.ArgumentParser(
        description="Wrap a generic USD into an OmniGibson-compatible object/link/visuals/collisions hierarchy."
    )
    parser.add_argument("--input-usd", required=True, help="Source USD / USDA file.")
    parser.add_argument("--output-usd", required=True, help="Output wrapped USD / USDA file.")
    parser.add_argument(
        "--asset-name",
        default=None,
        help="Root object prim name. Defaults to the input file stem.",
    )
    parser.add_argument(
        "--link-name",
        default="root_link",
        help="Single OG link name attached under the object root.",
    )
    parser.add_argument(
        "--collision-approximation",
        default="convexHull",
        help="UsdPhysics mesh collision approximation, e.g. convexHull / convexDecomposition / none.",
    )
    return parser.parse_args()


def get_source_root(stage: Usd.Stage):
    default_prim = stage.GetDefaultPrim()
    if default_prim and default_prim.IsValid():
        return default_prim

    children = [prim for prim in stage.GetPseudoRoot().GetChildren() if prim.IsActive()]
    if len(children) == 1:
        return children[0]

    raise RuntimeError("Source USD has no default prim and no unique top-level prim.")


def get_geom_relative_paths(root_prim):
    root_path = root_prim.GetPath()
    relative_paths = []
    for prim in Usd.PrimRange(root_prim):
        if prim == root_prim:
            continue
        if prim.IsA(UsdGeom.Gprim):
            relative_paths.append(str(prim.GetPath().MakeRelativePath(root_path)))
    return relative_paths


def ensure_parent_xforms(stage: Usd.Stage, prim_path: Sdf.Path):
    parts = prim_path.GetParentPath().pathString.split("/")
    current = ""
    for part in parts:
        if not part:
            continue
        current += f"/{part}"
        if not stage.GetPrimAtPath(current):
            UsdGeom.Xform.Define(stage, current)


def main():
    args = parse_args()
    input_usd = Path(args.input_usd).expanduser().resolve()
    output_usd = Path(args.output_usd).expanduser().resolve()
    asset_name = args.asset_name or input_usd.stem

    if not input_usd.is_file():
        raise FileNotFoundError(f"Input USD not found: {input_usd}")

    source_stage = Usd.Stage.Open(str(input_usd))
    if source_stage is None:
        raise RuntimeError(f"Failed to open source USD: {input_usd}")

    source_root = get_source_root(source_stage)
    source_root_path = source_root.GetPath()
    geom_relative_paths = get_geom_relative_paths(source_root)

    output_usd.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(output_usd))
    if stage is None:
        raise RuntimeError(f"Failed to create output USD: {output_usd}")

    stage.SetMetadata("metersPerUnit", source_stage.GetMetadata("metersPerUnit"))
    up_axis = UsdGeom.GetStageUpAxis(source_stage)
    if up_axis:
        UsdGeom.SetStageUpAxis(stage, up_axis)

    root_path = Sdf.Path(f"/{asset_name}")
    link_path = root_path.AppendChild(args.link_name)
    visuals_path = link_path.AppendChild("visuals")
    collisions_path = link_path.AppendChild("collisions")

    root_xform = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(root_xform.GetPrim())

    link_xform = UsdGeom.Xform.Define(stage, link_path)
    link_prim = link_xform.GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(link_prim)

    visuals_prim = UsdGeom.Xform.Define(stage, visuals_path).GetPrim()
    visuals_prim.GetReferences().AddReference(
        assetPath=str(input_usd),
        primPath=source_root_path,
    )

    collisions_xform = UsdGeom.Xform.Define(stage, collisions_path)
    collisions_prim = collisions_xform.GetPrim()
    collisions_prim.GetReferences().AddReference(
        assetPath=str(input_usd),
        primPath=source_root_path,
    )
    UsdGeom.Imageable(collisions_prim).CreatePurposeAttr().Set(UsdGeom.Tokens.guide)

    for rel_path in geom_relative_paths:
        collision_geom_path = collisions_path.AppendPath(Sdf.Path(rel_path))
        ensure_parent_xforms(stage, collision_geom_path)
        collision_prim = stage.OverridePrim(collision_geom_path)
        UsdPhysics.CollisionAPI.Apply(collision_prim)
        if collision_prim.IsA(UsdGeom.Mesh) or rel_path:
            mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(collision_prim)
            mesh_collision.CreateApproximationAttr().Set(args.collision_approximation)
        UsdGeom.Imageable(collision_prim).CreatePurposeAttr().Set(UsdGeom.Tokens.guide)

    stage.GetRootLayer().Save()

    print("source_root:", source_root_path)
    print("geom_prim_count:", len(geom_relative_paths))
    print("output_usd:", output_usd)
    print("og_root:", root_path)
    print("og_link:", link_path)


if __name__ == "__main__":
    main()
