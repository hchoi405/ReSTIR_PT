from falcor import *

import random

OUT_DIR = ""

INTERACTIVE = False

NAME = "VeachAjar"
FILE = "VeachAjar/VeachAjar.pyscene"
ANIM = [0, 100]
METHOD = "input"
REF_COUNT = 8192
ENABLE_RESTIR = True
MULTIGBUF_COUNT = 4

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


def add_path(g, gbuf, enable_restir=True, crn=False):

    # Toggle between ReSTIRPT and MegakernelPathTracer
    if enable_restir:
        PathTracer = createPass("ReSTIRPTPass", {
            'samplesPerPixel': 1,
            # 'syncSeedSSReSTIR': True if crn else False,
            'fixSpatialSeed': True if crn else False,
            'temporalSeedOffset': 1000000 if crn else 0,
        })
        path = "ReSTIRPT"
        ScreenSpaceReSTIRPass = createPass("ScreenSpaceReSTIRPass", {
            'options':ScreenSpaceReSTIROptions(
                fixSpatialSeed=True if crn else False,
                temporalSeedOffset=1000000 if crn else 0
            )
        })
        screenReSTIR = "ScreenSpaceReSTIR"
    else:
        if crn:
            print("ERROR: CRN for PathTracing is not supported.")
            exit()
        PathTracer = createPass("ReSTIRPTPass", {
            'samplesPerPixel': 1,
            'pathSamplingMode': PathSamplingMode.PathTracing
        })
        path = "ReSTIRPT"
        ScreenSpaceReSTIRPass = createPass("ScreenSpaceReSTIRPass", {
            'options':ScreenSpaceReSTIROptions(useTemporalResampling=False, useSpatialResampling=False)
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
        g.addEdge(f"{screenReSTIR}.color2", f"{path}.directLighting2")
        g.addEdge(f"{screenReSTIR}.temporalColor", f"{path}.directTemporal")

    return path, screenReSTIR


def add_gbuffer(g, pattern, init_seed=1):
    dicts = {
        'samplePattern': pattern,
        # sampleCount becomes a seed when used for [Uniform, UniformRandom, CRN] patterns
        # Uniform is for GBufferRaster, UniformRandom is only for GBufferRT (do not use for GBufferRaster)
        'sampleCount': init_seed,
        'useAlphaTest': True,
    }
    GBufferRaster = createPass("GBufferRaster", dicts)  # for input and svgf
    gbuf = "GBufferRaster"
    g.addPass(GBufferRaster, gbuf)
    return gbuf


def add_fileload(g):

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


def add_optix(g, gbuffer, path):
    OptixDenoiser = createPass("OptixDenoiser")
    optix = "OptixDenoiser"
    g.addPass(OptixDenoiser, optix)

    g.addEdge(f"{path}.color", f"{optix}.color")
    g.addEdge(f"{path}.albedo", f"{optix}.albedo")
    g.addEdge(f"{gbuffer}.normW", f"{optix}.normal")
    g.addEdge(f"{gbuffer}.mvec", f"{optix}.mvec")

    return optix


def add_svgf(g, gbuffer, path):
    SVGFPass = createPass("SVGFPass", {'Enabled': True, 'Iterations': 4, 'FeedbackTap': 1,
                          'VarianceEpsilon': 1.0e-4, 'PhiColor': 10.0, 'PhiNormal': 128.0, 'Alpha': 0.2, 'MomentsAlpha': 0.2})
    svgf = "SVGFPass"
    g.addPass(SVGFPass, svgf)

    g.addEdge(f"{gbuffer}.emissive", f"{svgf}.Emission")
    g.addEdge(f"{gbuffer}.posW", f"{svgf}.WorldPosition")
    g.addEdge(f"{gbuffer}.normW", f"{svgf}.WorldNormal")
    g.addEdge(f"{gbuffer}.pnFwidth", f"{svgf}.PositionNormalFwidth")
    g.addEdge(f"{gbuffer}.linearZ", f"{svgf}.LinearZ")
    g.addEdge(f"{gbuffer}.mvec", f"{svgf}.MotionVec")
    g.addEdge(f"{path}.color", f"{svgf}.Color")
    g.addEdge(f"{path}.albedo", f"{svgf}.Albedo")

    return svgf


def add_capture(g, pairs, start, end, opts=None):

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
    g = RenderGraph("PathGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Uniform)
    path, _ = add_path(g, gbuf, False)

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
    g.markOutput(f"{path}.color")

    return g


def render_input(start, end):
    g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Center)
    path, ss_restir = add_path(g, gbuf, enable_restir=ENABLE_RESTIR, crn=False)

    # Connect input/output
    pairs = {
        ## PathTracer
        'current': f"{path}.color",
        'current2': f"{path}.color2",
        'temporal': f"{path}.temporalColor",
        # 'indirect': f"{path}.indirect",
        # 'indirect1spp': f"{path}.debug",
        'albedo': f"{path}.albedo",
        # 'viewAlbedo': f"{path}.specularAlbedo",

        ## GBufferRaster
        'emissive': f"{gbuf}.emissive",
        'normal': f"{gbuf}.normW",
        'linearZ': f"{gbuf}.linearZ",
        'position': f"{gbuf}.posW",
        'mvec': f"{gbuf}.mvec",
        'pnFwidth': f"{gbuf}.pnFwidth",
        'specRough': f"{gbuf}.specRough",
        'diffuseOpacity': f"{gbuf}.diffuseOpacity",
    }
    if ENABLE_RESTIR:
        pairs['direct'] = f"{ss_restir}.color"
        pairs['direct2'] = f"{ss_restir}.color2"
        pairs['directTemporal'] = f"{ss_restir}.temporalColor"
        pass
    opts = {
        'captureCameraMat': False
    }
    if not INTERACTIVE:
        add_capture(g, pairs, start, end, opts)

    # Add output
    g.markOutput(f"{path}.color")

    return g


def render_crn(start, end):
    g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Center, init_seed=1000000)
    path, ss_restir = add_path(g, gbuf, enable_restir=ENABLE_RESTIR, crn=True)

    # Connect input/output
    pairs = {
        #
        'crn': f"{path}.color",
        # 'albedo2': f"{path}.albedo",
        # #
        # 'emissive2': f"{gbuf}.emissive",
        # 'normal2': f"{gbuf}.normW",
        # 'depth2': f"{gbuf}.linearZ",
        # 'position2': f"{gbuf}.posW",
        # 'mvec2': f"{gbuf}.mvec",
        # 'specRough2': f"{gbuf}.specRough",
        # 'diffuseOpacity2': f"{gbuf}.diffuseOpacity",
    }
    opts = {'captureCameraMat': False}
    if not INTERACTIVE:
        add_capture(g, pairs, start, end, opts)

    # Add output
    g.markOutput(f"{path}.color")

    return g


def render_svgf_optix(start, end):
    g = RenderGraph("MutlipleGraph")
    # Load libraries

    gbuffile, pathfile = add_fileload(g)

    svgf = add_svgf(g, gbuffile, pathfile)
    optix = add_optix(g, gbuffile, pathfile)

    # Connect input/output
    pairs = {
        # SVGF
        'svgf': f"{svgf}.Filtered image",
        # OptiX
        'optix': f"{optix}.output"
    }
    opts = {
        'captureCameraMat': False
    }
    add_capture(g, pairs, start, end, opts)

    # # Add output
    # g.markOutput(f"{optix}.output")
    # g.markOutput(f"{svgf}.Filtered image")

    return g


def render_multigbuf(start, end):
    g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, pattern=SamplePattern.Halton, init_seed=MULTIGBUF_COUNT)

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

    # Add output
    g.markOutput(f"{gbuf}.diffuseOpacity")

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

