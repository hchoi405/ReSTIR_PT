import os
import subprocess
import queue
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
import config

class RobocopyManager:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self.process_queue)
        self.thread.daemon = True  # Ensures the thread exits when the main program does
        self.thread.start()

    def add_copy_job(self, source, destination):
        """Add a copy job to the queue."""
        self.queue.put((source, destination))

    def process_queue(self):
        """Process each item in the queue one at a time."""
        while True:
            source, destination = self.queue.get()
            print(f'Starting robocopy from {source} to {destination}')
            subprocess.run(['robocopy', source, destination, '/MOVE', '/MT:4', '/R:3', '/W:10'])
            print(f'Completed robocopy from {source} to {destination}')
            self.queue.task_done()

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

def postprocess_common(src_dir, scene_name, frames):
    # Remove last frames, if does not exist, ignore it
    num_frames = scene.defs[scene_name]['anim'][1] - scene.defs[scene_name]['anim'][0] + 1
    if scene_name != "Dining-room-dynamic":
        for frame in range(frames[0] + num_frames, frames[0] + num_frames + 10):
            for f in os.listdir(src_dir):
                if f.endswith(f'{frame:04d}.exr'):
                    if os.path.exists(os.path.join(src_dir, f)):
                        os.remove(os.path.join(src_dir, f))

def starts_with_number(filename):
    # This pattern matches any string that starts with exactly four digits
    pattern = r'^\d{4}'
    if re.match(pattern, filename):
        return True
    return False

def process_input(src_dir, dest_dir, frame, sample_idx, suffix=None):
    try:
        ### Post-process the indivisual images
        # # RGB to Z
        # names = ["visibility"]
        # for name in names:
        #     path = os.path.join(src_dir, f'{name}_{frame:04d}.exr')
        #     if os.path.exists(path):
        #         img = exr.read_all(path)['default']
        #         img = img[:,:,0:1]
        #         exr.write(os.path.join(dest_dir, f'{name}_{frame:04d}.exr'), img, compression=exr.ZIP_COMPRESSION)
        #     else:
        #         print(f'WARN: {path} not found.')

        # specRough and diffuseOpacity to roughness and opacity
        spec_path = os.path.join(src_dir, f'specRough_{frame:04d}.exr')
        if os.path.exists(spec_path):
            spec_img = exr.read_all(spec_path)['default']
            rough_img = spec_img[:,:,3:4]
            exr.write(os.path.join(dest_dir, f'roughness_{frame:04d}.exr'), rough_img, compression=exr.ZIP_COMPRESSION)
            exr.write(os.path.join(dest_dir, f'specularAlbedo_{frame:04d}.exr'), spec_img[:,:,0:3], compression=exr.ZIP_COMPRESSION)
            os.remove(os.path.join(src_dir, f'specRough_{frame:04d}.exr'))
        else:
            print(f'WARN: {spec_path} not found.')

        diffuseOpacity_path = os.path.join(src_dir, f'diffuseOpacity_{frame:04d}.exr')
        if os.path.exists(diffuseOpacity_path):
            diffuseOpacity_img = exr.read_all(diffuseOpacity_path)['default']
            diffuse_img = diffuseOpacity_img[:,:,0:3]
            opacity_img = diffuseOpacity_img[:,:,3:4]
            exr.write(os.path.join(dest_dir, f'diffuseAlbedo_{frame:04d}.exr'), diffuse_img, compression=exr.ZIP_COMPRESSION)
            exr.write(os.path.join(dest_dir, f'opacity_{frame:04d}.exr'), opacity_img, compression=exr.ZIP_COMPRESSION)
            os.remove(os.path.join(src_dir, f'diffuseOpacity_{frame:04d}.exr'))
        else:
            print(f'WARN: {diffuseOpacity_path} not found.')

        ### Post-process to handle multi-samples
        # Collect files of the currently rendered frame
        rendered_files = os.listdir(dest_dir)
        rendered_files = [f for f in rendered_files if f.endswith(f'{frame:04d}.exr')]
        rendered_files = [f for f in rendered_files if not starts_with_number(f)]

        # Handle suffix
        if suffix is None:
            pass
        else:
            for f in rendered_files:
                basename = f.split('_')[0]
                newname = f'{basename}{suffix}_{frame:04d}.exr'
                shutil.move(os.path.join(dest_dir, f), os.path.join(dest_dir, newname))

        # Re-collect files of the currently rendered frame
        rendered_files = os.listdir(dest_dir)
        rendered_files = [f for f in rendered_files if f.endswith(f'{frame:04d}.exr')]
        rendered_files = [f for f in rendered_files if not starts_with_number(f)]

        # Find the largest sample index from {sample_idx:04d}_*.exr
        if sample_idx == 0:
            # Just move
            for f in rendered_files:
                shutil.move(os.path.join(dest_dir, f), os.path.join(dest_dir, f'{sample_idx:04d}_{f}'))
        else:
            last_sample_idx = sample_idx - 1
            # Average the images
            for f in rendered_files:
                if 'mvec' in f: # Do not average motion vectors
                    continue
                img_avg = exr.read_all(os.path.join(dest_dir, f'{last_sample_idx:04d}_{f}'))['default']
                img = exr.read_all(os.path.join(dest_dir, f))['default']
                new_avg = ((last_sample_idx+1) * img_avg + img) / ((last_sample_idx+1) + 1)
                if 'normal' in f: # Normalize normals
                    factor = np.linalg.norm(new_avg, axis=2, keepdims=True)
                    factor[factor == 0] = 1
                    new_avg /= factor
                exr.write(os.path.join(dest_dir, f'{sample_idx:04d}_{f}'), new_avg, compression=exr.ZIP_COMPRESSION)
                os.remove(os.path.join(dest_dir, f))
                os.remove(os.path.join(dest_dir, f'{last_sample_idx:04d}_{f}'))

    except Exception as e:
        func_name = sys._getframe()
        print(f"[{func_name}] Error processing frame {frame}: {str(e)}")

