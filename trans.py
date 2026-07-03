import sys

try:
    import bpy
    from mathutils import Vector
except ModuleNotFoundError as e:
    if getattr(e, "name", "") in {"bpy", "mathutils"}:
        blender_bin = "/Applications/Blender.app/Contents/MacOS/Blender"
        script_path = __file__
        sys.stderr.write(
            "找不到 bpy/mathutils：这个脚本必须在 Blender 的 Python 环境里运行。\n\n"
            "用命令行运行（推荐）：\n"
            f'  "{blender_bin}" --background --python "{script_path}"\n\n'
            "或：打开 Blender → Scripting → Run Script。\n"
        )
        raise SystemExit(1) from None
    raise
import os
import re
import shutil
from pathlib import Path

# =======================
# 你只需要改这里
# =======================
ASSET_NAME = "cola_can"

# 导出目录，改成你自己的路径
# Mac 示例：
OUT_DIR = "/Users/a54197/Documents/vcis文档/智源学者/cola_can_obj"

# 如果你希望用命令行后台导出某个 .blend，把路径填这里
# 留空则使用当前打开的 Blender 场景（或 Blender 启动文件）
BLEND_FILE = ""

# 如果当前 Blender 已经打开并有模型，这里留空
# 如果你想从 OBJ 文件夹重新导入，可以填 OBJ 所在文件夹路径
SOURCE_OBJ_DIR = "/Users/a54197/Documents/vcis文档/智源学者/cola_can_obj"

CANDIDATE_OBJ_FROM_OUT_DIR = True

CENTER_TO_ORIGIN = True
EXPORT_SELECTED_ONLY = False
REMOVE_CAMERA_LIGHT = True
# =======================


def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not name:
        name = "Object"
    if name[0].isdigit():
        name = "M_" + name
    return name


def get_supported_kwargs(op, kwargs):
    """只传 Blender 当前版本支持的参数，避免版本差异报错。"""
    props = op.get_rna_type().properties
    valid = {p.identifier for p in props if not p.is_readonly}
    return {k: v for k, v in kwargs.items() if k in valid}


def set_bool_or_enum(op, kwargs, name, bool_value=True, enum_candidates=None):
    """兼容 Boolean / Enum 两种参数形式。"""
    props = op.get_rna_type().properties
    if name not in props:
        return

    prop = props[name]

    if prop.type == "BOOLEAN":
        kwargs[name] = bool_value
        return

    if prop.type == "ENUM" and enum_candidates:
        available = [item.identifier for item in prop.enum_items]
        for candidate in enum_candidates:
            if candidate in available:
                kwargs[name] = candidate
                return


def clean_scene():
    """删除不需要的相机、灯光、空物体等，让 USD 更干净。"""
    for obj in list(bpy.context.scene.objects):
        if REMOVE_CAMERA_LIGHT and obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    # 只保留 MESH，删除 OBJ 导入时可能带来的空物体
    # 如果你的模型依赖父级空物体，这里会先保留世界变换再解除父级
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]

    for obj in mesh_objects:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world

    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)

    # 清理名称，避免 USD prim 名称异常
    for obj in bpy.context.scene.objects:
        obj.name = safe_name(obj.name)
        obj.data.name = safe_name(obj.data.name)

    for mat in bpy.data.materials:
        mat.name = safe_name(mat.name)


def import_objs_if_needed():
    """如果 SOURCE_OBJ_DIR 不为空，则先清空场景并导入该文件夹下所有 OBJ。"""
    if not SOURCE_OBJ_DIR:
        return

    src = Path(SOURCE_OBJ_DIR)
    if not src.exists():
        raise FileNotFoundError(f"OBJ 文件夹不存在: {src}")

    obj_files = sorted(src.glob("*.obj"))
    if not obj_files:
        raise FileNotFoundError(f"该文件夹里没有 OBJ 文件: {src}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    for obj_path in obj_files:
        print(f"正在导入 OBJ: {obj_path}")

        # Blender 新版一般是 bpy.ops.wm.obj_import
        if hasattr(bpy.ops.wm, "obj_import"):
            op = bpy.ops.wm.obj_import
            kwargs = get_supported_kwargs(op, {
                "filepath": str(obj_path),
            })
            op(**kwargs)
        else:
            # 老版本 OBJ 导入方式
            bpy.ops.import_scene.obj(filepath=str(obj_path))


def ensure_scene_has_meshes(out_dir: Path):
    global SOURCE_OBJ_DIR

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if mesh_objects:
        return

    candidates = []
    if SOURCE_OBJ_DIR:
        candidates.append(Path(SOURCE_OBJ_DIR))
    candidates.append(out_dir)
    candidates.append(Path(__file__).resolve().parent)

    for cand in candidates:
        try:
            obj_files = sorted(cand.glob("*.obj"))
        except Exception:
            continue
        if obj_files:
            SOURCE_OBJ_DIR = str(cand)
            import_objs_if_needed()
            return

    raise RuntimeError(
        "场景里没有 MESH 物体，且未找到可导入的 OBJ。\n"
        f"请：\n"
        f"1) 在 Blender 里打开包含模型的 .blend 后运行脚本，或\n"
        f"2) 把 SOURCE_OBJ_DIR 指向含 .obj 的文件夹。\n"
        f"当前 OUT_DIR: {out_dir}"
    )


def center_asset_to_origin():
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        return

    corners = []
    for obj in mesh_objects:
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ Vector(corner))

    min_v = Vector((
        min(v.x for v in corners),
        min(v.y for v in corners),
        min(v.z for v in corners),
    ))
    max_v = Vector((
        max(v.x for v in corners),
        max(v.y for v in corners),
        max(v.z for v in corners),
    ))

    center = (min_v + max_v) * 0.5

    for obj in mesh_objects:
        obj.location -= center


