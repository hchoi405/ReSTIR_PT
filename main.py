# type: ignore
import random

OUT_DIR = "C:/Users/hchoi/repositories/ReSTIR_PT/output"

INTERACTIVE = False

NAME = "staircase"
FILE = "C:/Users/hchoi/repositories/ReSTIR_PT/fbxscenes/staircase/staircase.pyscene"
ANIM = [0, 2]
METHOD = "secondinput"
REF_COUNT = 8192
ENABLE_RESTIR = True
SEED_OFFSET = 0
SAMPLE_INDEX = 0
MULTIGBUF_COUNT = 4
INPUT_SUFFIX = ""
DUMMY_RUN = False

def frange(start, stop=None, step=None):
    # if set start=0.0 and step = 1.0 if not specified
    start = float(start)
    if stop == None:
        stop = start + 0.0
        start = 0.0
    if step == None:
        step = 1.0

    print("start = ", start, "stop = ", stop, "step = ", step)

    count = 0
    while True:
        temp = float(start + count * step)
        if step > 0 and temp >= stop:
            break
        elif step < 0 and temp <= stop:
            break
        yield temp
        count += 1


def add_path(g, gbuf, enable_restir=True, crn=False, path_seed_offset=0):
    if DUMMY_RUN:
        return "dummy", "dummy"

    loadRenderPassLibrary("ReSTIRPTPass.dll")
    loadRenderPassLibrary("ScreenSpaceReSTIRPass.dll")

    # Toggle between ReSTIRPT and MegakernelPathTracer
    if enable_restir:
        PathTracer = createPass("ReSTIRPTPass", {
            'samplesPerPixel': 1,
            # 'syncSeedSSReSTIR': True if crn else False,
            'fixSpatialSeed': True if crn else False,
            'temporalSeedOffset': (1000000 if crn else 0) + path_seed_offset,
        })
        path = "ReSTIRPT"
        ScreenSpaceReSTIRPass = createPass("ScreenSpaceReSTIRPass", {
            'NumReSTIRInstances': 1,
            'options':ScreenSpaceReSTIROptions(
                fixSpatialSeed=True if crn else False,
                temporalSeedOffset=(1000000 if crn else 0) + path_seed_offset
            )
        })
        screenReSTIR = "ScreenSpaceReSTIR"
    else:
        if crn:
            print("ERROR: CRN for PathTracing is not supported.")
            exit()
        PathTracer = createPass("ReSTIRPTPass", {
            'samplesPerPixel': 1,
            'pathSamplingMode': PathSamplingMode.PathTracing,
            'temporalSeedOffset': path_seed_offset,
        })
        path = "ReSTIRPT"
        ScreenSpaceReSTIRPass = createPass("ScreenSpaceReSTIRPass", {
            'options':ScreenSpaceReSTIROptions(
                useTemporalResampling=False, useSpatialResampling=False,
                temporalSeedOffset=path_seed_offset
            )
        })
        screenReSTIR = "ScreenSpaceReSTIR"

        # PathTracer = createPass("MegakernelPathTracer", {'samplesPerPixel': 1})
        # path = "PathTracer"
        # screenReSTIR = ""

    g.addPass(PathTracer, path)
    g.addPass(ScreenSpaceReSTIRPass, screenReSTIR)

    g.addEdge(f"{gbuf}.vbuffer", f"{path}.vbuffer")
    # if enable_restir:
    if True:
        g.addEdge(f"{gbuf}.mvec", f"{path}.motionVectors")
        g.addEdge(f"{gbuf}.vbuffer", f"{screenReSTIR}.vbuffer")
        g.addEdge(f"{gbuf}.mvec", f"{screenReSTIR}.motionVectors")
        g.addEdge(f"{screenReSTIR}.color", f"{path}.directLighting")

    return path, screenReSTIR