def postprocess_input(src_dir, scene_name, frames, sample_idx, suffix=None):
    print('\tPost-processing the input...', end=' ', flush=True)

    # Process multiprocessing
    num_workers = min(60, mp.cpu_count() - 4) # 60 is maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process_input, [(src_dir, src_dir, frame, sample_idx, suffix) for frame in frames])
    pool.close()

    print('Done')

def postprocess_ref(src_dir, scene_name, frames):
    pass

def process_restirref_frame(name, frame, idx, tmp_dir):
    try:
        last_idx = max(config.REF_START_SAMPLE_INDEX, idx - 1)

        rendered_path = os.path.join(tmp_dir, f'{name}_{frame:04d}_{idx:04d}.exr')
        prev_ref_path = os.path.join(tmp_dir, f'ref_{name}_{frame:04d}_{last_idx:04d}.exr')
        new_ref_path = os.path.join(tmp_dir, f'ref_{name}_{frame:04d}_{idx:04d}.exr')

        if idx == config.REF_START_SAMPLE_INDEX:
            shutil.move(rendered_path, new_ref_path)
        else:
            num_prev = last_idx - config.REF_START_SAMPLE_INDEX + 1
            img_prev = exr.read_all(prev_ref_path)['default']
            img = exr.read_all(rendered_path)['default']
            new_avg = (num_prev * img_prev + img) / (num_prev + 1)
            exr.write(new_ref_path, new_avg, compression=exr.ZIP_COMPRESSION)
            # Remove
            os.remove(rendered_path)
            os.remove(prev_ref_path)

    except Exception as e:
        func_name = sys._getframe()
        print(f"[{func_name}] Error processing frame {frame}: {str(e)}")

def process_refrestir_frame_last(name, frame, idx, src_dir):
    try:
        tmp_dir = os.path.join(src_dir, 'tmp')
        ref_path = os.path.join(tmp_dir, f'ref_{name}_{frame:04d}_{idx:04d}.exr')
        if os.path.exists(ref_path):
            path = os.path.join(tmp_dir, f'ref_{name}_{frame:04d}_{idx:04d}.exr')
            new_path = os.path.join(src_dir, f'ref_{name}_{frame:04d}.exr')
            shutil.move(path, new_path)
        else:
            print(f'ERROR: ref file not found {ref_path}')
    except Exception as e:
        func_name = sys._getframe()
        print(f"[{func_name}] Error processing frame {frame}: {str(e)}")

