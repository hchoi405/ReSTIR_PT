import os
import subprocess
import re
import shutil
import sys
import numpy as np
import multiprocessing as mp
from functools import partial

import scene
from scripts import exr

import argparse

# Function to update the variable value
def update_variable(match, new_value):
    if match:
        variable, value, _, _ = match.groups()

        # Check if the original value is a string
        if value.startswith('"') or value.startswith("'"):
            return f'{variable} = "{new_value}"'
        else:
            return f'{variable} = {new_value}'
    else:
        print("doesn't match", match, new_value)

def set_variable(varname, value):
    filename = 'main.py'
    # read the contents of the file into a string
    with open(filename, 'r') as f:
        code = f.read()

    pattern = rf'(^{varname})\s*=\s*((["\'])(?P<inside_quotes>.*?)\3|.+)$'
    code = re.sub(pattern, lambda m: update_variable(m, value), code, flags=re.MULTILINE)

    # write the new code back to the file
    with open(filename, 'w') as f:
        f.write(code)

def change_scene(scene_name):
    # the file we want to modify
    filename = 'main.py'
    # read the contents of the file into a string
    with open(filename, 'r') as f:
        code = f.read()

    variables = ['SCENE_NAME', 'SCENE_FILE', 'SCENE_ANIM']
    values = [scene_name, scene.defs[scene_name]['file'], scene.defs[scene_name]['anim']]

    for varname, val in zip(variables, values):
        pattern = rf'(^{varname})\s*=\s*((["\'])(?P<inside_quotes>.*?)\3|.+)$'
        code = re.sub(pattern, lambda m: update_variable(m, val), code, flags=re.MULTILINE)

    # write the new code back to the file
    with open(filename, 'w') as f:
        f.write(code)

def change_method(new_method):
    # the file we want to modify
    filename = 'main.py'
    # read the contents of the file into a string
    with open(filename, 'r') as f:
        code = f.read()

    # use regular expressions to find the assignment statement for the METHOD variable
    match = re.search(r'METHOD\s*=\s*["\'](.*)["\']', code)

    if match:
        # replace the old value with the new value
        new_code = code[:match.start(1)] + new_method + code[match.end(1):]

        # write the new code back to the file
        with open(filename, 'w') as f:
            f.write(new_code)
    else:
        print('Could not find METHOD variable in file.')

def process_albedo(dest_dir, diffuse_file, spec_file):
    diffuse_img = exr.read_all(os.path.join(dest_dir, diffuse_file))['default']
    spec_img = exr.read_all(os.path.join(dest_dir, spec_file))['default']
    albedo = diffuse_img[:,:,:3] + spec_img[:,:,:3]

    # Make one when zero
    # For perfect specular like glass or mirror, make the albedo 1
    # It means current has the original color, without demodulation
    zeroRoughness = spec_img[:,:,3:4] == 0
    zeroAlbedo = albedo == 0
    nonzeroOpacity = diffuse_img[:,:,3:4] != 0
    perfect = zeroRoughness & zeroAlbedo & nonzeroOpacity

    if np.any(perfect): print('Pefect specular detected: ', spec_file)
    albedo[perfect] = 1

    exr.write(os.path.join(dest_dir, diffuse_file.replace('diffuseOpacity', 'albedo')), albedo)

    # Remove
    os.remove(os.path.join(dest_dir, diffuse_file))
    os.remove(os.path.join(dest_dir, spec_file))

def make_albedo(dest_dir):
    files = os.listdir(dest_dir)
    files = [f for f in files if f.endswith('.exr')]
    diffuse_files = [f for f in files if 'diffuseOpacity' in f]
    spec_files = [f for f in files if 'specRough' in f]

    with mp.Pool(10) as p:
        p.starmap(partial(process_albedo, dest_dir), zip(diffuse_files, spec_files))

def scale_exposure(img, exposure):
    return img * np.power(2.0, exposure)

