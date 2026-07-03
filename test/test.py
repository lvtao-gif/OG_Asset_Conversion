import yaml
import torch as th
import numpy
import random

import omnigibson as og
from omnigibson.macros import gm
from omnigibson.utils.constants import PrimType # 刚体/软体布料
import omnigibson.lazy as lazy
from omnigibson.utils.ui_utils import KeyboardRobotController

import omnigibson.utils.transform_utils as T  # 3D变换工具库（坐标转换、旋转等）
import math  # 数学计算库，用于圆周率等数学常数






# 主函数
def main_sim_and_sam(
    task_name=None,
    task_dir=None,
    capture_dir=None,
    robot_type=None,
    Save_video_date=True,
    enable_object_states=False,
    enable_transition_rules=False,
    enable_reset_hotkey=False,
):  # Save_video_date 是否采集视频数据
    
    gm.USE_GPU_DYNAMICS = False
    gm.ENABLE_FLATCACHE = False
    # Custom USD smoke tests do not need the full BEHAVIOR state / transition stack.
    # Disabling them avoids the v3.7.1 contact-view invalidation path in toggle updates.
    gm.ENABLE_OBJECT_STATES = enable_object_states
    gm.ENABLE_TRANSITION_RULES = enable_transition_rules
    gm.HEADLESS = False

    # 加载预选的配置文件 - 包含环境场景、obj、机器人等
    config_filename = fr"./{task_dir}/Scene_cfg.yaml"
    cfg_Scene = yaml.load(open(config_filename, "r", encoding="utf-8"), Loader=yaml.FullLoader)

    for obj in cfg_Scene["objects"]:
        if "orientation" in obj:
            ori = obj["orientation"]
            if len(ori) == 3:
                obj["orientation"] = T.euler2quat(th.tensor([math.radians(a) for a in ori]))
            elif len(ori) == 4:
                pass
    for obj in cfg_Scene["objects"]:
        if "prim_type" in obj:
            if obj["prim_type"] == "RIGID":
                obj["prim_type"] = PrimType.RIGID
            elif obj["prim_type"] == "CLOTH":
                obj["prim_type"] = PrimType.CLOTH
                gm.USE_GPU_DYNAMICS = True
            else:
                raise ValueError(f"Unknown prim_type: {obj['prim_type']}")
    if "rendering_frequency" in cfg_Scene["env"]:
        if cfg_Scene["env"]["rendering_frequency"] == 60:
            gm.USE_GPU_DYNAMICS = True
            gm.ENABLE_HQ_RENDERING = True
            gm.ENABLE_FLATCACHE = False

    for obj in cfg_Scene["objects"]:
        if "position" in obj:
            pos = obj["position"]
            if isinstance(pos[0], list) and isinstance(pos[1], list):
                x = random.uniform(pos[0][0], pos[0][1])
                y = random.uniform(pos[1][0], pos[1][1])
                z = pos[2]
                obj["position"] = [x, y, z]
                print(f"检索到物体 {obj['name']} 为区间形式（任务物体），随机采样位置：[{x:.4f}, {y:.4f}, {z}]")

    cfg_cameras = yaml.load(open("./cfg/cameras.yaml", "r", encoding="utf-8"), Loader=yaml.FullLoader)
    cfg_Scene["env"]["external_sensors"] += cfg_cameras[robot_type]["external_sensors"]

    env = og.Environment(configs=cfg_Scene)
    env.reset()

    scene_objects = {}
    missing_objects = []
    if 'objects' in cfg_Scene:
        for obj_config in cfg_Scene['objects']:
            if 'name' in obj_config:
                obj_name = obj_config['name']
                obj_reference = env.scene.object_registry("name", obj_name)
                scene_objects[obj_name] = obj_reference
                if obj_reference is None:
                    missing_objects.append(obj_name)
                    print(f"[未找到] 物体未加载到 scene.object_registry: {obj_name}")
                else:
                    print(f"[已加载] 物体: {obj_name}")

    if missing_objects:
        print(f"[汇总] 以下物体未成功注册: {missing_objects}")
        required_usd_objects = [
            obj["name"]
            for obj in cfg_Scene["objects"]
            if obj.get("type") == "USDObject" and obj.get("name") in missing_objects
        ]
        if required_usd_objects:
            raise RuntimeError(f"关键 USDObject 未加载成功: {required_usd_objects}")

    structure_categories = ['floors', 'walls', 'ceilings']
    scene_model = cfg_Scene.get('scene', {}).get('scene_model', '')
    if scene_model:
        for category in structure_categories:
            registry_result = env.scene.object_registry("category", category)
            if registry_result is not None:
                objects_list = list(registry_result)
                if objects_list:
                    scene_objects[category] = objects_list
                    print(f"已获取对象引用-类别: {category}, 数量: {len(objects_list)}")


    robot = env.robots[0]
    action_dim = robot.action_dim
    action_generator = KeyboardRobotController(robot=robot)
    if enable_reset_hotkey:
        action_generator.register_custom_keymapping(
            key=lazy.carb.input.KeyboardInput.R,  # 按键：R
            description="Reset the robot",         # 描述：重置机器人
            callback_fn=lambda: env.reset(),       # 回调函数：调用环境重置
        )
    action_generator.print_keyboard_teleop_info()     # 打印键盘控制说明信息
    # og.sim.enable_viewer_camera_teleoperation()


    #######################################
    # 将主镜头移动到一个良好的观察位置
    if "start_viewer_camera_pos_ort" in cfg_Scene:
        cam_cfg = cfg_Scene["start_viewer_camera_pos_ort"]
        pos = cam_cfg.get("position", [0,0,2])
        ort = cam_cfg.get("orientation", [0,0,0,1])
        og.sim.viewer_camera.set_position_orientation(position=pos, orientation=ort)
        print(f"摄像机位置与朝向已设置为：pos={pos}, ort={ort}")

    for obj in cfg_Scene["objects"]:
        if "ObjectStates" not in obj:
            continue
        obj_name = obj["name"]
        obj_ref = scene_objects.get(obj_name)
        if obj_ref is None:
            print(f"[警告] 未找到物体引用: {obj_name}")
            continue


    # 再仿真几步，让系统稳定
    zero_action = numpy.zeros(action_dim)
    for _ in range(20):
        env.step(zero_action)    





    # ============================================= #
    # 在下面位置补充VLA初始化以及接收任务指令函数
    
    # ......

    # ============================================= # 













    STEP = 0
    # ====== 开始无限循环仿真 ======
    print("\033[92m====== 开始进行仿真评测 ======\033[0m")
    while 1:
        ######################################################
        # ============ 执行一步仿真 ==============
        # 推进仿真运行 1 Step
        STEP += 1



        # 使用机器人控制
        # =========================================== #
        # 在该位置补充VLA获取场景信息与推理控制机器人代码
        

        # ......


        # =========================================== #



        action = action_generator.get_teleop_action()   # 获取键盘输入的遥控动作
        env.step(action=action*1.0)


if __name__ == "__main__":
    main_sim_and_sam(task_name='将桌子上的香蕉放入收纳篮中', 
                     task_dir='./env_yaml_test', 
                     capture_dir='./env_yaml_test', 
                     robot_type='固定式机器人', 
                     Save_video_date=True
                     )