reflist = ['current', 'envLight', 'emissive']
def postprocess_refrestir(src_dir, scene_name, frames, idx):
    # Create tmp directory
    tmp_dir = os.path.join(src_dir, 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)

    # Move the images in src_dir to the tmp_dir with appending the index
    exr_list = os.listdir(src_dir)
    exr_list = [f for f in exr_list if f.endswith('.exr')]
    exr_list = [f for f in exr_list if any([f.startswith(f'{name}_') for name in reflist])]
    if len(exr_list) == 0:
        print('ERROR2: No exr files found.')
        return
    for f in exr_list:
        shutil.move(os.path.join(src_dir, f), os.path.join(tmp_dir, f'{f.split(".")[0]}_{idx:04d}.exr'))

    # Process multiprocessing
    num_workers = min(60, mp.cpu_count() - 4) # 60 is maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        for name in reflist:
            pool.starmap(partial(process_restirref_frame, name), [(frame, idx, tmp_dir) for frame in frames])

    # # Last sample processing
    # if idx == config.REF_SAMPLES_PER_PIXEL - 1:
    #     with mp.Pool(processes=num_workers) as pool:
    #         for name in reflist:
    #             pool.starmap(partial(process_refrestir_frame_last, name), [(frame, idx, src_dir) for frame in frames])
    #     # Remove tmp
    #     shutil.rmtree(tmp_dir)

def process_centergbuf(frame, src_dir, dest_dir):
    # Extract depth from LinearZ
    try:
        linearz_path = os.path.join(src_dir, f'linearZ_{frame:04d}.exr')
        if os.path.exists(linearz_path):
            linearz_img = exr.read_all(linearz_path)['default']
            depth_img = linearz_img[:,:,0:1]
            exr.write(os.path.join(dest_dir, f'depth_{frame:04d}.exr'), depth_img, compression=exr.ZIP_COMPRESSION)
        else:
            print(f'WARN: {linearz_path} not found.')
    except Exception as e:
        func_name = sys._getframe()
        print(f"[{func_name}] Error processing frame {frame}: {str(e)}")

def postprocess_centergbuf(src_dir, scene_name, frames):
    print('\tPost-processing the centergbuf...', end=' ', flush=True)

    # Process multiprocessing
    num_workers = min(60, mp.cpu_count() - 4) # 60 is maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process_centergbuf, [(frame, src_dir, src_dir) for frame in frames])
    pool.close()

    print('Done')

def process_multigbuf(src_dir, frame):
    try:
        # Extract depth from LinearZ
        linearz_path = os.path.join(src_dir, f'linearZ_multi_{frame:04d}.exr')
        if os.path.exists(linearz_path):
            linearz_img = exr.read_all(linearz_path)['default']
            depth_img = linearz_img[:,:,0:1]
            exr.write(os.path.join(src_dir, f'depth_multi_{frame:04d}.exr'), depth_img, compression=exr.ZIP_COMPRESSION)
            # remove linearZ
            os.remove(linearz_path)
        else:
            print(f'WARN: {linearz_path} not found.')

        # Normalize normal_multi
        img = exr.read_all(os.path.join(src_dir, f'normal_multi_{frame:04d}.exr'))['default']
        factor = np.linalg.norm(img, axis=2, keepdims=True)
        factor[factor == 0] = 1
        img /= factor
        exr.write(os.path.join(src_dir, f'normal_multi_{frame:04d}.exr'), img, compression=exr.ZIP_COMPRESSION)

    except Exception as e:
        func_name = sys._getframe()
        print(f"[{func_name}] Error processing frame {frame}: {str(e)}")

def postprocess_multigbuf(src_dir, scene_name, frames):
    print('\tPost-processing the multigbuf...', end=' ', flush=True)
    # Normalize normal_multi
    num_workers = min(60, mp.cpu_count()) # 60 is maximum for Windows
    with mp.Pool(processes=num_workers) as pool:
        pool.starmap(process_multigbuf, [(src_dir, frame) for frame in frames])
    print('Done.')