loadRenderPassLibrary("ReSTIRPTPass.dll")
loadRenderPassLibrary("ScreenSpaceReSTIRPass.dll")
loadRenderPassLibrary("GBuffer.dll")
loadRenderPassLibrary("FileloadPass.dll")
loadRenderPassLibrary("OptixDenoiser.dll")
loadRenderPassLibrary("SVGFPass.dll")
loadRenderPassLibrary("CapturePass.dll")
loadRenderPassLibrary("AccumulatePass.dll")

print("ANIM = ", ANIM)
if METHOD == 'input':
    graph = render_input(*ANIM)
elif METHOD == 'crn':
    graph = render_crn(*ANIM)
elif METHOD == 'ref':
    graph = render_ref(*ANIM)
elif METHOD == 'svgf_optix':
    graph = render_svgf_optix(*ANIM)
elif METHOD == 'multigbuf':
    graph = render_multigbuf(*ANIM)

m.addGraph(graph)
m.loadScene(FILE)
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
            elif METHOD == 'multigbuf':
                for i in range(MULTIGBUF_COUNT):
                    m.renderFrame()
            else:
                m.renderFrame()

    # capture = m.profiler.endCapture()
    # m.profiler.enabled = False
    # print(capture)
    # with open('event.txt', 'w') as f: f.write(f'{capture}\n')
    exit()