def process(src_dir, dest_dir, frame, scene_name):
    # Tone mapping for ZeroDay
    if scene_name == "MEASURE_ONE" or scene_name == "MEASURE_SEVEN_COLORED_LIGHTS":
        exposure = 7.0 if scene_name == "MEASURE_ONE" else 5.0
        input_list = ["path", "current_demodul", "accum_demodul", "history_demodul", "emissive", "envLight", "indirectEmissive", "colorDiffuse", "colorSpecular"]
        for input in input_list:
            if os.path.exists(os.path.join(src_dir, f'{input}_{frame:04d}.exr')):
                img = exr.read_all(os.path.join(src_dir, f'{input}_{frame:04d}.exr'))['default']
                img = scale_exposure(img, exposure)
                exr.write(os.path.join(dest_dir, f'{input}_{frame:04d}.exr'), img, compression=exr.ZIP_COMPRESSION)

    # Copy path to current
    shutil.copy(os.path.join(src_dir, f'path_{frame:04d}.exr'), os.path.join(dest_dir, f'current_{frame:04d}.exr'))

    # LinearZ -> Depth
    shutil.move(os.path.join(src_dir, f'depth_{frame:04d}.exr'), os.path.join(dest_dir, f'linearZ_{frame:04d}.exr'))
    linearz_img = exr.read_all(os.path.join(src_dir, f'linearZ_{frame:04d}.exr'))['default']
    depth_img = linearz_img[:,:,0:1]
    exr.write(os.path.join(dest_dir, f'depth_{frame:04d}.exr'), depth_img, compression=exr.ZIP_COMPRESSION)

    # RGB to Z
    names = ["visibility", "primarySpecular", "primaryDelta"]
    for name in names:
        path = os.path.join(src_dir, f'{name}_{frame:04d}.exr')
        if os.path.exists(path):
            img = exr.read_all(path)['default']
            img = img[:,:,0:1]
            exr.write(os.path.join(dest_dir, f'{name}_{frame:04d}.exr'), img, compression=exr.ZIP_COMPRESSION)

    # specRough and diffuseOpacity to roughness and opacity
    spec_img = exr.read_all(os.path.join(src_dir, f'specRough_{frame:04d}.exr'))['default']
    rough_img = spec_img[:,:,3:4]
    exr.write(os.path.join(dest_dir, f'roughness_{frame:04d}.exr'), rough_img, compression=exr.ZIP_COMPRESSION)
    # os.remove(os.path.join(src_dir, f'specRough_{frame:04d}.exr'))
    diffuseOpacity_img = exr.read_all(os.path.join(src_dir, f'diffuseOpacity_{frame:04d}.exr'))['default']
    diffuse_img = diffuseOpacity_img[:,:,0:3]
    opacity_img = diffuseOpacity_img[:,:,3:4]
    exr.write(os.path.join(dest_dir, f'diffuseAlbedo_{frame:04d}.exr'), diffuse_img, compression=exr.ZIP_COMPRESSION)
    exr.write(os.path.join(dest_dir, f'opacity_{frame:04d}.exr'), opacity_img, compression=exr.ZIP_COMPRESSION)
    os.remove(os.path.join(src_dir, f'diffuseOpacity_{frame:04d}.exr'))

def postprocess_input(src_dir, scene_name):
    print('Post-processing the data...', end=' ', flush=True)
    # Find maximum number of frames
    files = os.listdir(src_dir)
    files = [f for f in files if f.endswith('.exr')]
    frames = [int(f.rsplit('_', 1)[1].split('.')[0]) for f in files]
    num_frames = max(frames) + 1

    with mp.Pool(processes=mp.cpu_count()) as pool:
        pool.starmap(process, [(src_dir, src_dir, frame, scene_name) for frame in range(num_frames)])

    print('Done.')