def postprocess(method, scene_name, sample_idx=0):
    src_dir = f'{OUT_DIR}/'
    # Find frames
    exr_list = os.listdir(src_dir)
    exr_list = [f for f in exr_list if f.endswith('.exr')]
    if len(exr_list) == 0:
        print('No exr files found. Skip.')
        return
    frames = sorted(list(set([int(f.split('.')[0].split('_')[-1]) for f in exr_list])))

    if method == 'input':
        postprocess_input(src_dir, scene_name, frames, sample_idx)
    elif method == 'secondinput':
        postprocess_input(src_dir, scene_name, frames, sample_idx, suffix='2')
    elif method == 'ref':
        postprocess_ref(src_dir, scene_name, frames)
    elif method == 'ref_restir':
        postprocess_refrestir(src_dir, scene_name, frames, sample_idx)
    elif method == 'centergbuf':
        postprocess_centergbuf(src_dir, scene_name, frames)
    elif method == 'multigbuf':
        postprocess_multigbuf(src_dir, scene_name, frames)
    else:
        print(f'Post-processing for {method} is not implemented.')

    if method == 'input' or method == 'secondinput':
        if sample_idx == config.SAMPLES_PER_PIXEL - 1:
            postprocess_common(src_dir, scene_name, frames)
    else:
        postprocess_common(src_dir, scene_name, frames)

def build(args):
    print('Building..', end=' ')
    if not args.nobuild or args.buildonly:
        sys.stdout.flush()
        bin_2019 = 'C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/MSBuild/Current/Bin/MSBuild.exe'
        bin_2022 = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
        if not os.path.exists(bin_2022):
            ret = subprocess.run([bin_2019, "Falcor.sln", "/p:Configuration=ReleaseD3D12", "/m:24", "/v:m"], capture_output=True, text=True)
        else:
            ret = subprocess.run([bin_2022, "Falcor.sln", "/p:Configuration=ReleaseD3D12", "/m:24", "/v:m"], capture_output=True, text=True)
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

