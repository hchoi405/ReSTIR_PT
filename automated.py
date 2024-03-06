import os
import subprocess
import re
import shutil
import sys
import numpy as np
import multiprocessing as mp
from functools import partial
import argparse

import scene
import scripts.exr as exr

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

def change_variable_code(code, varname, new_value):
    pattern = rf'(^{varname})\s*=\s*((["\'])(?P<inside_quotes>.*?)\3|.+)$'
    code = re.sub(pattern, lambda m: update_variable(m, new_value), code, flags=re.MULTILINE)
    return code

def change_scene(scene_name):
    # the file we want to modify
    filename = 'main.py'
    # read the contents of the file into a string
    with open(filename, 'r') as f:
        code = f.read()

    variables = ['NAME', 'FILE', 'ANIM']
    values = [scene_name, scene.defs[scene_name]['file'], scene.defs[scene_name]['anim']]

    for varname, val in zip(variables, values):
        code = change_variable_code(code, varname, val)

    # write the new code back to the file
    with open(filename, 'w') as f:
        f.write(code)

def update_pyvariable(filename, varname, new_value):
    assert(filename.endswith('.py'))

    # read the contents of the file into a string
    with open(filename, 'r') as f:
        code = f.read()
        code = change_variable_code(code, varname, new_value)

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

def merge_gbufs(dest_dirs, num):
    directory = dest_dirs[0]
    files = os.listdir(directory)
    files = [f for f in files if f.endswith('.exr')]
    types = [f.rsplit('_', 1)[0] for f in files]
    types = list(set(types))

    dest_dir = dest_dirs[0].rsplit('_', 1)[0]
    if not os.path.exists(dest_dir):
        os.mkdir(dest_dir)

    frames = [int(f.rsplit('_', 1)[1].split('.')[0]) for f in files]
    num_frames = max(frames) + 1
    print(types)
    print(num_frames)

    # Load the exr files and average them
    for t in types:
        for frame in range(num_frames):
            imgs = []
            for directory in dest_dirs:
                filename = f'{t}_{frame:04d}.exr'
                filepath = os.path.join(directory, filename)
                img = exr.read_all(filepath)['default']
                imgs.append(img)
            imgs = np.array(imgs)
            avg_img = np.mean(imgs, axis=0)
            dest_path = os.path.join(dest_dir, f'{t}_{frame:04d}.exr')
            exr.write(dest_path, avg_img)

def process_albedo(dest_dir, primary_delta_file, nrd_reflectance_file, albedo_file):
    primary_delta_img = exr.read_all(os.path.join(dest_dir, primary_delta_file))['default']
    nrd_reflectance_img = exr.read_all(os.path.join(dest_dir, nrd_reflectance_file))['default']
    albedo_img = exr.read_all(os.path.join(dest_dir, albedo_file))['default']

    new_albedo = np.where(primary_delta_img[:,:,0:1] > 0.0, nrd_reflectance_img, albedo_img)
    exr.write(os.path.join(dest_dir, albedo_file), new_albedo, compression=exr.ZIP_COMPRESSION)

def make_albedo(dest_dir):
    files = os.listdir(dest_dir)
    files = [f for f in files if f.endswith('.exr')]
    primary_delta_files = [f for f in files if f.startswith('primaryDelta')]
    nrd_reflectance_files = [f for f in files if f.startswith('nrdDeltaReflectionReflectance')]
    albedo_files = [f for f in files if f.startswith('albedo')]

    with mp.Pool(10) as p:
        p.starmap(partial(process_albedo, dest_dir), zip(primary_delta_files, nrd_reflectance_files, albedo_files))

def scale_exposure(img, exposure):
    return img * np.power(2.0, exposure)

