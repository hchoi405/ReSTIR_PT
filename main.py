from falcor import *

import os

out_dir = "C:/Users/hchoi/repositories/rt-denoiser/data"

NAME = "BistroExterior2"
FILE = "C:/Users/hchoi/repositories/ORCA/Bistro/BistroExterior.pyscene"
ANIM = [700, 800]
METHOD = "input"
REF_COUNT = 8192
FILELOAD_STARTFRAME = 0
SINGLE_REPROJ_FRAME = 101

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


def addEdgeToReproject(g, path, gbuf, reproj):
    g.addEdge(f"{path}.color", f"{reproj}.Color")
    # g.addEdge(f"{path}.visibility", f"{reproj}.Viz")
    g.addEdge(f"{gbuf}.emissive", f"{reproj}.Emission")
    g.addEdge(f"{gbuf}.posW", f"{reproj}.WorldPosition")
    g.addEdge(f"{gbuf}.normW", f"{reproj}.WorldNormal")
    g.addEdge(f"{gbuf}.pnFwidth", f"{reproj}.PositionNormalFwidth")
    g.addEdge(f"{gbuf}.linearZ", f"{reproj}.LinearZ")
    g.addEdge(f"{gbuf}.mvec", f"{reproj}.MotionVec")
    g.addEdge(f"{gbuf}.diffuseOpacity", f"{reproj}.DiffuseOpacity")
    g.addEdge(f"{gbuf}.specRough", f"{reproj}.SpecRough")


def add_path_reproj(g, gbuf):
    loadRenderPassLibrary("PathTracer.dll")
    loadRenderPassLibrary("ReprojectPass.dll")

    PathTracer = createPass("PathTracer", {'samplesPerPixel': 1})
    Reproject = createPass("ReprojectPass", {"singleReprojFrame": SINGLE_REPROJ_FRAME})
    Reproject2 = createPass("ReprojectPass", {'separateBuffer': False})

    path = "PathTracer"
    reproj = "Reproject"
    reproj2 = "Reproject2"

    g.addPass(PathTracer, path)
    g.addPass(Reproject, reproj)
    g.addPass(Reproject2, reproj2)

    g.addEdge(f"{gbuf}.vbuffer", f"{path}.vbuffer")
    addEdgeToReproject(g, f"{path}", f"{gbuf}", reproj)
    addEdgeToReproject(g, f"{path}", f"{gbuf}", reproj2)

    return path, reproj, reproj2


def add_gbuffer(g, center=True):
    loadRenderPassLibrary("GBuffer.dll")

    if center:
        GBufferRaster = createPass("GBufferRaster", {'samplePattern': SamplePattern.Center, 'sampleCount': 1, 'useAlphaTest': True}) # for input and svgf
    else:
        GBufferRaster = createPass("GBufferRaster", {'samplePattern': SamplePattern.Uniform, 'sampleCount': 1, 'useAlphaTest': True}) # for input and svgf
    gbuf = "GBufferRaster"
    g.addPass(GBufferRaster, gbuf)
    return gbuf


def add_fileload(g):
    loadRenderPassLibrary("FileloadPass.dll")

    # key:value = filename:channelName
    channels = {
        'path': 'color',
        'albedo': 'albedo',
        'normal': 'normW',
        'mvec': 'mvec',
        'emissive': 'emissive',
        'depth': 'linearZ',
        'position': 'posW',
        'pnFwidth': 'pnFwidth',
    }
    input_dir = f"//CGLAB-NAS/NFSStorage/dataset_new/data_{NAME}"
    FileloadPassGbuf = createPass("FileloadPass", {
        'directory': input_dir,
        'filenames': list(channels.keys()),
        'channalNames': list(channels.values()),
        'startFrame': FILELOAD_STARTFRAME,
    })
    gbuffile = "GbufFileloadPass"
    g.addPass(FileloadPassGbuf, gbuffile)

    FileloadPassPath = createPass("FileloadPass", {
        'directory': input_dir,
        'filenames': list(channels.keys()),
        'channalNames': list(channels.values()),
        'startFrame': FILELOAD_STARTFRAME,
    })
    pathfile = "PathFileloadPass"
    g.addPass(FileloadPassPath, pathfile)

    return gbuffile, pathfile