def add_gbuffer(g, pattern, init_seed=1):
    if DUMMY_RUN:
        return "dummy"

    loadRenderPassLibrary("GBuffer.dll")

    sample_pattern = SamplePattern.Center
    if pattern == 'Uniform':
        sample_pattern = SamplePattern.Uniform
    elif pattern == 'CenterUniform':
        sample_pattern = SamplePattern.CenterUniform
    elif pattern == 'Center':
        sample_pattern = SamplePattern.Center
    elif pattern == 'Halton':
        sample_pattern = SamplePattern.Halton
    else:
        print("ERROR: Invalid sample pattern.")
        exit()

    dicts = {
        'samplePattern': sample_pattern,
        # sampleCount becomes a seed when used for [Uniform, UniformRandom, CRN] patterns
        # Uniform is for GBufferRaster, UniformRandom is only for GBufferRT (do not use UniformRandom for GBufferRaster)
        'sampleCount': init_seed,
        'sampleIndex': SAMPLE_INDEX,
        'useAlphaTest': True,
    }
    GBufferRaster = createPass("GBufferRaster", dicts)
    gbuf = "GBufferRaster"
    g.addPass(GBufferRaster, gbuf)
    return gbuf


def add_fileload(g):
    if DUMMY_RUN:
        return "dummy"

    loadRenderPassLibrary("FileloadPass.dll")

    # key:value = filename:channelName
    channels = {
        'current': 'color',
        'albedo': 'albedo',
        'normal': 'normW',
        'mvec': 'mvec',
        'emissive': 'emissive',
        'depth': 'linearZ',
        'position': 'posW',
        'pnFwidth': 'pnFwidth',
    }
    input_dir = OUT_DIR
    FileloadPassGbuf = createPass("FileloadPass", {
        'directory': input_dir,
        'filenames': list(channels.keys()),
        'channalNames': list(channels.values()),
        'startFrame': 0,
    })
    gbuffile = "GbufFileloadPass"
    g.addPass(FileloadPassGbuf, gbuffile)

    FileloadPassPath = createPass("FileloadPass", {
        'directory': input_dir,
        'filenames': list(channels.keys()),
        'channalNames': list(channels.values()),
        'startFrame': 0,
    })
    pathfile = "PathFileloadPass"
    g.addPass(FileloadPassPath, pathfile)

    return gbuffile, pathfile


def add_capture(g, pairs, start, end, opts=None):
    if DUMMY_RUN:
        import scripts.exr as exr
        import numpy as np
        import shutil
        for frame in range(start, end+1):
            key_first = list(pairs.keys())[0]
            exr.write(f"{OUT_DIR}/{key_first}_{frame:04d}.exr", np.ones((1080, 1920, 4), dtype=np.float32) * (SAMPLE_INDEX+1))
            for key in list(pairs.keys())[1:]:
                print('Generating dummy exr:', f"{OUT_DIR}/{key}_{frame:04d}.exr")
                shutil.copyfile(f"{OUT_DIR}/{key_first}_{frame:04d}.exr", f"{OUT_DIR}/{key}_{frame:04d}.exr")
        return "dummy_capture"

    loadRenderPassLibrary("CapturePass.dll")

    channels = list(pairs.keys())
    inputs = list(pairs.values())

    options = {
        'directory': OUT_DIR,
        'channels': channels,
        'exitAtEnd': True,
        'accumulate': False,
        'writeStart': 0,    # Control frame number in below
        'writeEnd': 10000,  # Control frame number in below
        'captureCameraMat': False,
        'includeAlpha': ["specRough", "diffuseOpacity", "specRough2", "diffuseOpacity2"],
    }
    if opts is not None:
        options.update(opts)
    CapturePass = createPass("CapturePass", options)

    capture = "CapturePass"
    g.addPass(CapturePass, capture)

    def addEdgeOutput(input, channel):
        g.addEdge(input, f"{capture}.{channel}")
        g.markOutput(f"{capture}.{channel}")

    for input, channel in zip(inputs, channels):
        addEdgeOutput(input, channel)

    return capture


