import os
import subprocess
import threading
import re
import shutil
import sys
import numpy as np
import time
import multiprocessing as mp
from functools import partial
import argparse
import glob

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

def process_input(src_dir, dest_dir, frame):
    # Extract depth from LinearZ
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

def postprocess_input(src_dir, scene_name, frames):
    print('Post-processing the input...', end=' ', flush=True)

    # Process multiprocessing
    num_workers = min(60, mp.cpu_count()) # 60 is maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process_input, [(src_dir, src_dir, frame) for frame in frames])
    pool.close()

    # Remove last frames, if does not exist, ignore it
    num_frames = scene.defs[scene_name]['anim'][1] - scene.defs[scene_name]['anim'][0] + 1
    if scene_name != "Dining-room-dynamic":
        for frame in range(frames[0] + num_frames, frames[0] + num_frames + 10):
            for f in os.listdir(src_dir):
                if f.endswith(f'{frame:04d}.exr'):
                    if os.path.exists(os.path.join(src_dir, f)):
                        os.remove(os.path.join(src_dir, f))

    print('Done')

def postprocess_ref(src_dir, scene_name, frames):
    pass

def process_multigbuf(src_dir, frame):
    img = exr.read_all(os.path.join(src_dir, f'normal_multi_{frame:04d}.exr'))['default']
    factor = np.linalg.norm(img, axis=2, keepdims=True)
    factor[factor == 0] = 1
    img /= factor
    exr.write(os.path.join(src_dir, f'normal_multi_{frame:04d}.exr'), img, compression=exr.ZIP_COMPRESSION)

def postprocess_multigbuf(src_dir, scene_name, frames):
    # Normalize normal_multi
    num_workers = min(60, mp.cpu_count()) # 60 is maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process_multigbuf, [(src_dir, frame) for frame in frames])
    pass

def postprocess(method, scene_name):
    src_dir = f'{OUT_DIR}/'
    # Find frames
    exr_list = os.listdir(src_dir)
    exr_list = [f for f in exr_list if f.endswith('.exr')]
    if len(exr_list) == 0:
        print('No exr files found. Skip.')
        return
    frames = sorted(list(set([int(f.split('.')[0].split('_')[-1]) for f in exr_list])))

    if  method == 'input':
        postprocess_input(src_dir, scene_name, frames)
    elif method == 'ref':
        postprocess_ref(src_dir, scene_name, frames)
    elif method == 'multigbuf':
        postprocess_multigbuf(src_dir, scene_name, frames)

def build(args):
    print('Building..', end=' ')
    if not args.nobuild or args.buildonly:
        sys.stdout.flush()
        ret = subprocess.run(['C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe', "Falcor.sln", "/p:Configuration=ReleaseD3D12", "/m:24", "/v:m"], capture_output=True, text=True)
        if ret.returncode != 0:
            print(ret.stdout)
            sys.exit(-1)
        print('Done.')
        if args.buildonly:
            print(ret.stdout)
            sys.exit(0)
    else:
        print('Skipped.')

def get_latest_log_file(log_directory, log_pattern, baseline=None):
    while True:
        log_files = glob.glob(os.path.join(log_directory, log_pattern))
        log_files.sort(key=os.path.getmtime, reverse=True)
        if log_files:
            latest_log_file = log_files[0]
            if baseline is None or os.path.getmtime(latest_log_file) > os.path.getmtime(baseline):
                return latest_log_file
        time.sleep(0.5)  # Adjust as needed

def monitor_log_file(log_file, stop_signal):
    print(f"Monitoring log file: {log_file}")
    with open(log_file, 'r') as file:
        file.seek(0, os.SEEK_END)  # Skip existing content
        try:
            while not stop_signal.is_set():
                line = file.readline()
                if not line:
                    time.sleep(0.5)  # Adjust as needed
                    continue
                print(line, end='')
        except KeyboardInterrupt:
            print("\nStopped monitoring the log file.")

def run(local=True, noscript=False):
    if local:
        # Call Mogwai
        binary_path = os.path.join("Bin", "x64", "Release", "Mogwai.exe")
        if noscript:
            binary_args = []
        else:
            binary_args = ["--script=main.py"]
        script_dir = os.path.abspath(os.path.dirname(__file__))
        binary_abs_path = os.path.join(script_dir, binary_path)
        print(f"Running {binary_abs_path} {' '.join(binary_args)}...", end=" ", flush=True)
        ret = subprocess.run([binary_abs_path] + binary_args, capture_output=True, text=True)
        if ret.returncode != 0:
            print(ret.stdout)
            sys.exit(-1)
        print('Done.')
    else:
        script_file = "main.py"
        binary_path = os.path.join("Bin", "x64", "Release", "Mogwai.exe")

        cwd = os.path.abspath(os.path.dirname(__file__))
        binary_args_path = os.path.join(cwd, script_file)
        binary_abs_path = os.path.join(cwd, binary_path)

        binary_command = f"psexec -i 1 {binary_abs_path} --script={binary_args_path}"

        ## Log monitoring

        log_directory = './Bin/x64/Release/'
        log_pattern = r'Mogwai.exe.*.log'

        # Determine the latest log file before starting the subprocess
        existing_latest_log = get_latest_log_file(log_directory, log_pattern)

        # Start the subprocess
        proc = subprocess.Popen(binary_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Determine the new log file created by this subprocess run
        new_log_file = get_latest_log_file(log_directory, log_pattern, baseline=existing_latest_log)

        stop_thread = threading.Event()
        # Start monitoring the new log file
        log_thread = threading.Thread(target=monitor_log_file, args=(new_log_file, stop_thread))
        log_thread.start()

        # Wait for the subprocess to complete
        proc.wait()

        # Signal the monitoring thread to stop
        stop_thread.set()
        log_thread.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated script for Mogwai')
    parser.add_argument('--nobuild', action='store_true', default=False)
    parser.add_argument('--buildonly', action='store_true', default=False)
    parser.add_argument('--nopostprocessing', action='store_true', default=False)
    parser.add_argument('--methods', nargs='+', default=[], choices=['input', 'crn', 'ref', 'svgf_optix', 'multigbuf'], required=False)
    parser.add_argument('--nas', action='store_true', default=False)
    parser.add_argument('--interactive', action='store_true', default=False)
    parser.add_argument('--dir', default='dataset')
    parser.add_argument('--mogwai', action='store_true', default=False)
    args = parser.parse_args()

    if args.mogwai:
        run(local=True, noscript=True)
        exit()

    # Update HOME_DIR
    HOME_DIR = os.path.abspath('../').replace('\\', '/')
    update_pyvariable("scene.py", "HOME_DIR", HOME_DIR)

    # Import scene after updating HOME_DIR
    import scene

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
        update_pyvariable("main.py", "REF_COUNT", 8192)
        # Create output directory
        os.makedirs(OUT_DIR, exist_ok=True)

    #########################################################
    # Call build in silent mode and check if it was successful
    build(args)

    directory = args.dir
    print(f'Generating at {directory}...')

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
            run()

            if args.interactive:
                exit()

            if not args.nopostprocessing:
                postprocess(method, scene_name)

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