def add_optix(g, gbuffer, path):
    loadRenderPassLibrary("OptixDenoiser.dll")
    OptixDenoiser = createPass("OptixDenoiser")
    optix = "OptixDenoiser"
    g.addPass(OptixDenoiser, optix)

    g.addEdge(f"{path}.color", f"{optix}.color")
    g.addEdge(f"{path}.albedo", f"{optix}.albedo")
    g.addEdge(f"{gbuffer}.normW", f"{optix}.normal")
    g.addEdge(f"{gbuffer}.mvec", f"{optix}.mvec")

    return optix


def add_svgf(g, gbuffer, path):
    loadRenderPassLibrary("SVGFPass.dll")
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
    loadRenderPassLibrary("CapturePass.dll")

    channels = list(pairs.keys())
    inputs = list(pairs.values())

    options = {
            'directory': out_dir,
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
    # Load libraries
    loadRenderPassLibrary("ReprojectPass.dll")
    loadRenderPassLibrary("GBuffer.dll")
    loadRenderPassLibrary("PathTracer.dll")
    loadRenderPassLibrary("CapturePass.dll")
    loadRenderPassLibrary("AccumulatePass.dll")

    # Create pass
    ReprojectPass = createPass("ReprojectPass")
    GBufferRaster = createPass("GBufferRaster", {'samplePattern': SamplePattern.Uniform, 'useAlphaTest': True})
    PathTracer = createPass("PathTracer", {'samplesPerPixel': 1})
    AccumulatePass = createPass("AccumulatePass", {'enabled': True})
    AccumulatePass2 = createPass("AccumulatePass", {'enabled': True})
    AccumulatePass3 = createPass("AccumulatePass", {'enabled': True})
    AccumulatePass4 = createPass("AccumulatePass", {'enabled': True})

    # Add pass
    reproj = "Reproject"
    g.addPass(ReprojectPass, reproj)
    g.addPass(GBufferRaster, "GBufferRaster")
    g.addPass(PathTracer, "PathTracer")
    g.addPass(AccumulatePass, "AccumulatePass")
    g.addPass(AccumulatePass2, "AccumulatePass2")
    g.addPass(AccumulatePass3, "AccumulatePass3")
    g.addPass(AccumulatePass4, "AccumulatePass4")

    # Connect input/output
    addEdgeToReproject(g, "PathTracer", "GBufferRaster", reproj)

    # Pass G-buffer to path tracer
    g.addEdge("GBufferRaster.vbuffer", "PathTracer.vbuffer")
    g.addEdge("GBufferRaster.emissive", "AccumulatePass4.input")
    g.addEdge("PathTracer.color", "AccumulatePass.input")
    g.addEdge("Reproject.Current", "AccumulatePass2.input")
    g.addEdge("PathTracer.envLight", "AccumulatePass3.input")

    pairs = {
        'ref': f'AccumulatePass.output',
        'ref_demodul': f'AccumulatePass2.output',
        'ref_envLight': f'AccumulatePass3.output',
        'ref_emissive': f'AccumulatePass4.output'
    }
    opts = {
        'accumulate': True,
        'accumulateCount': REF_COUNT,
    }

    add_capture(g, pairs, start, end, opts)
    g.markOutput("PathTracer.color")

    return g


def render_input(start, end):
    g = RenderGraph("MutlipleGraph")

    gbuf = add_gbuffer(g, center=True)
    path, reproj, reproj2 = add_path_reproj(g, gbuf)

    # Connect input/output
    pairs = {
        # Reproject for ours
        'current_demodul': f"{reproj}.Current",
        'accum1_demodul': f"{reproj}.Accumulated",
        'history1_demodul': f"{reproj}.History",
        'accumhistorylen1': f"{reproj}.Length",
        'accum2_demodul': f"{reproj}.Accumulated2",
        'history2_demodul': f"{reproj}.History2",
        'accumhistorylen2': f"{reproj}.Length2",
        'albedo': f"{reproj}.Albedo",
        # Reproject for others (BMFR, NBG)
        'accum_demodul': f"{reproj2}.Accumulated",
        'history_demodul': f"{reproj2}.History",
        'accumhistorylen': f"{reproj2}.Length",
        # PathTracer
        'path': f"{path}.color",
        'envLight': f"{path}.envLight",
        'visibility': f"{path}.visibility",
        # GBufferRaster
        'emissive': f"{gbuf}.emissive",
        'normal': f"{gbuf}.normW",
        'depth': f"{gbuf}.linearZ",
        'position': f"{gbuf}.posW",
        'mvec': f"{gbuf}.mvec",
        'pnFwidth': f"{gbuf}.pnFwidth",
        # 'specRough': f"{gbuf}.specRough",
        # 'diffuseOpacity': f"{gbuf}.diffuseOpacity",
        # # Path
        # 'albedo': f"{path}.albedo"
    }
    opts = {
        'captureCameraMat': True
    }
    add_capture(g, pairs, start, end, opts)

    # Add output
    g.markOutput("PathTracer.color")
    # g.markOutput("Reproject.History")
    # g.markOutput("Reproject.Accumulated")

    return g


def render_svgf_optix(start, end):
    g = RenderGraph("MutlipleGraph")
    # Load libraries
    # loadRenderPassLibrary("TorchPass.dll")

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


def render_gbufrand(start, end):
    g = RenderGraph("FinalGraph")
    # Load libraries
    loadRenderPassLibrary("CapturePass.dll")

    gbuf = add_gbuffer(g, False)

    # Create and add capture
    pairs = {
        'emissive2': f'{gbuf}.emissive',
        'normal2': f'{gbuf}.normW',
        'depth2': f'{gbuf}.linearZ',
        'position2': f'{gbuf}.posW',
        'mvec2': f'{gbuf}.mvec',
        'pnFwidth2': f'{gbuf}.pnFwidth',
        'specRough2': f'{gbuf}.specRough',
        'diffuseOpacity2': f'{gbuf}.diffuseOpacity'
    }
    add_capture(g, pairs, start, end)

    return g


if NAME == 'Dining-room-dynamic':
    # Dynamic directional light for dining-room
    # [-0.6, -0.0]
    start = -0.1
    end = -0.8
    step = -0.005
    num_frames = int((end - start) / step)
    ANIM = [0, num_frames]

ANIM[1] += 3 # Add more frames

if METHOD == 'input':
    graph = render_input(*ANIM)
elif METHOD == 'ref':
    graph = render_ref(*ANIM)
elif METHOD == 'gbufrand':
    graph = render_gbufrand(*ANIM)
elif METHOD == 'svgf_optix':
    graph = render_svgf_optix(*ANIM)

m.addGraph(graph)
m.loadScene(FILE)
# Call this after scene loading
m.scene.camera.nearPlane = 0.15 # Increase near plane to prevent Z-fighting

m.clock.framerate = 30
m.clock.time = 0
m.clock.pause()

# m.profiler.enabled = True
if NAME == 'Dining-room-dynamic':
    frame = 0
    for y in frange(start, end, step):
        m.clock.frame = frame
        m.scene.lights[0].direction.y = y
        if METHOD == 'ref':
            for _ in range(REF_COUNT):
                m.renderFrame()
        else:
            m.renderFrame()
        frame += 1
        if frame == ANIM[1] + 1: break

else:
    # Start frame
    for frame in range(*ANIM):
        # if frame == ANIM[0] + 10:
        #     m.profiler.startCapture()

        m.clock.frame = frame
        if METHOD == 'ref':
            for i in range(REF_COUNT):
                m.renderFrame()
        else:
            m.renderFrame()
        # print('frame:', m.clock.frame)

# capture = m.profiler.endCapture()
# m.profiler.enabled = False
# print(capture)
# with open('C:/Users/hchoi/repositories/rt-denoiser/event.txt', 'w') as f: f.write(f'{capture}\n')
exit()
