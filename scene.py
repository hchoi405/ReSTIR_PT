HOME_DIR = "C:/Users/hchoi/repositories"
FALCOR_DIR = f"{HOME_DIR}/ReSTIR_PT"
NAS_DIR = f"F:"

MEDIA_DIR = f"{FALCOR_DIR}/media/"
ORCA_PATH = f"{HOME_DIR}/ORCA/"
FBX_PATH = f"{FALCOR_DIR}/fbxscenes/"
FBX_REMOTE_PATH = f"{NAS_DIR}/fbxscenes/"

defs = {
    # "BistroExteriorDoF": {'file': ORCA_PATH + "Bistro/BistroExteriorDoF.pyscene", 'anim':[1400, 1500]},
    # "BistroExterior2": {'file': ORCA_PATH + "Bistro/BistroExterior.pyscene", 'anim':[1400, 1700]},
    # "BistroExteriorDynamic": {'file': ORCA_PATH + "BistroExterior_dynamic_camera_flipped/BistroExterior_dynamic.pyscene", 'anim':[0, 300]},
    # "staircase" : {'file': FBX_PATH + "staircase/staircase.pyscene", 'anim':[0, 300]},
    # "EmeraldSquare2" : {'file': ORCA_PATH + "EmeraldSquare/EmeraldSquare_Day.pyscene", 'anim':[1700, 2000]},

    # "spaceship" : {'file': FBX_REMOTE_PATH + "spaceship/spaceship.pyscene", 'anim':[0, 300]},
    # "modernhall" : {'file': FBX_REMOTE_PATH + "modernhall/modernhall.pyscene", 'anim':[100, 101]},
    # "kitchenware" : {'file': FBX_REMOTE_PATH + "kitchenware/kitchenware.pyscene", 'anim':[0, 300]},
    # "terrazzo-kitchen" : {'file': FBX_REMOTE_PATH + "terrazzo-kitchen/terrazzo-kitchen.pyscene", 'anim':[0, 300]},
    "kitchen5" : {'file': FBX_REMOTE_PATH + "kitchen5/kitchen5.pyscene", 'anim':[0, 300]},
}

considered = {
    # "classroom" : {'file': FBX_PATH + "classroom/classroom.pyscene", 'anim':[0, 300]},
    # "BistroExterior1": {'file': ORCA_PATH + "Bistro/BistroExterior.pyscene", 'anim':[0, 600]},
    # "BistroExterior3": {'file': ORCA_PATH + "Bistro/BistroExterior.pyscene", 'anim':[3600, 4200]},
    # "SunTemple2" : {'file': ORCA_PATH + "SunTemple/SunTemple.pyscene", 'anim':[1600, 2200]},
    # "EmeraldSquare1" : {'file': ORCA_PATH + "EmeraldSquare/EmeraldSquare_Day.pyscene", 'anim':[0, 600]},
    # "whiteroom" : {'file': FBX_PATH + "whiteroom/whiteroom.pyscene", 'anim':[0, 600]},
    # "SunTemple1" : {'file': ORCA_PATH + "SunTemple/SunTemple.pyscene", 'anim':[300, 900]},
    # "breakfastroom" : {'file': FBX_PATH + "the-breakfast-room/breakfastroom.pyscene", 'anim':[0, 600]},
    # "VeachAjarAnimated": {'file': "VeachAjar/VeachAjarAnimated.pyscene", 'anim':[0, 600]},
    # "BistroInterior_Wine": {'file': ORCA_PATH + "Bistro/BistroInterior_Wine.pyscene", 'anim':[0, 100]},
    # "BistroInterior": {'file': ORCA_PATH + "Bistro/BistroInterior.pyscene", 'anim':[0, 600]},
}

tmp = {
    # "BistroInterior_Wine": {'file': ORCA_PATH + "Bistro/BistroInterior_Wine.pyscene", 'anim':[0, 100]},
    # "Arcade": {'file': "Arcade/Arcade.pyscene", 'anim':[0, 10]},
    # "VeachAjar": {'file': "VeachAjar/VeachAjar.pyscene", 'anim':[0, 100]},
    # "MEASURE_SEVEN_COLORED_LIGHTS": {'file': ORCA_PATH + "ZeroDay/MEASURE_SEVEN/MEASURE_SEVEN_COLORED_LIGHTS.pyscene", 'anim':[100, 200]}, # Exp+5.0
    # "BistroExterior": {'file': ORCA_PATH + "Bistro/BistroExterior.pyscene", 'anim':[0, 100]},
    # "Classroom": {'file': BITTERLI_SCENE_PATH + "classroom/scene.pyscene", 'anim':[0, 300]}, # [0, 597]
    # "Dining-room": {'file': BITTERLI_SCENE_PATH + "dining-room/scene.pyscene", 'anim':[0, 300]},
    # "Dining-room-dynamic": {'file': BITTERLI_SCENE_PATH + "dining-room/scene-dynamic.pyscene", 'anim':[0, 0]},
    # "Staircase": {'file': BITTERLI_SCENE_PATH + "staircase/scene2.pyscene", 'anim':[0, 300]}, # [0, 447]
    # "Staircase2": {'file': BITTERLI_SCENE_PATH + "staircase/scene2.pyscene", 'anim':[0, 300]},
    "VeachAjar": {'file': "VeachAjar/VeachAjar.pyscene", 'anim':[0, 0]},
    "CornellBox": {'file': "TestScenes/CornellBox.pyscene", 'anim':[0, 0]},
    "MEASURE_SEVEN_COLORED_LIGHTS": {'file': "ZeroDay_v1/MEASURE_SEVEN/MEASURE_SEVEN_COLORED_LIGHTS.pyscene", 'anim':[0, 0]},
    "BistroExterior": {'file': ORCA_PATH + "Bistro/BistroExterior.pyscene", 'anim':[0, 1]},
    "BistroInterior": {'file': ORCA_PATH + "Bistro/BistroInterior.pyscene", 'anim':[0, 0]},
    "BistroInterior_Wine": {'file': ORCA_PATH + "Bistro/BistroInterior_Wine.pyscene", 'anim':[0, 100]},
    "SunTemple" : {'file': ORCA_PATH + "SunTemple/SunTemple.pyscene", 'anim':[250, 350]},
    "MEASURE_ONE": {'file': ORCA_PATH + "ZeroDay/MEASURE_ONE/MEASURE_ONE.pyscene", 'anim':[0, 100]}, # Exp+7
    "MEASURE_SEVEN_COLORED_LIGHTS": {'file': ORCA_PATH + "ZeroDay/MEASURE_SEVEN/MEASURE_SEVEN_COLORED_LIGHTS.pyscene", 'anim':[0, 100]}, # Exp+5.0
}