def process(src_dir, dest_dir, frame, scene_name):
    # # Copy path to current
    # shutil.copy(os.path.join(src_dir, f'path_{frame:04d}.exr'), os.path.join(dest_dir, f'current_{frame:04d}.exr'))

    # LinearZ -> Depth
    shutil.move(os.path.join(src_dir, f'depth_{frame:04d}.exr'), os.path.join(dest_dir, f'linearZ_{frame:04d}.exr'))
    linearz_img = exr.read_all(os.path.join(src_dir, f'linearZ_{frame:04d}.exr'))['default']
    depth_img = linearz_img[:,:,0:1]
    exr.write(os.path.join(dest_dir, f'depth_{frame:04d}.exr'), depth_img, compression=exr.ZIP_COMPRESSION)

    # RGB to Z
    names = ["visibility"]
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
    exr.write(os.path.join(dest_dir, f'specularAlbedo_{frame:04d}.exr'), spec_img[:,:,0:3], compression=exr.ZIP_COMPRESSION)
    os.remove(os.path.join(src_dir, f'specRough_{frame:04d}.exr'))
    diffuseOpacity_img = exr.read_all(os.path.join(src_dir, f'diffuseOpacity_{frame:04d}.exr'))['default']
    diffuse_img = diffuseOpacity_img[:,:,0:3]
    opacity_img = diffuseOpacity_img[:,:,3:4]
    exr.write(os.path.join(dest_dir, f'diffuseAlbedo_{frame:04d}.exr'), diffuse_img, compression=exr.ZIP_COMPRESSION)
    exr.write(os.path.join(dest_dir, f'opacity_{frame:04d}.exr'), opacity_img, compression=exr.ZIP_COMPRESSION)
    os.remove(os.path.join(src_dir, f'diffuseOpacity_{frame:04d}.exr'))

    # # Rename nrdDeltaReflectionReflectance to albedo
    # if os.path.exists(os.path.join(src_dir, f'nrdDeltaReflectionReflectance_{frame:04d}.exr')):
    #     shutil.move(os.path.join(src_dir, f'nrdDeltaReflectionReflectance_{frame:04d}.exr'), os.path.join(dest_dir, f'albedo_{frame:04d}.exr'))

def postprocess_input(src_dir, scene_name):
    print('Post-processing the input...', end=' ', flush=True)

    # Find frames
    exr_list = os.listdir(src_dir)
    exr_list = [f for f in exr_list if f.endswith('.exr')]
    if len(exr_list) == 0:
        print('No exr files found. Skip.')
        return

    # Collect frames from files
    frames = sorted(list(set([int(f.split('.')[0].split('_')[-1]) for f in exr_list])))
    num_frames = scene.defs[scene_name]['anim'][1] - scene.defs[scene_name]['anim'][0] + 1

    # Process multiprocessing
    num_workers = min(60, mp.cpu_count()) # maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process, [(src_dir, src_dir, frame, scene_name) for frame in frames])
    pool.close()

    # Remove last frames, if does not exist, ignore it
    if scene_name != "Dining-room-dynamic":
        for frame in range(frames[0] + num_frames, frames[0] + num_frames + 10):
            for f in os.listdir(src_dir):
                if f.endswith(f'{frame:04d}.exr'):
                    if os.path.exists(os.path.join(src_dir, f)):
                        os.remove(os.path.join(src_dir, f))

    print('Done.')

def process_ref(src_dir, dest_dir, frame):
    # Change RGB visibility to Z
    # viz = exr.read_all(os.path.join(src_dir, f'ref_visibility_{frame:04d}.exr'))['default']
    # viz = viz[:,:,0:1]
    # exr.write(os.path.join(dest_dir, f'ref_visibility_{frame:04d}.exr'), viz, compression=exr.ZIP_COMPRESSION)
    pass