def run(noscript=False):
    # Call Mogwai
    binary_path = os.path.join("Bin", "x64", "Release", "Mogwai.exe")
    if noscript:
        binary_args = []
    else:
        binary_args = ["--script=main.py"]
    script_dir = os.path.abspath(os.path.dirname(__file__))
    binary_abs_path = os.path.join(script_dir, binary_path)
    ret = subprocess.run([binary_abs_path] + binary_args, capture_output=True, text=True)
    # ret = subprocess.run([binary_abs_path] + binary_args)
    if ret.returncode != 0:
        return -1, ret.stdout
    return 0, ret.stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated script for Mogwai')
    parser.add_argument('--nobuild', action='store_true', default=False)
    parser.add_argument('--buildonly', action='store_true', default=False)
    parser.add_argument('--nopostprocessing', action='store_true', default=False)
    parser.add_argument('--methods', nargs='+', default=[], choices=['input', 'ref', 'ref_restir', 'secondinput', 'centergbuf', 'multigbuf'], required=False)
    parser.add_argument('--nas', action='store_true', default=False)
    parser.add_argument('--interactive', action='store_true', default=False)
    parser.add_argument('--dir', default='dataset')
    parser.add_argument('--mogwai', action='store_true', default=False)
    args = parser.parse_args()

    if args.mogwai:
        run(noscript=True)
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
        # update_pyvariable("main.py", "SAMPLES_PER_PIXEL", 1)
    else:
        update_pyvariable("main.py", "INTERACTIVE", False)
        update_pyvariable("main.py", "OUT_DIR", OUT_DIR)
        update_pyvariable("main.py", "REF_COUNT", 8192)
        # update_pyvariable("main.py", "SAMPLES_PER_PIXEL", 2)
        # Create output directory
        os.makedirs(OUT_DIR, exist_ok=True)

    #########################################################
    # Call build in silent mode and check if it was successful
    build(args)

    directory = args.dir
    print(f'Generating at {directory}...')

    scene_names = list(scene.defs.keys())

    print('automated.py for scenes', scene_names)


    manager = RobocopyManager()
    for i in range(len(scene_names)):
        scene_name = scene_names[i]
        dest_dir = os.path.join(directory, scene_name)

        change_scene(scene_name)

        for method in args.methods:
            change_method(method)

            update_pyvariable("main.py", "SEED_OFFSET", 0)

            if method == 'ref_restir':
                sample_idx = config.REF_START_SAMPLE_INDEX

                tmp_dir = os.path.join(OUT_DIR, 'tmp')
                if not os.path.exists(tmp_dir):
                    # Create tmp directory if not exist
                    os.makedirs(tmp_dir, exist_ok=True)
                else:
                    # Or check the minimum sample_idx to restart with
                    exr_list = os.listdir(tmp_dir)
                    exr_list = [f for f in exr_list if f.endswith('.exr')]
                    exr_list = [f for f in exr_list if f.startswith('ref_')]
                    # Check all reflist files exist for all frames
                    len_anim = scene.defs[scene_name]['anim'][1] - scene.defs[scene_name]['anim'][0] + 1
                    fulllen = (len_anim + 1) * len(reflist) # +1 for the dummy frame
                    if len(exr_list) != fulllen:
                        print(f'No complete ref files found: (actual {len(exr_list)} != expected {fulllen}). Restarting from {config.REF_START_SAMPLE_INDEX}...')
                    else:
                        min_idx = min([int(f.split('_')[-1].split('.')[0]) for f in exr_list])
                        if min_idx >= config.REF_START_SAMPLE_INDEX and min_idx < config.REF_SAMPLES_PER_PIXEL:
                            # Force rename to min_idx
                            def rreplace(s, old, new, occurrence):
                                li = s.rsplit(old, occurrence)
                                return new.join(li)

                            for f in exr_list:
                                newname = rreplace(f, f.split('.')[0].split("_")[-1], f'{min_idx:04d}', 1)
                                os.rename(os.path.join(tmp_dir, f), os.path.join(tmp_dir, newname))

                            sample_idx = min_idx + 1
                            print(f'Restarting from {sample_idx}...')

                while sample_idx < config.REF_SAMPLES_PER_PIXEL:
                    update_pyvariable("main.py", "SEED_OFFSET", sample_idx)
                    print(f'Sample idx {sample_idx}:', end=' ', flush=True)
                    retcode, stdout = run()
                    if retcode != 0:
                        print('Unsucessful, retry')
                    else:
                        postprocess(method, scene_name, sample_idx)
                        print('Done.')
                        sample_idx += 1

            elif method == 'input' or method == 'secondinput':
                # Launch Mogwai
                for sample_idx in range(config.SAMPLES_PER_PIXEL):
                    update_pyvariable("main.py", "SAMPLE_INDEX", sample_idx)
                    if method == 'input':
                        update_pyvariable("main.py", "SEED_OFFSET", sample_idx)
                    else:
                        update_pyvariable("main.py", "SEED_OFFSET", sample_idx + 1000000)
                        # update_pyvariable("main.py", "SEED_OFFSET", sample_idx)
                    print(f'Rendering Sample idx {sample_idx}...', end='', flush=True)
                    retcode, stdout = run()
                    if retcode != 0:
                        print(stdout)
                    print('Done.')

                    if not args.nopostprocessing:
                        postprocess(method, scene_name, sample_idx)
            else:
                print(f'Rendering...', end='', flush=True)
                run()
                print('Done.')
                if not args.nopostprocessing:
                    postprocess(method, scene_name, 0)

            if args.interactive:
                exit()

        # Move data directory
        if os.path.exists(OUT_DIR):
            print(f'Moving to {dest_dir}...', end=' ', flush=True)
            os.makedirs(dest_dir, exist_ok=True)
            # Copy files explicitly for overwriting
            for f in os.listdir(OUT_DIR):
                shutil.move(os.path.join(OUT_DIR, f), os.path.join(dest_dir, f))

        if args.nas:
            # Move to NAS asynchronously
            print('Moving to NAS...', end=' ', flush=True)
            nas_dir = f'F:/{directory}/{scene_name}'
            manager.add_copy_job(dest_dir, nas_dir)

    print('Done.')

    exit()