def render_ref(start, end):
    g = None

    if not DUMMY_RUN:
        loadRenderPassLibrary("AccumulatePass.dll")

        g = RenderGraph("PathGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Uniform)
    path, _ = add_path(g, gbuf, False)

    if not DUMMY_RUN:
        AccumulatePass1 = createPass("AccumulatePass", {'enabled': True})
        AccumulatePass2 = createPass("AccumulatePass", {'enabled': True})
        AccumulatePass3 = createPass("AccumulatePass", {'enabled': True})

        # Add pass
        g.addPass(AccumulatePass1, "AccumulatePass1")
        g.addPass(AccumulatePass2, "AccumulatePass2")
        g.addPass(AccumulatePass3, "AccumulatePass3")

        g.addEdge(f"{path}.color", "AccumulatePass1.input")
        g.addEdge(f"{path}.envLight", "AccumulatePass2.input")
        g.addEdge(f"{gbuf}.emissive", "AccumulatePass3.input")

        g.markOutput(f"{path}.color")

    pairs = {
        'ref': f'AccumulatePass1.output',
        'ref_envLight': f'AccumulatePass2.output',
        'ref_emissive': f'AccumulatePass3.output'
    }
    opts = {
        'accumulate': True,
        'accumulateCount': REF_COUNT,
    }

    add_capture(g, pairs, start, end, opts)

    return g


def render_input(start, end, sample_pattern='Uniform', gbufseed=0, pathseed=0):
    g = None
    if not DUMMY_RUN:
        g = RenderGraph("MutlipleGraph")

    ## GBufferRaster
    gbuf = add_gbuffer(g, pattern=sample_pattern, init_seed=gbufseed)

    ## PathTracer
    path, ss_restir = add_path(g, gbuf, enable_restir=ENABLE_RESTIR, crn=False, path_seed_offset=pathseed)

    # Add output
    if not DUMMY_RUN:
        g.markOutput(f"{path}.color")

    # Connect input/output
    pairs = {
        ## PathTracer
        f'color{INPUT_SUFFIX}': f"{path}.color",
        # f'temporal{INPUT_SUFFIX}': f"{path}.temporalColor",
        f'envLight{INPUT_SUFFIX}': f"{path}.envLight",
        # f'albedo{INPUT_SUFFIX}': f"{path}.albedo",
        f'directDiffuseIllumination{INPUT_SUFFIX}': f'{ss_restir}.diffuseIllumination',
        f'directDiffuseReflectance{INPUT_SUFFIX}': f'{ss_restir}.diffuseReflectance',
        f'directSpecularIllumination{INPUT_SUFFIX}': f'{ss_restir}.specularIllumination',
        f'directSpecularReflectance{INPUT_SUFFIX}': f'{ss_restir}.specularReflectance',
    }

    # Store motion vector only for center (first sample)
    if METHOD == 'input' and SAMPLE_INDEX == 0:
        pairs.update({
            f'mvec{INPUT_SUFFIX}': f"{gbuf}.mvec"
        })

    ## Save G-buffer only for input, not secondinput (center)
    # if METHOD == 'input':
    ## Save G-buffer for all methods (jittered)
    if True:
        pairs.update({
            ## GBufferRaster
            f'albedo{INPUT_SUFFIX}': f"{gbuf}.texC", # modified in GBufferRaster.3d.slang
            f'normal{INPUT_SUFFIX}': f"{gbuf}.normW",
            f'position{INPUT_SUFFIX}': f"{gbuf}.posW",
            f'emissive{INPUT_SUFFIX}': f"{gbuf}.emissive",
            f'linearZ{INPUT_SUFFIX}': f"{gbuf}.linearZ",
            f'pnFwidth{INPUT_SUFFIX}': f"{gbuf}.pnFwidth",
            f'specRough{INPUT_SUFFIX}': f"{gbuf}.specRough",
            f'diffuseOpacity{INPUT_SUFFIX}': f"{gbuf}.diffuseOpacity",
        })
        # For NRD
        pairs.update({f'normWRoughnessMaterialID{INPUT_SUFFIX}': f'{gbuf}.normWRoughnessMaterialID'})
        # NRD
        pairs.update({
            f'nrdDiffuseRadianceHitDist{INPUT_SUFFIX}': f'{path}.nrdDiffuseRadianceHitDist',
            f'nrdSpecularRadianceHitDist{INPUT_SUFFIX}': f'{path}.nrdSpecularRadianceHitDist',
            f'nrdResidualRadianceHitDist{INPUT_SUFFIX}': f'{path}.nrdResidualRadianceHitDist',
            f'nrdEmission{INPUT_SUFFIX}': f'{path}.nrdEmission',
            f'nrdDiffuseReflectance{INPUT_SUFFIX}': f'{path}.nrdDiffuseReflectance',
            f'nrdSpecularReflectance{INPUT_SUFFIX}': f'{path}.nrdSpecularReflectance',

            f'nrdDeltaReflectionRadianceHitDist{INPUT_SUFFIX}': f'{path}.nrdDeltaReflectionRadianceHitDist',
            f'nrdDeltaReflectionReflectance{INPUT_SUFFIX}': f'{path}.nrdDeltaReflectionReflectance',
            f'nrdDeltaReflectionEmission{INPUT_SUFFIX}': f'{path}.nrdDeltaReflectionEmission',
            f'nrdDeltaReflectionHitDist{INPUT_SUFFIX}': f'{path}.nrdDeltaReflectionHitDist',
            f'nrdDeltaReflectionPathLength{INPUT_SUFFIX}': f'{path}.nrdDeltaReflectionPathLength',
            f'nrdDeltaReflectionNormWRoughMaterialID{INPUT_SUFFIX}': f'{path}.nrdDeltaReflectionNormWRoughMaterialID',

            f'nrdDeltaTransmissionRadianceHitDist{INPUT_SUFFIX}': f'{path}.nrdDeltaTransmissionRadianceHitDist',
            f'nrdDeltaTransmissionReflectance{INPUT_SUFFIX}': f'{path}.nrdDeltaTransmissionReflectance',
            f'nrdDeltaTransmissionEmission{INPUT_SUFFIX}': f'{path}.nrdDeltaTransmissionEmission',
            f'nrdDeltaTransmissionPosW{INPUT_SUFFIX}': f'{path}.nrdDeltaTransmissionPosW',
            f'nrdDeltaTransmissionPathLength{INPUT_SUFFIX}': f'{path}.nrdDeltaTransmissionPathLength',
            f'nrdDeltaTransmissionNormWRoughMaterialID{INPUT_SUFFIX}': f'{path}.nrdDeltaTransmissionNormWRoughMaterialID',
        })

    if ENABLE_RESTIR:
        pairs.update({
            f'direct{INPUT_SUFFIX}': f"{ss_restir}.color",
            # 'directTemporal': f"{ss_restir}.temporalColor",
        })
        pass

    opts = {
        'captureCameraMat': True if METHOD == 'input' else False,
        'captureCameraMatOnly': False,
        'includeAlpha': [
            "specRough", "diffuseOpacity", "specRough2", "diffuseOpacity2",
            "normWRoughnessMaterialID", "normWRoughnessMaterialID2",
            "nrdDiffuseRadianceHitDist", "nrdDiffuseRadianceHitDist2",
            "nrdSpecularRadianceHitDist", "nrdSpecularRadianceHitDist2",
            "nrdDeltaReflectionRadianceHitDist", "nrdDeltaReflectionRadianceHitDist2",
            "nrdDeltaTransmissionRadianceHitDist", "nrdDeltaTransmissionRadianceHitDist2",
            "nrdResidualRadianceHitDist", "nrdResidualRadianceHitDist2",
        ],
    }

    if not INTERACTIVE:
        add_capture(g, pairs, start, end, opts)

    return g


def render_ref_restir(start, end):
    g = None
    if not DUMMY_RUN:
        g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, pattern="Uniform", init_seed=SEED_OFFSET)
    path, ss_restir = add_path(g, gbuf, enable_restir=ENABLE_RESTIR, crn=False, path_seed_offset=SEED_OFFSET)

    if not DUMMY_RUN:
        # Add output
        g.markOutput(f"{path}.color")

    # Connect input/output
    pairs = {
        ## PathTracer
        'current': f"{path}.color",
        'envLight': f"{path}.envLight",

        ## GBufferRaster
        'emissive': f"{gbuf}.emissive",
    }
    opts = {
        'captureCameraMat': False
    }
    if not INTERACTIVE:
        add_capture(g, pairs, start, end, opts)

    return g