def apply_rotation_scale():
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        return

    bpy.ops.object.select_all(action="DESELECT")

    for obj in mesh_objects:
        obj.select_set(True)

    bpy.context.view_layer.objects.active = mesh_objects[0]

    # 保留位置，只应用旋转和缩放
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def copy_textures(out_dir: Path):
    textures_dir = out_dir / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    copied = []

    for img in bpy.data.images:
        if not img.filepath:
            continue

        src = Path(bpy.path.abspath(img.filepath))

        if not src.exists():
            print(f"警告：找不到贴图文件: {src}")
            continue

        dst = textures_dir / src.name

        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)

        # 让 Blender 材质节点引用导出目录里的贴图
        img.filepath = str(dst)
        try:
            img.reload()
        except Exception:
            pass

        copied.append(dst)

    return copied


def check_uvs():
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            if len(obj.data.uv_layers) == 0:
                print(f"警告：{obj.name} 没有 UV，贴图可能无法正确显示。")


def export_usd(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_usda = out_dir / f"{ASSET_NAME}.usda"
    final_usd = out_dir / f"{ASSET_NAME}.usd"

    if tmp_usda.exists():
        tmp_usda.unlink()
    if final_usd.exists():
        final_usd.unlink()

    op = bpy.ops.wm.usd_export

    kwargs = {
        "filepath": str(tmp_usda),
        "selected_objects_only": EXPORT_SELECTED_ONLY,
        "visible_objects_only": True,
        "export_animation": False,
        "export_hair": False,
        "export_uvmaps": True,
        "export_normals": True,
        "export_cameras": False,
        "export_lights": False,
        "generate_preview_surface": True,
        "convert_to_usd_preview_surface": True,
        "relative_paths": True,
        "relative_path": True,
        "root_prim_path": f"/World/{safe_name(ASSET_NAME)}",
        "evaluation_mode": "RENDER",
    }

    # 材质导出：不同 Blender 版本这里可能是 Boolean，也可能是 Enum
    set_bool_or_enum(
        op,
        kwargs,
        "export_materials",
        True,
        enum_candidates=["EXPORT", "USD_PREVIEW_SURFACE", "PREVIEW", "MATERIALS"],
    )

    # 贴图导出：Blender 文档里 NEW 表示导出到 USD 旁边的 textures 文件夹
    set_bool_or_enum(
        op,
        kwargs,
        "export_textures",
        True,
        enum_candidates=["NEW", "COPY", "EXPORT"],
    )

    set_bool_or_enum(
        op,
        kwargs,
        "export_textures_mode",
        True,
        enum_candidates=["NEW", "COPY", "EXPORT"],
    )

    # 尽量强制 ASCII / USDA
    set_bool_or_enum(
        op,
        kwargs,
        "file_format",
        True,
        enum_candidates=["USDA", "ASCII", "USD"],
    )

    kwargs = get_supported_kwargs(op, kwargs)

    print("USD 导出参数：")
    for k, v in kwargs.items():
        print(f"  {k}: {v}")

    result = op(**kwargs)
    print("Blender USD 导出结果:", result)

    if not tmp_usda.exists():
        raise RuntimeError("导出失败：没有生成 .usda 文件")

    # 合法操作：把文本 usda 改成 usd 后缀
    os.replace(tmp_usda, final_usd)

    # 检查文件头，确认它是文本 USD，而不是二进制 USDC
    with open(final_usd, "rb") as f:
        header = f.read(16)

    print("最终 USD 文件:", final_usd)
    print("文件头:", header)

    if not header.startswith(b"#usda"):
        print("警告：文件头不是 #usda，可能不是文本 USD。")

    return final_usd


def main():
    global SOURCE_OBJ_DIR

    if BLEND_FILE:
        blend_path = Path(BLEND_FILE)
        if not blend_path.exists():
            raise FileNotFoundError(f"BLEND_FILE 不存在: {blend_path}")
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))

    out_dir = Path(OUT_DIR)

    if CANDIDATE_OBJ_FROM_OUT_DIR and (not SOURCE_OBJ_DIR):
        try:
            if any(out_dir.glob("*.obj")):
                SOURCE_OBJ_DIR = str(out_dir)
        except Exception:
            pass

    import_objs_if_needed()
    ensure_scene_has_meshes(out_dir)
    clean_scene()

    if CENTER_TO_ORIGIN:
        center_asset_to_origin()

    apply_rotation_scale()
    check_uvs()
    copied_textures = copy_textures(out_dir)

    usd_path = export_usd(out_dir)

    print("\n完成。导出结果：")
    print(f"USD 文件: {usd_path}")
    print(f"贴图数量: {len(copied_textures)}")
    print(f"贴图目录: {out_dir / 'textures'}")
    print("\n把整个文件夹一起放进 OG，不要只复制 .usd 文件。")


main()