def postprocess_ref(src_dir, scene_name):
    print('Post-processing the ref...', end=' ', flush=True)

    # Find frames
    exr_list = os.listdir(src_dir)
    exr_list = [f for f in exr_list if f.endswith('.exr')]
    if len(exr_list) == 0:
        print('No exr files found. Skip.')
        return
    frames = sorted(list(set([int(f.split('.')[0].split('_')[-1]) for f in exr_list])))
    num_frames = scene.defs[scene_name]['anim'][1] - scene.defs[scene_name]['anim'][0] + 1

    num_workers = min(60, mp.cpu_count()) # maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process_ref, [(src_dir, src_dir, frame) for frame in frames])
    pool.close()

def process_exposure(input_list, exposure, frame):
    for input in input_list:
        input_path = os.path.join('./output/', f'{input}_{frame:04d}.exr')
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
    parser.add_argument('--methods', nargs='+', default=[], choices=['input', 'ref', 'svgf_optix'], required=True)
    parser.add_argument('--nas', action='store_true', default=False)
    parser.add_argument('--interactive', action='store_true', default=False)
    parser.add_argument('--dir', default='dataset')
    args = parser.parse_args()

    # Update HOME_DIR
    HOME_DIR = os.path.abspath('../').replace('\\', '/')
    update_pyvariable("scene.py", "HOME_DIR", HOME_DIR)

    OUT_DIR = os.path.abspath('./output').replace('\\', '/')
    if not os.path.exists(OUT_DIR):
        print(f'{OUT_DIR} not found. Trying to create...')
        try:
            os.mkdir(OUT_DIR)
        except:
            print(f'Failed to create {OUT_DIR}.', 'Check if you set the correct directory OUT_DIR in automated.py')
            exit(-1)

    if args.interactive:
        args.nopostprocessing = True
        update_pyvariable("main.py", "INTERACTIVE", True)
        update_pyvariable("main.py", "REF_COUNT", 65536)
    else:
        update_pyvariable("main.py", "INTERACTIVE", False)
        update_pyvariable("main.py", "OUT_DIR", OUT_DIR)
        update_pyvariable("main.py", "REF_COUNT", 1024)
        # Create output directory
        os.makedirs(OUT_DIR, exist_ok=True)

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

    directory = args.dir
    print(f'Generating at {directory}...')

    #########################################################
    # Call Mogwai
    binary_path = os.path.join("Bin", "x64", "Release", "Mogwai.exe")
    binary_args = ["--script=main.py"]
    script_dir = os.path.abspath(os.path.dirname(__file__))
    binary_abs_path = os.path.join(script_dir, binary_path)

    scene_names = list(scene.defs.keys())

    print('automated.py for scenes', scene_names)

    ps = {}
    for i in range(len(scene_names)):
        scene_name = scene_names[i]
        dest_dir = os.path.join(directory, scene_name)

        change_scene(scene_name)

        for method in args.methods:
            change_method(method)

            # Launch Mogwai
            subprocess.run([binary_abs_path] + binary_args)

            if args.interactive:
                exit()

            if args.nopostprocessing:
                continue

            if  method == 'input':
                # Modulate
                postprocess_input(f'{OUT_DIR}/', scene_name)
                pass
            elif method == 'ref':
                postprocess_ref(f'{OUT_DIR}/', scene_name)

        # Move data directory
        if os.path.exists(OUT_DIR):
            print(f'Moving to {dest_dir}...', end=' ', flush=True)
            os.makedirs(dest_dir, exist_ok=True)
            # Copy files explicitly for overwriting
            for f in os.listdir(OUT_DIR):
                shutil.move(os.path.join(OUT_DIR, f), os.path.join(dest_dir, f))
        print('Done.')

        if args.nas:
            # Move to NAS asynchronously
            print('Moving to NAS...', end=' ', flush=True)
            nas_dir = f'F:/{directory}/{scene_name}'
            p = subprocess.Popen(['robocopy', dest_dir, nas_dir, '/MOVE', '/MT:12', '/R:10', '/W:10'], shell=True)
            ps[p.pid] = p

    print('Done.')

    exit()