def render_centergbuf(start, end):
    g = None
    if not DUMMY_RUN:
        g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Center)

    if not DUMMY_RUN:
        # Add output
        g.markOutput(f"{gbuf}.linearZ")

    # Connect input/output
    pairs = {
        ## GBufferRaster
        'mvec': f"{gbuf}.mvec",
        'pnFwidth': f"{gbuf}.pnFwidth",
        'linearZ': f"{gbuf}.linearZ",
    }
    if not INTERACTIVE:
        add_capture(g, pairs, start, end, {'captureCameraMat': False})

    return g

def render_multigbuf(start, end):
    g = None
    if not DUMMY_RUN:
        loadRenderPassLibrary("AccumulatePass.dll")

        g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Halton, init_seed=MULTIGBUF_COUNT)

    if not DUMMY_RUN:
        # Add output
        g.markOutput(f"{gbuf}.diffuseOpacity")

    # Connect input/output
    pairs = {
        'emissive_multi': f"{gbuf}.emissive",
        'normal_multi': f"{gbuf}.normW",
        'position_multi': f"{gbuf}.posW",
        'albedo_multi': f"{gbuf}.texC", # modified in GBufferRaster.3d.slang
        'specRough_multi': f"{gbuf}.specRough",
        'diffuseOpacity_multi': f"{gbuf}.diffuseOpacity",
        'linearZ_multi': f"{gbuf}.linearZ",
        # 'pnFwidth': f"{gbuf}.pnFwidth",
        # 'mvec': f"{gbuf}.mvec",
    }

    capture_pairs = {}
    for i, (key, value) in enumerate(pairs.items()):
        AccumulatePass = createPass("AccumulatePass", {'enabled': True})
        g.addPass(AccumulatePass, f"AccumulatePass{i}")
        g.addEdge(value, f"AccumulatePass{i}.input")

        capture_pairs[key] = f"AccumulatePass{i}.output"

    add_capture(g, capture_pairs, start, end, {'accumulate': True, 'accumulateCount': MULTIGBUF_COUNT})

    return g