def process_exposure(input_list, exposure, frame):
    for input in input_list:
        input_path = os.path.join('./data/', f'{input}_{frame:04d}.exr')
        if os.path.exists(input_path):
            img = exr.read_all(input_path)['default']
            img = scale_exposure(img, exposure)
            exr.write(input_path, img, compression=exr.ZIP_COMPRESSION)
        else:
            print(f'{input_path} not found')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated script for Mogwai')
    parser.add_argument('--nobuild', action='store_true', default=False)
    parser.add_argument('--buildonly', action='store_true', default=False)
    parser.add_argument('--nopostprocessing', action='store_true', default=False)
    parser.add_argument('--methods', nargs='+', default=[], choices=['input', 'ref', 'svgf_optix'])
    parser.add_argument('--nas', action='store_true', default=False)
    parser.add_argument('--interactive', action='store_true', default=False)
    args = parser.parse_args()

    if args.interactive:
        args.nopostprocessing = True
        set_variable("INTERACTIVE", True)
        set_variable("NO_CAPTURE_INPUT", True)
    else:
        set_variable("INTERACTIVE", False)
        set_variable("NO_CAPTURE_INPUT", False)

    #########################################################
    # Call build in silent mode and check if it was successful
    print('Building..', end=' ')
    if not args.nobuild or args.buildonly:
        sys.stdout.flush()
        if args.buildonly:
            ret = subprocess.run(['C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe', "Falcor.sln", "/p:Configuration=ReleaseD3D12", "/m:24", "/v:m"])
        else:
            ret = subprocess.run(['C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe', "Falcor.sln", "/p:Configuration=ReleaseD3D12", "/m:24", "/v:m"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ret.returncode != 0:
            print('Failed.')
            sys.exit(1)
        print('Done.')

        if args.buildonly:
            sys.exit(0)
    else:
        print('Skipped.')

    dir_names = ["dataset_restir2"]
    for j in range(len(dir_names)):
        print(f'Processing {dir_names[j]}...')

        #########################################################
        # Call Mogwai
        binary_path = os.path.join("Bin", "x64", "Release", "Mogwai.exe")
        bianry_args = ["--script=main.py"]
        script_dir = os.path.abspath(os.path.dirname(__file__))
        binary_abs_path = os.path.join(script_dir, binary_path)

        scene_names = scene.names
        scene_numframes = scene.frames
        set_variable("ENABLE_RESTIR", True)

        print('automated.py for scenes', scene_names)

        for i in range(len(scene_names)):
            scene_name = scene_names[i]

            change_scene(scene_name)

            for method in args.methods:
                change_method(method)

                # Launch Mogwai
                subprocess.run([binary_abs_path] + bianry_args)

                if args.nopostprocessing:
                    continue

                if method == 'input':
                    # Modulate
                    postprocess_input('./data/', scene_name)
                    pass
                elif method == 'ref':
                    # Scale exposure of
                    if scene_name == "MEASURE_ONE":
                        exposure = 7.0
                    elif scene_name == "MEASURE_SEVEN_COLORED_LIGHTS":
                        exposure = 5.0
                    else:
                        exposure = 0.0
                    input_list = ["ref", "ref_demodul", "ref_envLight", "ref_emissive"]

                    with mp.Pool(processes=mp.cpu_count()) as pool:
                        pool.map(partial(process_exposure, input_list, exposure), range(scene_numframes[i]))

            # Move data directory
            # check if the destination directory already exists
            dest_dir = f'./{dir_names[j]}/data_{scene_name}'
            print(f'Moving to {dest_dir}...', end=' ', flush=True)
            if os.path.exists('./data'):
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir)
                for f in os.listdir('./data/'):
                    shutil.move(os.path.join('./data/', f), os.path.join(dest_dir, f))
                shutil.rmtree('./data/')
            print('Done.')

            # Move to NAS asynchronously
            if args.nas:
                print('Moving to NAS...', end=' ', flush=True)
                nas_dir = f'//CGLAB-NAS/NFSStorage/{dir_names[j]}/data_{scene_name}'
                p = subprocess.Popen(['robocopy', dest_dir, nas_dir, '/MOVE', '/MT:6', '/R:10', '/W:10'], shell=True)

        print('Done.')


    exit()