if 'Dining-room-dynamic-static' == NAME:
    start = -0.5
    end = -0.5
    step = 0
    num_frames = 101
    ANIM = [0, num_frames]
    dir_list = [start] * num_frames
elif 'Dining-room-dynamic' in NAME:
    # Dynamic directional light for dining-room
    # [-0.6, -0.0]
    start = -0.1
    end = -0.8
    step = -0.003
    num_frames = int((end - start) / step)
    ANIM = [0, num_frames]
    dir_list = frange(start, end, step)


print("ANIM = ", ANIM)
if METHOD == 'input':
    graph = render_input(*ANIM, sample_pattern='CenterUniform', gbufseed=SEED_OFFSET, pathseed=SEED_OFFSET)
    # graph = render_input(*ANIM, sample_pattern='CenterUniform', gbufseed=SEED_OFFSET, pathseed=SEED_OFFSET)
elif METHOD == 'secondinput':
    graph = render_input(*ANIM, sample_pattern='CenterUniform', gbufseed=SEED_OFFSET, pathseed=SEED_OFFSET)
    # graph = render_input(*ANIM, sample_pattern='Uniform', gbufseed=SEED_OFFSET, pathseed=SEED_OFFSET)
elif METHOD == 'ref':
    graph = render_ref(*ANIM)
elif METHOD == 'ref_restir':
    graph = render_ref_restir(*ANIM)
elif METHOD == 'centergbuf':
    graph = render_centergbuf(*ANIM)
elif METHOD == 'multigbuf':
    graph = render_multigbuf(*ANIM)

if not DUMMY_RUN:
    m.addGraph(graph)
    m.loadScene(FILE, buildFlags=SceneBuilderFlags.UseCache)
    # m.loadScene(FILE, buildFlags=SceneBuilderFlags.RebuildCache)
    # Call this after scene loading
    m.scene.camera.nearPlane = 0.15 # Increase near plane to prevent Z-fighting

    m.clock.framerate = 60
    m.clock.time = 0
    if INTERACTIVE:
        m.clock.pause()
        m.clock.frame = ANIM[0]
    else:
        m.clock.pause()

        # m.profiler.enabled = True
        if 'Dining-room-dynamic' in NAME:
            frame = 0
            for y in dir_list:
                m.clock.frame = frame
                print('Rendering frame:', m.clock.frame)
                m.scene.lights[0].direction.y = y
                if METHOD == 'ref':
                    for _ in range(REF_COUNT):
                        m.renderFrame()
                else:
                    m.renderFrame()
                frame += 1
                if frame == ANIM[1] + 1: break
        else:
            num_frames = ANIM[1] - ANIM[0] + 1

            # Start frame
            for frame in range(num_frames):
                m.clock.frame = ANIM[0] + frame
                print('Rendering frame:', m.clock.frame)
                # if frame == ANIM[0] + 10:
                #     m.profiler.startCapture()
                if METHOD == 'ref':
                    for i in range(REF_COUNT):
                        m.renderFrame()
                elif METHOD == "multigbuf":
                    for i in range(MULTIGBUF_COUNT):
                        m.renderFrame()
                else:
                    m.renderFrame()

        # capture = m.profiler.endCapture()
        # m.profiler.enabled = False
        # print(capture)
        # with open('event.txt', 'w') as f: f.write(f'{capture}\n')
        exit()
